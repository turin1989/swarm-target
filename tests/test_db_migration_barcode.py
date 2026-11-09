"""Tests for the legacy-database migration that adds the items.barcode column."""

import sqlite3

from inventory import db

LEGACY_ITEMS_SCHEMA = """
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unit_price REAL NOT NULL DEFAULT 0,
    reorder_point INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT ''
);
"""


def _make_legacy_db(path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(LEGACY_ITEMS_SCHEMA)
        conn.execute(
            "INSERT INTO items (sku, name) VALUES (?, ?)", ("LEGACY-1", "Old item")
        )
        conn.commit()
    finally:
        conn.close()


def test_init_db_adds_barcode_column_to_legacy_db(tmp_path):
    path = str(tmp_path / "legacy.db")
    _make_legacy_db(path)

    db.init_db(path)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        assert "barcode" in columns
        # Pre-existing rows get a NULL barcode.
        row = conn.execute("SELECT barcode FROM items WHERE sku = 'LEGACY-1'").fetchone()
        assert row["barcode"] is None
    finally:
        conn.close()


def test_migrated_barcode_column_is_unique_but_allows_nulls(tmp_path):
    path = str(tmp_path / "legacy.db")
    _make_legacy_db(path)

    db.init_db(path)

    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO items (sku, name, barcode) VALUES (?, ?, ?)",
            ("NEW-1", "New item", "BC-1"),
        )
        # Duplicate non-null barcode must be rejected.
        try:
            conn.execute(
                "INSERT INTO items (sku, name, barcode) VALUES (?, ?, ?)",
                ("NEW-2", "Another", "BC-1"),
            )
        except sqlite3.IntegrityError as exc:
            assert "barcode" in str(exc)
        else:
            raise AssertionError("duplicate barcode was not rejected")
        # Multiple NULL barcodes are fine.
        conn.execute("INSERT INTO items (sku, name) VALUES (?, ?)", ("NEW-3", "Third"))
        conn.commit()
    finally:
        conn.close()
