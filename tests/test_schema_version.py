import sqlite3

from inventory import db


def test_fresh_db_records_version_1(tmp_path):
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


def test_init_db_is_idempotent(tmp_path):
    path = str(tmp_path / "twice.db")
    db.init_db(path)
    db.init_db(path)  # must not raise
    assert db.get_schema_version(path) == 1
    conn = sqlite3.connect(path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    finally:
        conn.close()
    assert count == 1


def test_init_db_migrates_existing_db_without_version(tmp_path):
    # Simulate a pre-versioning database: tables exist, no schema_version table.
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE items ("
            "id INTEGER PRIMARY KEY, "
            "sku TEXT NOT NULL UNIQUE, "
            "name TEXT NOT NULL, "
            "description TEXT NOT NULL DEFAULT '', "
            "unit_price REAL NOT NULL DEFAULT 0, "
            "reorder_point INTEGER NOT NULL DEFAULT 0, "
            "active INTEGER NOT NULL DEFAULT 1)"
        )
        conn.commit()
    finally:
        conn.close()
    db.init_db(path)
    assert db.get_schema_version(path) == 1
