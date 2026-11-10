"""Item persistence helpers."""

import sqlite3
from typing import Optional

from inventory.models import Item, ItemCreate, ItemUpdate


def _row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def get_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row is not None else None


def get_item_by_sku(conn: sqlite3.Connection, sku: str) -> Item | None:
    row = conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()
    return _row_to_item(row) if row is not None else None


def list_items(
    conn: sqlite3.Connection,
    active: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Item]:
    sql = "SELECT * FROM items"
    params: list = []
    if active is not None:
        sql += " WHERE active = ?"
        params.append(int(active))
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    params += [limit, offset]
    return [_row_to_item(r) for r in conn.execute(sql, params).fetchall()]


def create_item(conn: sqlite3.Connection, payload: ItemCreate) -> Item:
    """Insert a new item and return it.

    Raises sqlite3.IntegrityError if the sku already exists.
    """
    cur = conn.execute(
        """
        INSERT INTO items (sku, name, description, unit_price, reorder_point)
        VALUES (?, ?, ?, ?, ?)
        """,
        (payload.sku, payload.name, payload.description, payload.unit_price, payload.reorder_point),
    )
    item = get_item(conn, cur.lastrowid)
    assert item is not None
    return item


def update_item(conn: sqlite3.Connection, item_id: int, payload: ItemUpdate) -> Item | None:
    """Apply a partial update to an item. Returns None if the item does not exist."""
    if get_item(conn, item_id) is None:
        return None
    updates = payload.model_dump(exclude_unset=True)
    allowed = {"name", "description", "unit_price", "active"}
    updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if updates:
        if "active" in updates:
            updates["active"] = int(updates["active"])
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE items SET {assignments} WHERE id = ?", [*updates.values(), item_id])
    return get_item(conn, item_id)


def delete_item(conn: sqlite3.Connection, item_id: int) -> bool:
    """Delete an item. Returns True if a row was removed, False otherwise."""
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return cur.rowcount > 0
