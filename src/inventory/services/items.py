"""Item persistence helpers."""

import sqlite3
from datetime import datetime, timezone

from inventory.models import Item, ItemCreate, ItemUpdate

# Columns a client is allowed to change via update_item.
_UPDATABLE_FIELDS = {"name", "description", "unit_price", "active"}


def row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def get_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    """Return the item with the given id, or None if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return None
    return row_to_item(row)


def get_item_by_sku(conn: sqlite3.Connection, sku: str) -> Item | None:
    """Return the item with the given sku, or None if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return None
    return row_to_item(row)


def create_item(conn: sqlite3.Connection, payload: ItemCreate) -> Item:
    """Insert a new item and return the persisted record.

    Raises sqlite3.IntegrityError if the sku already exists.
    """
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
            created_at,
        ),
    )
    item = get_item(conn, cur.lastrowid)
    assert item is not None  # just inserted
    return item


def update_item(conn: sqlite3.Connection, item_id: int, payload: ItemUpdate) -> Item | None:
    """Apply a partial update and return the updated item, or None if missing."""
    if get_item(conn, item_id) is None:
        return None
    updates = payload.model_dump(exclude_unset=True)
    updates = {k: v for k, v in updates.items() if k in _UPDATABLE_FIELDS and v is not None}
    if updates:
        if "active" in updates:
            updates["active"] = int(updates["active"])
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE items SET {assignments} WHERE id = ?", [*updates.values(), item_id])
    return get_item(conn, item_id)


def delete_item(conn: sqlite3.Connection, item_id: int) -> bool:
    """Delete the item with the given id. Returns True if a row was removed."""
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return cur.rowcount > 0
