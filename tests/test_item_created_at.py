"""Items carry a server-managed created_at timestamp (T020)."""

import re
import sqlite3

from inventory import db as db_module

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _create(client, sku="TS-1", **extra):
    r = client.post("/items", json={"sku": sku, "name": "Timestamped", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_item_sets_created_at_iso_utc(client):
    body = _create(client)
    assert "created_at" in body
    assert ISO_UTC.match(body["created_at"]), body["created_at"]


def test_created_at_returned_by_get_item(client):
    created = _create(client)
    r = client.get(f"/items/{created['id']}")
    assert r.status_code == 200
    assert r.json()["created_at"] == created["created_at"]


def test_created_at_returned_by_get_item_by_sku(client):
    created = _create(client)
    r = client.get(f"/items/by-sku/{created['sku']}")
    assert r.status_code == 200
    assert r.json()["created_at"] == created["created_at"]


def test_created_at_returned_by_list_items(client):
    created = _create(client)
    r = client.get("/items")
    assert r.status_code == 200
    rows = r.json()
    assert rows and rows[0]["created_at"] == created["created_at"]


def test_created_at_returned_by_bulk_create(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "B-1", "name": "One"}, {"sku": "B-2", "name": "Two"}],
    )
    assert r.status_code == 201, r.text
    for row in r.json():
        assert ISO_UTC.match(row["created_at"]), row["created_at"]


def test_created_at_returned_by_search(client):
    created = _create(client)
    r = client.get("/search", params={"q": "Timestamped"})
    assert r.status_code == 200
    rows = r.json()
    assert rows and rows[0]["created_at"] == created["created_at"]


def test_created_at_cannot_be_set_by_client_on_create(client):
    body = _create(client, created_at="1999-01-01T00:00:00Z")
    assert body["created_at"] != "1999-01-01T00:00:00Z"
    assert ISO_UTC.match(body["created_at"])


def test_created_at_ignored_on_put(client):
    created = _create(client)
    r = client.put(
        f"/items/{created['id']}",
        json={"name": "Renamed", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["created_at"] == created["created_at"]
    # Unchanged on subsequent reads too.
    r = client.get(f"/items/{created['id']}")
    assert r.json()["created_at"] == created["created_at"]


def test_init_db_backfills_created_at_for_legacy_databases(tmp_path):
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
    conn.execute("INSERT INTO items (sku, name) VALUES ('OLD-1', 'Legacy')")
    conn.commit()
    conn.close()

    db_module.init_db(path)

    conn = db_module.connect(path)
    try:
        row = conn.execute("SELECT created_at FROM items WHERE sku = 'OLD-1'").fetchone()
        assert row["created_at"] is not None
        assert ISO_UTC.match(row["created_at"]), row["created_at"]
    finally:
        conn.close()
