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
        rows = conn.execute("SELECT version FROM schema_version").fetchall()
    finally:
        conn.close()
    assert rows == [(1,)]


def test_init_db_adds_created_at_to_legacy_items_table(tmp_path):
    """Databases predating items.created_at get the column added and backfilled."""
    path = str(tmp_path / "legacy.db")
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
                reorder_point INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute("INSERT INTO items (sku, name) VALUES ('OLD-1', 'Old item')")
        conn.commit()
    finally:
        conn.close()

    db.init_db(path)

    conn = sqlite3.connect(path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
        assert "created_at" in columns
        (created_at,) = conn.execute(
            "SELECT created_at FROM items WHERE sku = 'OLD-1'"
        ).fetchone()
    finally:
        conn.close()
    import re

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at)


def test_init_db_adds_created_at_to_legacy_movements_table(tmp_path):
    """Databases predating movements.created_at get the column added and backfilled."""
    path = str(tmp_path / "legacy_movements.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                qty INTEGER NOT NULL,
                from_location_id INTEGER,
                to_location_id INTEGER,
                note TEXT NOT NULL DEFAULT '',
                reference TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO movements (item_id, kind, qty, to_location_id) VALUES (1, 'receive', 5, 1)"
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(path)

    conn = sqlite3.connect(path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(movements)")}
        assert "created_at" in columns
        (created_at,) = conn.execute(
            "SELECT created_at FROM movements WHERE id = 1"
        ).fetchone()
    finally:
        conn.close()
    import re

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at)


def test_init_db_is_idempotent(tmp_path):
    path = str(tmp_path / "twice.db")
    db.init_db(path)
    db.init_db(path)
    assert db.get_schema_version(path) == 1
    conn = sqlite3.connect(path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    finally:
        conn.close()
    assert count == 1
