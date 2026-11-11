import sqlite3

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


def test_init_db_is_idempotent(tmp_path):
    path = str(tmp_path / "fresh.db")
    db.init_db(path)
    db.init_db(path)  # must not fail
    assert db.get_schema_version(path) == 1
    conn = sqlite3.connect(path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    finally:
        conn.close()
    assert count == 1
