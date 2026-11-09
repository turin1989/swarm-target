"""Reporting queries."""

import sqlite3
from typing import Optional

from inventory.models import LowStockEntry


def low_stock(
    conn: sqlite3.Connection, location_id: Optional[int] = None
) -> list[LowStockEntry]:
    """Active items whose stock is at or below their reorder point.

    By default ``total_qty`` sums stock across all locations. When
    ``location_id`` is given, only stock at that location is counted.
    """
    join_condition = "s.item_id = i.id"
    params: list = []
    if location_id is not None:
        join_condition += " AND s.location_id = ?"
        params.append(location_id)
    rows = conn.execute(
        f"""
        SELECT i.id AS item_id, i.sku, i.name, i.reorder_point,
               COALESCE(SUM(s.qty), 0) AS total_qty
        FROM items i
        LEFT JOIN stock_levels s ON {join_condition}
        WHERE i.active = 1
        GROUP BY i.id
        HAVING total_qty <= i.reorder_point
        ORDER BY i.sku
        """,
        params,
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
