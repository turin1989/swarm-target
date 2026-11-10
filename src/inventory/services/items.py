"""Item persistence helpers.

All inline SQL for item CRUD lives here so the HTTP layer (``inventory.api``)
only deals with request/response concerns.
"""

import sqlite3
from typing import Optional

from inventory.db import utc_now_iso
from inventory.models import Item, ItemCreate, ItemUpdate
from inventory.services.errors import ConflictError

# Columns a PUT /items/{id} payload is allowed to change.
_UPDATABLE_COLUMNS = {"name", "description", "unit_price", "reorder_level", "active"}


def row_to_item(row: sqlite3.Row) -> Item:
    """Convert a ``items`` table row into an :class:`Item` model."""
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def get_item(conn: sqlite3.Connection, item_id: int) -> Optional[Item]:
    """Return the item with ``item_id``, or ``None`` if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return None
    return row_to_item(row)


def get_item_by_sku(conn: sqlite3.Connection, sku: str) -> Optional[Item]:
    """Return the item with exactly ``sku``, or ``None`` if it does not exist."""
    row = conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return None
    return row_to_item(row)


def create_item(conn: sqlite3.Connection, payload: ItemCreate) -> Item:
    """Insert a new item and return the persisted record.

    Raises :class:`ConflictError` if the sku or barcode already exists.
    """
    try:
        cur = conn.execute(
            """
            INSERT INTO items (sku, name, description, unit_price, reorder_level, created_at, barcode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.sku,
                payload.name,
                payload.description,
                payload.unit_price,
                payload.reorder_level,
                utc_now_iso(),
                payload.barcode,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "barcode" in str(exc):
            raise ConflictError(f"barcode {payload.barcode!r} already exists")
        raise ConflictError(f"sku {payload.sku!r} already exists")
    item = get_item(conn, cur.lastrowid)
    assert item is not None  # we just inserted it inside this transaction
    return item


def update_item(
    conn: sqlite3.Connection, item_id: int, payload: ItemUpdate
) -> Optional[Item]:
    """Apply the set fields of ``payload`` to an item.

    Returns the updated item, or ``None`` if no item with ``item_id`` exists.
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
    """Delete an item. Returns True if a row was removed, False if not found."""
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    return cur.rowcount > 0
