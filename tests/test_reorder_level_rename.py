"""T049: item field reorder_point is renamed to reorder_level."""

import sqlite3

from inventory import db


def test_create_item_accepts_reorder_level(client):
    r = client.post(
        "/items",
        json={"sku": "RL-1", "name": "Renamed", "unit_price": 1.0, "reorder_level": 7},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_create_item_with_reorder_point_returns_422(client):
    r = client.post(
        "/items",
        json={"sku": "RP-1", "name": "Old Field", "reorder_point": 7},
    )
    assert r.status_code == 422


def test_update_item_accepts_reorder_level(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 9})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reorder_level"] == 9
    assert "reorder_point" not in body


def test_update_item_with_reorder_point_returns_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 9})
    assert r.status_code == 422
    # Value is unchanged.
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == item["reorder_level"]


def test_item_response_exposes_reorder_level_only(client, item):
    body = client.get(f"/items/{item['id']}").json()
    assert "reorder_level" in body
    assert "reorder_point" not in body


def test_low_stock_entry_exposes_reorder_level_only(client, item, loc_a):
    # Item has reorder_level=5 and no stock, so it is low on stock.
    r = client.get("/reports/low-stock")
    assert r.status_code == 200, r.text
    entries = r.json()
    assert entries, "expected at least one low stock entry"
    entry = entries[0]
    assert entry["reorder_level"] == 5
    assert "reorder_point" not in entry


def test_schema_column_is_renamed(tmp_path):
    path = str(tmp_path / "schema.db")
    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
    finally:
        conn.close()
    assert "reorder_level" in columns
    assert "reorder_point" not in columns


def test_init_db_migrates_legacy_reorder_point_column(tmp_path):
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
        conn.execute(
            "INSERT INTO items (sku, name, reorder_point) VALUES ('L-1', 'Legacy', 4)"
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(path)

    conn = sqlite3.connect(path)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
        (value,) = conn.execute(
            "SELECT reorder_level FROM items WHERE sku = 'L-1'"
        ).fetchone()
    finally:
        conn.close()
    assert "reorder_level" in columns
    assert "reorder_point" not in columns
    assert value == 4
