"""Item persistence helpers (CRUD against the ``items`` table)."""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from inventory.models import Item, ItemCreate, ItemUpdate

_UPDATABLE_COLUMNS = {"name", "description", "unit_price", "reorder_level", "active"}


def _utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with a trailing Z, e.g. 2026-01-02T03:04:05Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def get_item(conn: sqlite3.Connection, item_id: int) -> Optional[Item]:
    """Fetch a single item by id, or None if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return None
    return row_to_item(row)


def create_item(conn: sqlite3.Connection, payload: ItemCreate) -> Item:
    """Insert a new item and return it.

    Propagates sqlite3.IntegrityError on sku/barcode uniqueness violations.
    """
    cur = conn.execute(
        """
        INSERT INTO items (sku, name, description, unit_price, reorder_level, barcode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.sku,
            payload.name,
            payload.description,
            payload.unit_price,
            payload.reorder_level,
            payload.barcode,
            _utc_now_iso(),
        ),
    )
    item = get_item(conn, cur.lastrowid)
    assert item is not None  # row was just inserted
    return item


def update_item(
    conn: sqlite3.Connection, item_id: int, payload: ItemUpdate
) -> Optional[Item]:
    """Apply the provided (non-None) fields to an item.

    Returns the updated item, or None if the item does not exist.
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
    """Delete an item by id. Returns True if a row was deleted, False otherwise."""
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return cur.rowcount > 0
