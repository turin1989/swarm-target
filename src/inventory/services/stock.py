"""Stock level bookkeeping and movement application."""

import sqlite3

from inventory.models import Movement, MovementCreate, StockLevel


class StockError(Exception):
    """Raised when a movement cannot be applied."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_stock_level(conn: sqlite3.Connection, item_id: int, location_id: int) -> int:
    row = conn.execute(
        "SELECT qty FROM stock_levels WHERE item_id = ? AND location_id = ?",
        (item_id, location_id),
    ).fetchone()
    return int(row["qty"]) if row else 0


def get_item_levels(conn: sqlite3.Connection, item_id: int) -> list[StockLevel]:
    rows = conn.execute(
        "SELECT item_id, location_id, qty FROM stock_levels WHERE item_id = ? ORDER BY location_id",
        (item_id,),
    ).fetchall()
    return [StockLevel(**dict(r)) for r in rows]


def get_location_levels(conn: sqlite3.Connection, location_id: int) -> list[StockLevel]:
    """Return all non-zero stock levels held at a location, ordered by item_id."""
    rows = conn.execute(
        """
        SELECT item_id, location_id, qty FROM stock_levels
        WHERE location_id = ? AND qty != 0
        ORDER BY item_id
        """,
        (location_id,),
    ).fetchall()
    return [StockLevel(**dict(r)) for r in rows]


def total_stock(conn: sqlite3.Connection, item_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(qty), 0) AS total FROM stock_levels WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    return int(row["total"])


def _adjust(conn: sqlite3.Connection, item_id: int, location_id: int, delta: int) -> None:
    conn.execute(
        """
        INSERT INTO stock_levels (item_id, location_id, qty) VALUES (?, ?, ?)
        ON CONFLICT(item_id, location_id) DO UPDATE SET qty = qty + excluded.qty
        """,
        (item_id, location_id, delta),
    )


def _require_available(
    conn: sqlite3.Connection, item_id: int, location_id: int, qty: int
) -> None:
    available = get_stock_level(conn, item_id, location_id)
    if qty > available:
        raise StockError(
            f"insufficient stock at location {location_id}: have {available}, need {qty}",
            status_code=409,
        )


def _require_location(conn: sqlite3.Connection, location_id: int | None, field: str) -> int:
    if location_id is None:
        raise StockError(f"{field} is required for this movement kind")
    row = conn.execute("SELECT id FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise StockError(f"location {location_id} not found", status_code=404)
    return location_id


def apply_movement(conn: sqlite3.Connection, m: MovementCreate) -> Movement:
    """Validate and apply a stock movement, returning the persisted record."""
    if m.qty <= 0:
        raise StockError("qty must be a positive integer", status_code=422)

    item = conn.execute("SELECT id FROM items WHERE id = ?", (m.item_id,)).fetchone()
    if item is None:
        raise StockError(f"item {m.item_id} not found", status_code=404)

    if m.kind == "receive":
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        _adjust(conn, m.item_id, to_id, m.qty)
    elif m.kind == "ship":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        _require_available(conn, m.item_id, from_id, m.qty)
        _adjust(conn, m.item_id, from_id, -m.qty)
    elif m.kind == "transfer":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        if from_id == to_id:
            raise StockError("cannot transfer to the same location")
        _require_available(conn, m.item_id, from_id, m.qty)
        _adjust(conn, m.item_id, from_id, -m.qty)
        _adjust(conn, m.item_id, to_id, m.qty)
    else:  # pragma: no cover - guarded by the Literal type
        raise StockError(f"unknown movement kind {m.kind!r}")

    cur = conn.execute(
        """
        INSERT INTO movements (item_id, kind, qty, from_location_id, to_location_id, note)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (m.item_id, m.kind, m.qty, m.from_location_id, m.to_location_id, m.note),
    )
    return get_movement(conn, cur.lastrowid)


def reverse_movement(conn: sqlite3.Connection, movement_id: int) -> Movement:
    """Create and apply a new movement that undoes an existing one."""
    original = get_movement(conn, movement_id)

    if original.kind == "receive":
        kind = "ship"
    elif original.kind == "ship":
        kind = "receive"
    else:  # transfer
        kind = "transfer"

    reversal = MovementCreate(
        item_id=original.item_id,
        kind=kind,
        qty=original.qty,
        from_location_id=original.to_location_id,
        to_location_id=original.from_location_id,
        note=f"reversal of {movement_id}",
    )
    return apply_movement(conn, reversal)


def get_movement(conn: sqlite3.Connection, movement_id: int) -> Movement:
    row = conn.execute("SELECT * FROM movements WHERE id = ?", (movement_id,)).fetchone()
    if row is None:
        raise StockError(f"movement {movement_id} not found", status_code=404)
    return Movement(**dict(row))


def list_movements(
    conn: sqlite3.Connection,
    limit: int = 100,
    offset: int = 0,
    item_id: int | None = None,
    kind: str | None = None,
) -> list[Movement]:
    sql = "SELECT * FROM movements"
    params: list = []
    conditions: list[str] = []
    if item_id is not None:
        conditions.append("item_id = ?")
        params.append(item_id)
    if kind is not None:
        conditions.append("kind = ?")
        params.append(kind)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    return [Movement(**dict(r)) for r in rows]
