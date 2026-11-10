"""Item persistence helpers (CRUD against the ``items`` table)."""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from inventory.models import Item, ItemCreate, ItemUpdate
from inventory.services.errors import ConflictError


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with a ``Z`` suffix, e.g. 2026-01-02T03:04:05Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def get_item(conn: sqlite3.Connection, item_id: int) -> Optional[Item]:
    """Return the item with ``item_id`` or ``None`` if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row is not None else None


def get_item_by_sku(conn: sqlite3.Connection, sku: str) -> Optional[Item]:
    """Return the item with exactly ``sku`` or ``None`` if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()
    return _row_to_item(row) if row is not None else None


def create_item(conn: sqlite3.Connection, payload: ItemCreate) -> Item:
    """Insert a new item and return the persisted record.

    Raises :class:`ConflictError` if the SKU already exists.
    """
    try:
        cur = conn.execute(
            """
            INSERT INTO items (sku, name, description, unit_price, reorder_level, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.sku,
                payload.name,
                payload.description,
                payload.unit_price,
                payload.reorder_level,
                utc_now_iso(),
            ),
        )
    except sqlite3.IntegrityError:
        raise ConflictError(f"sku {payload.sku!r} already exists")
    item = get_item(conn, cur.lastrowid)
    assert item is not None  # just inserted
    return item


_UPDATABLE_COLUMNS = {"name", "description", "unit_price", "reorder_level", "active"}


def update_item(
    conn: sqlite3.Connection, item_id: int, payload: ItemUpdate
) -> Optional[Item]:
    """Apply the fields set in ``payload`` and return the updated item.

    Returns ``None`` if the item does not exist. Fields that were omitted
    (or explicitly null) are left untouched.
    """
    existing = get_item(conn, item_id)
    if existing is None:
        return None
    updates = payload.model_dump(exclude_unset=True)
    updates = {k: v for k, v in updates.items() if k in _UPDATABLE_COLUMNS and v is not None}
    if updates:
        if "active" in updates:
            updates["active"] = int(updates["active"])
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE items SET {assignments} WHERE id = ?", [*updates.values(), item_id]
        )
    return get_item(conn, item_id)


def delete_item(conn: sqlite3.Connection, item_id: int) -> bool:
    """Delete the item with ``item_id``; return True if a row was deleted."""
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return cur.rowcount > 0
