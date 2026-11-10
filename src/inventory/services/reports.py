"""Reporting queries."""

import sqlite3

from inventory.models import LowStockEntry


def low_stock(
    conn: sqlite3.Connection, location_id: int | None = None
) -> list[LowStockEntry]:
    """Active items whose total stock is at or below their reorder level.

    When ``location_id`` is given, only stock held at that location counts
    towards ``total_qty``; otherwise stock across all locations is summed.
    """
    join_params: list = []
    join_filter = ""
    if location_id is not None:
        join_filter = " AND s.location_id = ?"
        join_params.append(location_id)
    rows = conn.execute(
        f"""
        SELECT i.id AS item_id, i.sku, i.name, i.reorder_level,
               COALESCE(SUM(s.qty), 0) AS total_qty
        FROM items i
        LEFT JOIN stock_levels s ON s.item_id = i.id{join_filter}
        WHERE i.active = 1
        GROUP BY i.id
        HAVING total_qty <= i.reorder_level
        ORDER BY i.sku
        """,
        join_params,
    ).fetchall()
    return [
        LowStockEntry(
            **dict(r),
            shortfall=max(0, r["reorder_level"] - r["total_qty"]),
        )
        for r in rows
    ]


def inventory_value(conn: sqlite3.Connection, location_id: int | None = None) -> float:
    """Total value of stock on hand (sum of qty * unit_price).

    When ``location_id`` is given, only stock held at that location is summed.
    """
    query = """
        SELECT COALESCE(SUM(s.qty * i.unit_price), 0) AS value
        FROM stock_levels s JOIN items i ON i.id = s.item_id
        """
    params: list = []
    if location_id is not None:
        query += " WHERE s.location_id = ?"
        params.append(location_id)
    row = conn.execute(query, params).fetchone()
    return float(row["value"])


def stats(conn: sqlite3.Connection) -> dict:
    """Entity counts plus the total number of units in stock."""
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
