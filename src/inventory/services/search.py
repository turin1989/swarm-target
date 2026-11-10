"""Item search."""

import sqlite3

from inventory.models import Item


def search_items(conn: sqlite3.Connection, q: str, limit: int = 50) -> list[Item]:
    """Case-insensitive substring match on sku or name."""
    needle = q.lower()
    rows = conn.execute(
        """
        SELECT * FROM items
        WHERE instr(lower(sku), ?) > 0 OR instr(lower(name), ?) > 0
        ORDER BY name
        LIMIT ?
        """,
        (needle, needle, limit),
    ).fetchall()
    return [Item(**{**dict(r), "active": bool(r["active"])}) for r in rows]
