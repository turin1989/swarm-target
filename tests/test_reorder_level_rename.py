"""T049: item field reorder_point is renamed to reorder_level."""

import sqlite3

from inventory import db


# --- API exposes reorder_level ---------------------------------------------------


def test_create_item_returns_reorder_level_not_reorder_point(client):
    r = client.post("/items", json={"sku": "RL-1", "name": "Renamed", "reorder_level": 3})
    assert r.status_code == 201
    body = r.json()
    assert body["reorder_level"] == 3
    assert "reorder_point" not in body


def test_get_item_returns_reorder_level_not_reorder_point(client, item):
    body = client.get(f"/items/{item['id']}").json()
    assert body["reorder_level"] == 5
    assert "reorder_point" not in body


def test_update_item_accepts_reorder_level(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 11})
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_level"] == 11
    assert "reorder_point" not in body


def test_low_stock_entry_exposes_reorder_level_not_reorder_point(client, loc_a):
    client.post("/items", json={"sku": "RL-LOW", "name": "Low", "reorder_level": 5})
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    assert entries[0]["reorder_level"] == 5
    assert "reorder_point" not in entries[0]


# --- sending reorder_point returns 422 -------------------------------------------


def test_create_item_with_reorder_point_returns_422(client):
    r = client.post("/items", json={"sku": "OLD-1", "name": "Old", "reorder_point": 3})
    assert r.status_code == 422


def test_update_item_with_reorder_point_returns_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 3})
    assert r.status_code == 422
    # The stored value is untouched.
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5


# --- the column is renamed in the schema -----------------------------------------


def test_items_table_has_reorder_level_column(tmp_path):
    path = str(tmp_path / "schema.db")
    db.init_db(path)
    conn = db.connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    finally:
        conn.close()
    assert "reorder_level" in columns
    assert "reorder_point" not in columns


def test_init_db_renames_legacy_reorder_point_column(tmp_path):
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            unit_price REAL NOT NULL DEFAULT 0,
            reorder_point INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    conn.execute("INSERT INTO items (sku, name, reorder_point) VALUES ('L-1', 'Legacy', 9)")
    conn.commit()
    conn.close()

    db.init_db(path)

    conn = db.connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        row = conn.execute("SELECT reorder_level FROM items WHERE sku = 'L-1'").fetchone()
    finally:
        conn.close()
    assert "reorder_level" in columns
    assert "reorder_point" not in columns
    assert row["reorder_level"] == 9
