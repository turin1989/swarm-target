"""Reporting queries."""

import sqlite3

from inventory.models import LowStockEntry


def low_stock(conn: sqlite3.Connection) -> list[LowStockEntry]:
    """Active items whose total stock across all locations is at or below their reorder level."""
    rows = conn.execute(
        """
        SELECT i.id AS item_id, i.sku, i.name, i.reorder_level,
               COALESCE(SUM(s.qty), 0) AS total_qty
        FROM items i
        LEFT JOIN stock_levels s ON s.item_id = i.id
        WHERE i.active = 1
        GROUP BY i.id
        HAVING total_qty <= i.reorder_level
        ORDER BY i.sku
        """
    ).fetchall()
    return [LowStockEntry(**dict(r)) for r in rows]


def inventory_value(conn: sqlite3.Connection) -> float:
    """Total value of stock on hand (sum of qty * unit_price)."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(s.qty * i.unit_price), 0) AS value
        FROM stock_levels s JOIN items i ON i.id = s.item_id
        """
    ).fetchone()
    return float(row["value"])
