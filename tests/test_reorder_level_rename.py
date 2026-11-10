"""T049: item field reorder_point is renamed to reorder_level everywhere."""

import sqlite3

from inventory import db as db_module


def _item_columns(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return {r["name"] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
    finally:
        conn.close()


# --- API models expose reorder_level, not reorder_point -------------------


def test_create_item_accepts_reorder_level(client):
    r = client.post(
        "/items",
        json={"sku": "RL-1", "name": "Renamed", "reorder_level": 7},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_item_response_uses_reorder_level(client, item):
    body = client.get(f"/items/{item['id']}").json()
    assert body["reorder_level"] == 5
    assert "reorder_point" not in body


def test_update_item_accepts_reorder_level(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 9})
    assert r.status_code == 200, r.text
    assert r.json()["reorder_level"] == 9
    assert "reorder_point" not in r.json()


def test_bulk_create_accepts_reorder_level(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "RL-B1", "name": "Bulk", "reorder_level": 3}],
    )
    assert r.status_code == 201, r.text
    assert r.json()[0]["reorder_level"] == 3
    assert "reorder_point" not in r.json()[0]


def test_low_stock_entry_uses_reorder_level(client, loc_a):
    r = client.post(
        "/items", json={"sku": "RL-LOW", "name": "Low", "reorder_level": 5}
    )
    assert r.status_code == 201, r.text
    entries = client.get("/reports/low-stock").json()
    assert entries, entries
    entry = next(e for e in entries if e["sku"] == "RL-LOW")
    assert entry["reorder_level"] == 5
    assert "reorder_point" not in entry


# --- sending the old name is rejected with 422 -----------------------------


def test_create_item_with_reorder_point_is_422(client):
    r = client.post(
        "/items",
        json={"sku": "OLD-NAME-1", "name": "Old", "reorder_point": 5},
    )
    assert r.status_code == 422, r.text


def test_update_item_with_reorder_point_is_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 5})
    assert r.status_code == 422, r.text
    # the item is unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5


def test_bulk_create_with_reorder_point_is_422(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "OLD-NAME-2", "name": "Old", "reorder_point": 5}],
    )
    assert r.status_code == 422, r.text


# --- the database column is renamed ----------------------------------------


def test_new_database_has_reorder_level_column(tmp_path):
    path = str(tmp_path / "new.db")
    db_module.init_db(path)
    columns = _item_columns(path)
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
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        "INSERT INTO items (sku, name, reorder_point) VALUES ('OLD-1', 'Legacy', 4)"
    )
    conn.commit()
    conn.close()

    db_module.init_db(path)

    columns = _item_columns(path)
    assert "reorder_level" in columns
    assert "reorder_point" not in columns

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT reorder_level FROM items WHERE sku = 'OLD-1'"
        ).fetchone()
    finally:
        conn.close()
    assert row["reorder_level"] == 4
