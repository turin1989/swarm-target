"""Bulk item persistence helpers."""

import sqlite3
from datetime import datetime, timezone

from inventory.models import ItemCreate


class BulkSkuConflictError(Exception):
    """Raised when a sku in a bulk payload already exists (or repeats)."""

    def __init__(self, sku: str) -> None:
        self.sku = sku
        super().__init__(f"sku {sku!r} already exists")


def insert_items(conn: sqlite3.Connection, payloads: list[ItemCreate]) -> list[int]:
    """Insert every item and return the new row ids.

    Raises BulkSkuConflictError on the first duplicate sku; the caller is
    expected to roll back so the whole batch is atomic.
    """
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    created_ids: list[int] = []
    for item in payloads:
        try:
            cur = conn.execute(
                """
                INSERT INTO items (sku, name, description, unit_price, reorder_level, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.sku,
                    item.name,
                    item.description,
                    item.unit_price,
                    item.reorder_level,
                    created_at,
                ),
            )
        except sqlite3.IntegrityError:
            raise BulkSkuConflictError(item.sku)
        created_ids.append(cur.lastrowid)
    return created_ids
