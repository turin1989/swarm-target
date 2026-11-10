"""Tests for duplicate location codes (task T007)."""

import sqlite3

from inventory.db import init_db


def test_duplicate_location_code_returns_409(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text

    r2 = client.post("/locations", json={"code": "WH-A", "name": "Another warehouse"})
    assert r2.status_code == 409, r2.text


def test_duplicate_location_code_detail_mentions_code(client):
    r = client.post("/locations", json={"code": "WH-DUP", "name": "Warehouse"})
    assert r.status_code == 201, r.text

    r2 = client.post("/locations", json={"code": "WH-DUP", "name": "Other"})
    assert r2.status_code == 409, r2.text
    # The HTTPException detail is surfaced as error.message in this app's
    # uniform error shape; it must mention the duplicate code.
    body = r2.json()
    detail = body.get("detail") or body["error"]["message"]
    assert "WH-DUP" in detail
    assert body["error"]["code"] == "conflict"


def test_duplicate_code_does_not_create_second_location(client):
    client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    client.post("/locations", json={"code": "WH-A", "name": "Duplicate"})

    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_distinct_codes_still_accepted(client):
    r1 = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    r2 = client.post("/locations", json={"code": "WH-B", "name": "Warehouse B"})
    assert r1.status_code == 201
    assert r2.status_code == 201


def test_locations_code_column_is_unique_in_schema(tmp_path):
    """Inserting a duplicate code directly into SQLite must fail."""
    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'A')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'B')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("locations.code is not UNIQUE in the schema")
    finally:
        conn.close()


def test_migration_adds_unique_index_to_legacy_database(tmp_path):
    """Databases created before the UNIQUE constraint get a unique index."""
    db_path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            unit_price REAL NOT NULL DEFAULT 0,
            reorder_point INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL
        );
        CREATE TABLE schema_version (version INTEGER NOT NULL);
        """
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'A')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'B')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate code accepted after migration")
    finally:
        conn.close()
