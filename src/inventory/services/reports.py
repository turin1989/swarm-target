"""Reporting queries."""

import sqlite3
from typing import Optional

from inventory.models import LowStockEntry


def low_stock(
    conn: sqlite3.Connection, location_id: Optional[int] = None
) -> list[LowStockEntry]:
    """Active items whose total stock is at or below their reorder level.

    By default stock is summed across all locations; when ``location_id`` is
    given, only stock held at that location counts towards ``total_qty``.
    """
    params: list = []
    join_filter = ""
    if location_id is not None:
        join_filter = " AND s.location_id = ?"
        params.append(location_id)
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
        params,
    ).fetchall()
    return [
        LowStockEntry(
            **dict(r),
            shortfall=max(0, r["reorder_level"] - r["total_qty"]),
        )
        for r in rows
    ]


_SUMMARY_KINDS = ("receive", "ship", "transfer")


def movements_summary(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """Per-kind movement counts and total quantities.

    Every kind in ``_SUMMARY_KINDS`` is always present; kinds with no
    movements report zero count and zero qty.
    """
    summary: dict[str, dict[str, int]] = {
        kind: {"count": 0, "qty": 0} for kind in _SUMMARY_KINDS
    }
    rows = conn.execute(
        """
        SELECT kind, COUNT(*) AS count, COALESCE(SUM(qty), 0) AS qty
        FROM movements
        GROUP BY kind
        """
    ).fetchall()
    for r in rows:
        if r["kind"] in summary:
            summary[r["kind"]] = {"count": r["count"], "qty": r["qty"]}
    return summary


def inventory_value(conn: sqlite3.Connection, location_id: int | None = None) -> float:
    """Total value of stock on hand (sum of qty * unit_price).

    If ``location_id`` is given, only stock held at that location is counted.
    """
    sql = """
        SELECT COALESCE(SUM(s.qty * i.unit_price), 0) AS value
        FROM stock_levels s JOIN items i ON i.id = s.item_id
        """
    params: tuple = ()
    if location_id is not None:
        sql += " WHERE s.location_id = ?"
        params = (location_id,)
    row = conn.execute(sql, params).fetchone()
    return float(row["value"])


def stats(conn: sqlite3.Connection) -> dict:
    """Entity counts plus the total number of stock units on hand."""
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
    return {
        "items": row["items"],
        "active_items": row["active_items"],
        "locations": row["locations"],
        "movements": row["movements"],
        "total_units": row["total_units"],
    }
