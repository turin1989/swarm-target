"""Reporting queries."""

import sqlite3

from inventory.models import LowStockEntry


def low_stock(conn: sqlite3.Connection) -> list[LowStockEntry]:
    """Active items whose total stock across all locations is below their reorder point."""
    rows = conn.execute(
        """
        SELECT i.id AS item_id, i.sku, i.name, i.reorder_point,
               COALESCE(SUM(s.qty), 0) AS total_qty
        FROM items i
        LEFT JOIN stock_levels s ON s.item_id = i.id
        WHERE i.active = 1
        GROUP BY i.id
        HAVING total_qty < i.reorder_point
        ORDER BY i.sku
        """
    ).fetchall()
    return [LowStockEntry(**dict(r)) for r in rows]


def stats(conn: sqlite3.Connection) -> dict:
    """Entity counts plus the total number of stocked units."""
    row = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM items) AS items,
            (SELECT COUNT(*) FROM items WHERE active = 1) AS active_items,
            (SELECT COUNT(*) FROM locations) AS locations,
            (SELECT COUNT(*) FROM movements) AS movements,
            (SELECT COALESCE(SUM(qty), 0) FROM stock_levels) AS total_units
        """
    ).fetchone()
    return dict(row)


def inventory_value(conn: sqlite3.Connection) -> float:
    """Total value of stock on hand (sum of qty * unit_price)."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(s.qty * i.unit_price), 0) AS value
        FROM stock_levels s JOIN items i ON i.id = s.item_id
        """
    ).fetchone()
    return float(row["value"])
