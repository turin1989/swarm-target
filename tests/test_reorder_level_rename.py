"""T049: item field reorder_point renamed to reorder_level."""

import sqlite3

# --- models expose reorder_level ------------------------------------------------


def test_item_create_model_exposes_reorder_level_not_reorder_point():
    from inventory.models import ItemCreate

    m = ItemCreate(sku="X", name="x", reorder_level=3)
    assert m.reorder_level == 3
    assert "reorder_level" in ItemCreate.model_fields
    assert "reorder_point" not in ItemCreate.model_fields


def test_item_update_model_exposes_reorder_level_not_reorder_point():
    from inventory.models import ItemUpdate

    m = ItemUpdate(reorder_level=4)
    assert m.reorder_level == 4
    assert "reorder_level" in ItemUpdate.model_fields
    assert "reorder_point" not in ItemUpdate.model_fields


def test_item_model_exposes_reorder_level_not_reorder_point():
    from inventory.models import Item

    assert "reorder_level" in Item.model_fields
    assert "reorder_point" not in Item.model_fields


def test_low_stock_entry_model_exposes_reorder_level_not_reorder_point():
    from inventory.models import LowStockEntry

    e = LowStockEntry(
        item_id=1, sku="X", name="x", total_qty=1, reorder_level=5, shortfall=4
    )
    assert e.reorder_level == 5
    assert "reorder_level" in LowStockEntry.model_fields
    assert "reorder_point" not in LowStockEntry.model_fields


# --- API responses use the new name ----------------------------------------------


def test_create_item_accepts_and_returns_reorder_level(client):
    r = client.post(
        "/items", json={"sku": "RL-1", "name": "New Name", "reorder_level": 7}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_get_item_returns_reorder_level(client, item):
    body = client.get(f"/items/{item['id']}").json()
    assert body["reorder_level"] == 5
    assert "reorder_point" not in body


def test_low_stock_report_uses_reorder_level(client, loc_a):
    r = client.post(
        "/items", json={"sku": "RL-LOW", "name": "Low", "reorder_level": 5}
    )
    assert r.status_code == 201
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["RL-LOW"]
    assert entries[0]["reorder_level"] == 5
    assert "reorder_point" not in entries[0]


# --- sending the old name is a 422 ------------------------------------------------


def test_create_item_with_reorder_point_422(client):
    r = client.post(
        "/items", json={"sku": "OLD-1", "name": "Old", "reorder_point": 5}
    )
    assert r.status_code == 422


def test_update_item_with_reorder_point_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 9})
    assert r.status_code == 422
    # item unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5


def test_bulk_create_with_reorder_point_422(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "BK-1", "name": "ok", "reorder_level": 1},
            {"sku": "BK-2", "name": "bad", "reorder_point": 2},
        ],
    )
    assert r.status_code == 422
    # nothing created
    assert client.get("/items").json()["total"] == 0


def test_other_unknown_fields_still_ignored(client, item):
    # Only reorder_point is rejected; unrelated extras keep being ignored.
    r = client.post(
        "/items", json={"sku": "EXTRA", "name": "Extra", "created_at": "1999-01-01T00:00:00Z"}
    )
    assert r.status_code == 201
    r = client.put(f"/items/{item['id']}", json={"name": "n", "whatever": 1})
    assert r.status_code == 200


# --- schema column renamed --------------------------------------------------------


def test_items_table_column_is_reorder_level(client, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info('items')").fetchall()}
    finally:
        conn.close()
    assert "reorder_level" in cols
    assert "reorder_point" not in cols


def test_migration_renames_reorder_point_column_in_legacy_db(tmp_path):
    from inventory import db as dbmod

    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            unit_price REAL NOT NULL DEFAULT 0,
            reorder_point INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            barcode TEXT UNIQUE
        );
        INSERT INTO items (sku, name, reorder_point) VALUES ('S1', 'Thing', 9);
        """
    )
    conn.commit()
    conn.close()

    dbmod.init_db(path)

    conn = sqlite3.connect(path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info('items')").fetchall()}
        value = conn.execute("SELECT reorder_level FROM items WHERE sku = 'S1'").fetchone()[0]
    finally:
        conn.close()
    assert "reorder_level" in cols
    assert "reorder_point" not in cols
    assert value == 9
