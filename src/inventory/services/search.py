"""Item search."""

import sqlite3

from inventory.models import Item


def search_items(conn: sqlite3.Connection, q: str, limit: int = 50) -> list[Item]:
    """Substring match on sku or name."""
    pattern = f"*{q}*"
    rows = conn.execute(
        """
        SELECT * FROM items
        WHERE sku GLOB ? OR name GLOB ?
        ORDER BY name
        LIMIT ?
        """,
        (pattern, pattern, limit),
    ).fetchall()
    return [Item(**{**dict(r), "active": bool(r["active"])}) for r in rows]
