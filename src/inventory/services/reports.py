"""Reporting queries."""

import sqlite3

from inventory.models import LowStockEntry


def low_stock(conn: sqlite3.Connection) -> list[LowStockEntry]:
    """Active items whose total stock across all locations is at or below their reorder point."""
    rows = conn.execute(
        """
        SELECT i.id AS item_id, i.sku, i.name, i.reorder_point,
               COALESCE(SUM(s.qty), 0) AS total_qty
        FROM items i
        LEFT JOIN stock_levels s ON s.item_id = i.id
        WHERE i.active = 1
        GROUP BY i.id
        HAVING total_qty <= i.reorder_point
        ORDER BY i.sku
        """
    ).fetchall()
    return [LowStockEntry(**dict(r)) for r in rows]


MOVEMENT_KINDS = ("receive", "ship", "transfer")


def movements_summary(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Per-kind movement count and total quantity; all kinds present, zeroed if absent."""
    summary = {kind: {"count": 0, "qty": 0} for kind in MOVEMENT_KINDS}
    rows = conn.execute(
        """
        SELECT kind, COUNT(*) AS count, COALESCE(SUM(qty), 0) AS qty
        FROM movements
        GROUP BY kind
        """
    ).fetchall()
    for row in rows:
        if row["kind"] in summary:
            summary[row["kind"]] = {"count": row["count"], "qty": row["qty"]}
    return summary


def inventory_value(conn: sqlite3.Connection) -> float:
    """Total value of stock on hand (sum of qty * unit_price)."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(s.qty * i.unit_price), 0) AS value
        FROM stock_levels s JOIN items i ON i.id = s.item_id
        """
    ).fetchone()
    return float(row["value"])
