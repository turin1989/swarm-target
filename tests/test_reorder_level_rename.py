"""T049: item field reorder_point was renamed to reorder_level."""

import sqlite3

from inventory import db as db_module
from inventory.models import Item, ItemCreate, ItemUpdate, LowStockEntry


def test_models_expose_reorder_level_not_reorder_point():
    for model in (ItemCreate, ItemUpdate, Item, LowStockEntry):
        assert "reorder_level" in model.model_fields, model.__name__
        assert "reorder_point" not in model.model_fields, model.__name__


def test_create_item_accepts_reorder_level(client):
    r = client.post(
        "/items", json={"sku": "RL-1", "name": "Renamed", "reorder_level": 7}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_create_item_with_reorder_point_returns_422(client):
    r = client.post(
        "/items", json={"sku": "RP-1", "name": "Old Field", "reorder_point": 7}
    )
    assert r.status_code == 422


def test_update_item_accepts_reorder_level(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 9})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 9
    assert "reorder_point" not in r.json()


def test_update_item_with_reorder_point_returns_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 9})
    assert r.status_code == 422
    # the old field must not have leaked into the stored item
    stored = client.get(f"/items/{item['id']}").json()
    assert stored["reorder_level"] == item["reorder_level"]


def test_schema_column_is_renamed(tmp_path):
    path = str(tmp_path / "schema.db")
    db_module.init_db(path)
    conn = db_module.connect(path)
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

    conn = db_module.connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        assert "reorder_level" in columns
        assert "reorder_point" not in columns
        row = conn.execute(
            "SELECT reorder_level FROM items WHERE sku = 'OLD-1'"
        ).fetchone()
        assert row["reorder_level"] == 4
    finally:
        conn.close()


def test_low_stock_report_uses_reorder_level(client, loc_a):
    r = client.post(
        "/items",
        json={"sku": "LOW-RL", "name": "Low", "reorder_level": 5},
    )
    item_id = r.json()["id"]
    client.post(
        "/movements",
        json={
            "item_id": item_id,
            "kind": "receive",
            "qty": 2,
            "to_location_id": loc_a["id"],
        },
    )
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = [e for e in r.json() if e["item_id"] == item_id]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["reorder_level"] == 5
    assert "reorder_point" not in entry
    assert entry["shortfall"] == 3
