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
    return [
        LowStockEntry(
            **dict(r), shortfall=max(0, r["reorder_point"] - r["total_qty"])
        )
        for r in rows
    ]


def movements_summary(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Per-kind count and total quantity of movements.

    All known kinds are always present; kinds with no movements report zeros.
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


def inventory_value(conn: sqlite3.Connection, location_id: int | None = None) -> float:
    """Total value of stock on hand (sum of qty * unit_price).

    If ``location_id`` is given, only stock held at that location is counted.
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
