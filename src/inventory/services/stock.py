"""Stock level bookkeeping and movement application."""

import sqlite3
from datetime import datetime, timezone

from inventory.models import Movement, MovementCreate, StockLevel
from inventory.services.errors import ConflictError, NotFoundError, ValidationError


def _utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with a trailing Z, e.g. 2026-01-02T03:04:05Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    return [
        StockLevel(item_id=r["item_id"], location_id=r["location_id"], quantity=r["qty"])
        for r in rows
    ]


def get_location_levels(conn: sqlite3.Connection, location_id: int) -> list[StockLevel]:
    """All non-zero stock levels held at a location, ordered by item_id.

    Raises NotFoundError (404) if the location does not exist.
    """
    row = conn.execute("SELECT id FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"location {location_id} not found")
    rows = conn.execute(
        """
        SELECT item_id, location_id, qty FROM stock_levels
        WHERE location_id = ? AND qty != 0
        ORDER BY item_id
        """,
        (location_id,),
    ).fetchall()
    return [
        StockLevel(item_id=r["item_id"], location_id=r["location_id"], quantity=r["qty"])
        for r in rows
    ]


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


def _set_level(conn: sqlite3.Connection, item_id: int, location_id: int, qty: int) -> None:
    conn.execute(
        """
        INSERT INTO stock_levels (item_id, location_id, qty) VALUES (?, ?, ?)
        ON CONFLICT(item_id, location_id) DO UPDATE SET qty = excluded.qty
        """,
        (item_id, location_id, qty),
    )


def _require_available(
    conn: sqlite3.Connection, item_id: int, location_id: int, qty: int
) -> None:
    available = get_stock_level(conn, item_id, location_id)
    if qty > available:
        raise ConflictError(
            f"insufficient stock for item {item_id} at location {location_id}: "
            f"requested {qty}, available {available}"
        )


def _require_location(conn: sqlite3.Connection, location_id: int | None, field: str) -> int:
    if location_id is None:
        raise ValidationError(f"{field} is required for this movement kind")
    row = conn.execute("SELECT id FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"location {location_id} not found")
    return location_id


def apply_movement(conn: sqlite3.Connection, m: MovementCreate) -> Movement:
    """Validate and apply a stock movement, returning the persisted record."""
    if m.quantity <= 0:
        raise ValidationError("quantity must be a positive integer", status_code=422)

    item = conn.execute("SELECT id, active FROM items WHERE id = ?", (m.item_id,)).fetchone()
    if item is None:
        raise NotFoundError(f"item {m.item_id} not found")
    if not item["active"]:
        raise ConflictError(f"item {m.item_id} is inactive")

    if m.kind == "receive":
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        _adjust(conn, m.item_id, to_id, m.quantity)
    elif m.kind == "ship":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        _require_available(conn, m.item_id, from_id, m.quantity)
        _adjust(conn, m.item_id, from_id, -m.quantity)
    elif m.kind == "transfer":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        if from_id == to_id:
            raise ValidationError("cannot transfer to the same location")
        _require_available(conn, m.item_id, from_id, m.quantity)
        _adjust(conn, m.item_id, from_id, -m.quantity)
        _adjust(conn, m.item_id, to_id, m.quantity)
    elif m.kind == "adjust":
        if m.from_location_id is not None:
            raise ValidationError("from_location_id must be null for adjust movements")
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        _set_level(conn, m.item_id, to_id, m.quantity)
    else:  # pragma: no cover - guarded by the Literal type
        raise ValidationError(f"unknown movement kind {m.kind!r}")

    cur = conn.execute(
        """
        INSERT INTO movements
            (item_id, kind, qty, from_location_id, to_location_id, note, reference, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            m.item_id,
            m.kind,
            m.quantity,
            m.from_location_id,
            m.to_location_id,
            m.note,
            m.reference,
            _utc_now_iso(),
        ),
    )
    return get_movement(conn, cur.lastrowid)


def _row_to_movement(row: sqlite3.Row) -> Movement:
    """Map a movements table row (column ``qty``) to the API model (``quantity``)."""
    data = dict(row)
    data["quantity"] = data.pop("qty")
    return Movement(**data)


def reverse_movement(conn: sqlite3.Connection, movement_id: int) -> Movement:
    """Create and apply a new movement that undoes an existing one."""
    original = get_movement(conn, movement_id)
    note = f"reversal of {movement_id}"

    if original.kind == "receive":
        reversal = MovementCreate(
            item_id=original.item_id,
            kind="ship",
            quantity=original.quantity,
            from_location_id=original.to_location_id,
            note=note,
        )
    elif original.kind == "ship":
        reversal = MovementCreate(
            item_id=original.item_id,
            kind="receive",
            quantity=original.quantity,
            to_location_id=original.from_location_id,
            note=note,
        )
    elif original.kind == "transfer":
        reversal = MovementCreate(
            item_id=original.item_id,
            kind="transfer",
            quantity=original.quantity,
            from_location_id=original.to_location_id,
            to_location_id=original.from_location_id,
            note=note,
        )
    else:
        raise ValidationError(f"{original.kind} movements cannot be reversed")

    return apply_movement(conn, reversal)


def get_movement(conn: sqlite3.Connection, movement_id: int) -> Movement:
    row = conn.execute("SELECT * FROM movements WHERE id = ?", (movement_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"movement {movement_id} not found")
    return _row_to_movement(row)


def list_movements(
    conn: sqlite3.Connection,
    item_id: int | None = None,
    kind: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Movement]:
    sql = "SELECT * FROM movements"
    params: list = []
    clauses: list[str] = []
    if item_id is not None:
        clauses.append("item_id = ?")
        params.append(item_id)
    if kind is not None:
        clauses.append("kind = ?")
        params.append(kind)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_movement(r) for r in rows]
