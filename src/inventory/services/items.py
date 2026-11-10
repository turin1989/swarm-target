"""Item persistence helpers."""

import sqlite3
from typing import Optional

from inventory.models import Item, ItemCreate, ItemUpdate


def row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def get_item(conn: sqlite3.Connection, item_id: int) -> Optional[Item]:
    """Return the item with the given id, or None if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return None
    return row_to_item(row)


def create_item(conn: sqlite3.Connection, payload: ItemCreate) -> Item:
    """Insert a new item and return the persisted record.

    Raises sqlite3.IntegrityError if the sku or barcode already exists.
    """
    cur = conn.execute(
        """
        INSERT INTO items (sku, name, description, unit_price, reorder_level, barcode)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            payload.sku,
            payload.name,
            payload.description,
            payload.unit_price,
            payload.reorder_level,
            payload.barcode,
        ),
    )
    item = get_item(conn, cur.lastrowid)
    assert item is not None
    return item


def update_item(
    conn: sqlite3.Connection, item_id: int, payload: ItemUpdate
) -> Optional[Item]:
    """Apply the given updates to an item.

    Returns the updated item, or None if the item does not exist.
    """
    if get_item(conn, item_id) is None:
        return None
    updates = payload.model_dump(exclude_unset=True)
    allowed = {"name", "description", "unit_price", "reorder_level", "active"}
    updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if updates:
        if "active" in updates:
            updates["active"] = int(updates["active"])
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE items SET {assignments} WHERE id = ?", [*updates.values(), item_id]
        )
    return get_item(conn, item_id)


def delete_item(conn: sqlite3.Connection, item_id: int) -> bool:
    """Delete an item by id. Returns True if it existed, False otherwise."""
    if get_item(conn, item_id) is None:
        return False
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return True
