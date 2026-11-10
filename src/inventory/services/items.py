"""Item persistence helpers."""

import sqlite3
from typing import Optional

from inventory.db import utc_now_iso
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
    """Insert a new item and return it.

    Raises sqlite3.IntegrityError if the sku or barcode already exists.
    """
    cur = conn.execute(
        """
        INSERT INTO items (sku, name, description, unit_price, reorder_point, created_at, barcode)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.sku,
            payload.name,
            payload.description,
            payload.unit_price,
            payload.reorder_point,
            utc_now_iso(),
            payload.barcode,
        ),
    )
    item = get_item(conn, cur.lastrowid)
    assert item is not None  # just inserted
    return item


def update_item(
    conn: sqlite3.Connection, item_id: int, payload: ItemUpdate
) -> Optional[Item]:
    """Apply the given update to an item and return the updated item.

    Returns None if the item does not exist.
    """
    existing = get_item(conn, item_id)
    if existing is None:
        return None
    updates = payload.model_dump(exclude_unset=True)
    allowed = {"name", "description", "unit_price", "active"}
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
    """Delete the item with the given id. Returns True if it existed."""
    if get_item(conn, item_id) is None:
        return False
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return True
