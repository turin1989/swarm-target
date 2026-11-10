"""Stock level bookkeeping and movement application."""

import sqlite3

from inventory.models import Movement, MovementCreate, StockLevel
from inventory.services.errors import NotFoundError, ValidationError


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


def _set_level(conn: sqlite3.Connection, item_id: int, location_id: int, qty: int) -> None:
    conn.execute(
        """
        INSERT INTO stock_levels (item_id, location_id, qty) VALUES (?, ?, ?)
        ON CONFLICT(item_id, location_id) DO UPDATE SET qty = excluded.qty
        """,
        (item_id, location_id, qty),
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
    if m.qty <= 0:
        raise ValidationError("qty must be a positive integer")

    item = conn.execute("SELECT id FROM items WHERE id = ?", (m.item_id,)).fetchone()
    if item is None:
        raise NotFoundError(f"item {m.item_id} not found")

    if m.kind == "receive":
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        _adjust(conn, m.item_id, to_id, m.qty)
    elif m.kind == "ship":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        _adjust(conn, m.item_id, from_id, -m.qty)
    elif m.kind == "transfer":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        _adjust(conn, m.item_id, from_id, -m.qty)
        _adjust(conn, m.item_id, to_id, m.qty)
    elif m.kind == "adjust":
        if m.from_location_id is not None:
            raise ValidationError("from_location_id must be null for adjust movements")
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        _set_level(conn, m.item_id, to_id, m.qty)
    else:  # pragma: no cover - guarded by the Literal type
        raise ValidationError(f"unknown movement kind {m.kind!r}")

    cur = conn.execute(
        """
        INSERT INTO movements (item_id, kind, qty, from_location_id, to_location_id, note, reference)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (m.item_id, m.kind, m.qty, m.from_location_id, m.to_location_id, m.note, m.reference),
    )
    return get_movement(conn, cur.lastrowid)


def get_movement(conn: sqlite3.Connection, movement_id: int) -> Movement:
    row = conn.execute("SELECT * FROM movements WHERE id = ?", (movement_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"movement {movement_id} not found")
    return Movement(**dict(row))


def list_movements(conn: sqlite3.Connection, limit: int = 100, offset: int = 0) -> list[Movement]:
    rows = conn.execute(
        "SELECT * FROM movements ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [Movement(**dict(r)) for r in rows]
