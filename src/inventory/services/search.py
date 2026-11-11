"""Item search."""

import sqlite3

from inventory.models import Item


def search_items(conn: sqlite3.Connection, q: str, limit: int = 50) -> list[Item]:
    """Case-insensitive substring match on sku or name."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped.lower()}%"
    rows = conn.execute(
        """
        SELECT * FROM items
        WHERE LOWER(sku) LIKE ? ESCAPE '\\' OR LOWER(name) LIKE ? ESCAPE '\\'
        ORDER BY name
        LIMIT ?
        """,
        (pattern, pattern, limit),
    ).fetchall()
    return [Item(**{**dict(r), "active": bool(r["active"])}) for r in rows]
