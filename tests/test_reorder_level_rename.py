"""T049: item field reorder_point is renamed to reorder_level."""

import sqlite3

from inventory.main import create_app


def test_create_item_exposes_reorder_level_not_reorder_point(client):
    r = client.post(
        "/items", json={"sku": "RL-1", "name": "Renamed", "reorder_level": 7}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_get_item_exposes_reorder_level_not_reorder_point(client, item):
    body = client.get(f"/items/{item['id']}").json()
    assert body["reorder_level"] == 5
    assert "reorder_point" not in body


def test_create_item_with_reorder_point_returns_422(client):
    r = client.post(
        "/items", json={"sku": "OLD-1", "name": "Old", "reorder_point": 3}
    )
    assert r.status_code == 422


def test_update_item_with_reorder_point_returns_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 3})
    assert r.status_code == 422
    # item unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5


def test_low_stock_entry_exposes_reorder_level_not_reorder_point(client, loc_a):
    client.post("/items", json={"sku": "LOW-1", "name": "Low", "reorder_level": 4})
    entries = client.get("/reports/low-stock").json()
    assert len(entries) == 1
    assert entries[0]["reorder_level"] == 4
    assert "reorder_point" not in entries[0]


def test_items_column_renamed_in_schema(tmp_path):
    db_path = str(tmp_path / "schema.db")
    create_app(db_path)
    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    finally:
        conn.close()
    assert "reorder_level" in columns
    assert "reorder_point" not in columns
