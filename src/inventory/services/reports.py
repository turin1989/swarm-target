"""Reporting queries."""

import sqlite3

from inventory.models import LowStockEntry


def low_stock(
    conn: sqlite3.Connection, location_id: int | None = None
) -> list[LowStockEntry]:
    """Active items whose total stock is at or below their reorder point.

    When ``location_id`` is given, only stock at that location counts towards
    ``total_qty``; otherwise stock across all locations is summed.
    """
    join = "LEFT JOIN stock_levels s ON s.item_id = i.id"
    params: list = []
    if location_id is not None:
        join += " AND s.location_id = ?"
        params.append(location_id)
    rows = conn.execute(
        f"""
        SELECT i.id AS item_id, i.sku, i.name, i.reorder_point,
               COALESCE(SUM(s.qty), 0) AS total_qty
        FROM items i
        {join}
        WHERE i.active = 1
        GROUP BY i.id
        HAVING total_qty <= i.reorder_point
        ORDER BY i.sku
        """,
        params,
    ).fetchall()
    return [LowStockEntry(**dict(r)) for r in rows]


def movements_summary(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Count and total quantity of movements grouped by kind.

    Every known movement kind is present in the result; kinds with no
    movements report zeros.
    """
    summary: dict[str, dict[str, int]] = {
        kind: {"count": 0, "qty": 0} for kind in ("receive", "ship", "transfer")
    }
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
