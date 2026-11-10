"""Stock level bookkeeping and movement application."""

import sqlite3
from datetime import datetime, timezone

from inventory.models import Movement, MovementCreate, StockLevel
from inventory.services.errors import ConflictError, NotFoundError, ValidationError


def get_stock_level(conn: sqlite3.Connection, item_id: int, location_id: int) -> int:
    row = conn.execute(
        "SELECT qty FROM stock_levels WHERE item_id = ? AND location_id = ?",
        (item_id, location_id),
    ).fetchone()
    return int(row["qty"]) if row else 0


def _row_to_stock_level(row: sqlite3.Row) -> StockLevel:
    # The database column is still named ``qty``; the API field is ``quantity``.
    data = dict(row)
    data["quantity"] = data.pop("qty")
    return StockLevel(**data)


def get_item_levels(conn: sqlite3.Connection, item_id: int) -> list[StockLevel]:
    rows = conn.execute(
        "SELECT item_id, location_id, qty FROM stock_levels WHERE item_id = ? ORDER BY location_id",
        (item_id,),
    ).fetchall()
    return [_row_to_stock_level(r) for r in rows]


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


def _require_location(conn: sqlite3.Connection, location_id: int | None, field: str) -> int:
    if location_id is None:
        raise ValidationError(f"{field} is required for this movement kind")
    row = conn.execute("SELECT id FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"location {location_id} not found")
    return location_id


def _utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (e.g. ``2026-11-10T12:34:56+00:00``)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def apply_movement(conn: sqlite3.Connection, m: MovementCreate) -> Movement:
    """Validate and apply a stock movement, returning the persisted record."""
    if m.quantity <= 0:
        raise ValidationError("quantity must be a positive integer")

    item = conn.execute(
        "SELECT id, active FROM items WHERE id = ?", (m.item_id,)
    ).fetchone()
    if item is None:
        raise NotFoundError(f"item {m.item_id} not found")
    if not item["active"]:
        raise ConflictError(f"item {m.item_id} is inactive and cannot be moved")

    if m.kind == "receive":
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        _adjust(conn, m.item_id, to_id, m.quantity)
    elif m.kind == "ship":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        _adjust(conn, m.item_id, from_id, -m.quantity)
    elif m.kind == "transfer":
        from_id = _require_location(conn, m.from_location_id, "from_location_id")
        to_id = _require_location(conn, m.to_location_id, "to_location_id")
        if from_id == to_id:
            raise ValidationError("cannot transfer to the same location")
        _adjust(conn, m.item_id, from_id, -m.quantity)
        _adjust(conn, m.item_id, to_id, m.quantity)
    else:  # pragma: no cover - guarded by the Literal type
        raise ValidationError(f"unknown movement kind {m.kind!r}")

    created_at = _utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO movements (item_id, kind, qty, from_location_id, to_location_id, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            m.item_id,
            m.kind,
            m.quantity,
            m.from_location_id,
            m.to_location_id,
            m.note,
            created_at,
        ),
    )
    return get_movement(conn, cur.lastrowid)


def _row_to_movement(row: sqlite3.Row) -> Movement:
    # The database column is still named ``qty``; the API field is ``quantity``.
    data = dict(row)
    data["quantity"] = data.pop("qty")
    return Movement(**data)


def get_movement(conn: sqlite3.Connection, movement_id: int) -> Movement:
    row = conn.execute("SELECT * FROM movements WHERE id = ?", (movement_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"movement {movement_id} not found")
    return _row_to_movement(row)


def list_movements(conn: sqlite3.Connection, limit: int = 100, offset: int = 0) -> list[Movement]:
    rows = conn.execute(
        "SELECT * FROM movements ORDER BY id LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [_row_to_movement(r) for r in rows]
