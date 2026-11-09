"""Item search."""

import sqlite3

from inventory.models import Item


def search_items(conn: sqlite3.Connection, q: str, limit: int = 50) -> list[Item]:
    """Case-insensitive substring match on sku, name or description."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    rows = conn.execute(
        """
        SELECT * FROM items
        WHERE sku LIKE ? ESCAPE '\\'
           OR name LIKE ? ESCAPE '\\'
           OR description LIKE ? ESCAPE '\\'
        ORDER BY name
        LIMIT ?
        """,
        (pattern, pattern, pattern, limit),
    ).fetchall()
    return [Item(**{**dict(r), "active": bool(r["active"])}) for r in rows]
