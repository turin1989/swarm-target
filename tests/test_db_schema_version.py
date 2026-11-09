import sqlite3

import pytest

from inventory import db


def test_init_db_records_version_1(tmp_path):
    path = str(tmp_path / "fresh.db")
    db.init_db(path)
    assert db.get_schema_version(path) == 1


def test_schema_version_table_has_single_row(tmp_path):
    path = str(tmp_path / "fresh.db")
    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    finally:
        conn.close()
    assert count == 1


def _create_pre_barcode_db(path: str) -> None:
    """Create a database whose items table predates the barcode column."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                unit_price REAL NOT NULL DEFAULT 0,
                reorder_level INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """
        )
        conn.execute("INSERT INTO items (sku, name) VALUES ('OLD-1', 'Old item')")
        conn.commit()
    finally:
        conn.close()


def test_init_db_migrates_barcode_column_onto_old_items_table(tmp_path):
    path = str(tmp_path / "old.db")
    _create_pre_barcode_db(path)
    db.init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        assert "barcode" in cols
        row = conn.execute("SELECT barcode FROM items WHERE sku = 'OLD-1'").fetchone()
        assert row["barcode"] is None
    finally:
        conn.close()


def test_migrated_barcode_column_enforces_uniqueness(tmp_path):
    path = str(tmp_path / "old.db")
    _create_pre_barcode_db(path)
    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("INSERT INTO items (sku, name, barcode) VALUES ('NEW-1', 'One', 'BC-1')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO items (sku, name, barcode) VALUES ('NEW-2', 'Two', 'BC-1')"
            )
        # multiple NULL barcodes remain allowed
        conn.execute("INSERT INTO items (sku, name) VALUES ('NEW-3', 'Three')")
        conn.execute("INSERT INTO items (sku, name) VALUES ('NEW-4', 'Four')")
    finally:
        conn.close()


def test_init_db_is_idempotent(tmp_path):
    path = str(tmp_path / "fresh.db")
    db.init_db(path)
    db.init_db(path)
    assert db.get_schema_version(path) == 1
    conn = sqlite3.connect(path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    finally:
        conn.close()
    assert count == 1
