"""T049: items expose reorder_level instead of reorder_point."""

import sqlite3

from inventory.db import connect, init_db


def test_create_item_exposes_reorder_level_not_reorder_point(client):
    r = client.post(
        "/items", json={"sku": "RL-1", "name": "Renamed", "reorder_level": 7}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_item_responses_use_reorder_level(client, item):
    for res in (
        client.get(f"/items/{item['id']}"),
        client.get(f"/items/by-sku/{item['sku']}"),
    ):
        assert res.status_code == 200
        assert res.json()["reorder_level"] == 5
        assert "reorder_point" not in res.json()


def test_create_item_with_reorder_point_is_422(client):
    r = client.post(
        "/items", json={"sku": "RL-2", "name": "Legacy", "reorder_point": 3}
    )
    assert r.status_code == 422


def test_update_item_with_reorder_point_is_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 3})
    assert r.status_code == 422


def test_low_stock_entry_exposes_reorder_level(client, item):
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert entries, "item with zero stock and reorder_level 5 should be low"
    entry = next(e for e in entries if e["item_id"] == item["id"])
    assert entry["reorder_level"] == 5
    assert "reorder_point" not in entry


def test_items_table_column_is_renamed(tmp_path):
    path = str(tmp_path / "schema.db")
    init_db(path)
    conn = connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    finally:
        conn.close()
    assert "reorder_level" in columns
    assert "reorder_point" not in columns


def test_existing_db_column_is_migrated(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(
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
        );
        INSERT INTO items (sku, name, reorder_point) VALUES ('OLD-1', 'Old', 9);
        """
    )
    old.commit()
    old.close()

    init_db(path)

    conn = connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        row = conn.execute("SELECT reorder_level FROM items WHERE sku = 'OLD-1'").fetchone()
    finally:
        conn.close()
    assert "reorder_level" in columns
    assert "reorder_point" not in columns
    assert row["reorder_level"] == 9
