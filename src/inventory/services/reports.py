"""Reporting queries."""

import sqlite3

from inventory.models import LowStockEntry


def low_stock(
    conn: sqlite3.Connection, location_id: int | None = None
) -> list[LowStockEntry]:
    """Active items whose total stock is at or below their reorder level.

    When ``location_id`` is given, only stock at that location counts
    towards ``total_qty``; otherwise stock across all locations is summed.
    """
    params: list = []
    join = "LEFT JOIN stock_levels s ON s.item_id = i.id"
    if location_id is not None:
        join += " AND s.location_id = ?"
        params.append(location_id)
    rows = conn.execute(
        f"""
        SELECT i.id AS item_id, i.sku, i.name, i.reorder_level,
               COALESCE(SUM(s.qty), 0) AS total_qty
        FROM items i
        {join}
        WHERE i.active = 1
        GROUP BY i.id
        HAVING total_qty <= i.reorder_level
        ORDER BY i.sku
        """,
        params,
    ).fetchall()
    return [
        LowStockEntry(**dict(r), shortfall=max(r["reorder_level"] - r["total_qty"], 0))
        for r in rows
    ]


def stats(conn: sqlite3.Connection) -> dict:
    """Entity counts and total stock units."""
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


_MOVEMENT_SUMMARY_KINDS = ("receive", "ship", "transfer")


def movements_summary(conn: sqlite3.Connection) -> dict:
    """Count and total quantity of movements, grouped by kind.

    Every kind in ``_MOVEMENT_SUMMARY_KINDS`` is present in the result,
    with zeros when there are no movements of that kind.
    """
    summary = {kind: {"count": 0, "qty": 0} for kind in _MOVEMENT_SUMMARY_KINDS}
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


def inventory_value(
    conn: sqlite3.Connection, location_id: int | None = None
) -> float:
    """Total value of stock on hand (sum of qty * unit_price).

    When ``location_id`` is given, only stock held at that location is
    counted; otherwise stock across all locations is summed.
    """
    sql = """
        SELECT COALESCE(SUM(s.qty * i.unit_price), 0) AS value
        FROM stock_levels s JOIN items i ON i.id = s.item_id
        """
    params: list = []
    if location_id is not None:
        sql += " WHERE s.location_id = ?"
        params.append(location_id)
    row = conn.execute(sql, params).fetchone()
    return float(row["value"])
