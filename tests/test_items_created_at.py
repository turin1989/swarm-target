"""T020: items carry a server-managed created_at timestamp."""

import re
from datetime import datetime, timezone

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _parse(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# --- set on insert, ISO-8601 UTC ------------------------------------------------


def test_create_item_sets_created_at_iso8601_utc(client):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    r = client.post("/items", json={"sku": "TS-1", "name": "Timestamped"})
    after = datetime.now(timezone.utc)
    assert r.status_code == 201
    created_at = r.json()["created_at"]
    assert ISO_Z.match(created_at), created_at
    assert before <= _parse(created_at) <= after


def test_created_at_persisted_in_db_column(client, item, tmp_path):
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        assert "created_at" in cols
        row = conn.execute(
            "SELECT created_at FROM items WHERE id = ?", (item["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert ISO_Z.match(row["created_at"])
    assert row["created_at"] == item["created_at"]


# --- returned by every endpoint that returns an Item -----------------------------


def test_created_at_returned_on_get(client, item):
    body = client.get(f"/items/{item['id']}").json()
    assert body["created_at"] == item["created_at"]
    assert ISO_Z.match(body["created_at"])


def test_created_at_returned_on_list(client, item):
    body = client.get("/items").json()
    assert body["items"][0]["created_at"] == item["created_at"]


def test_created_at_returned_on_put(client, item):
    body = client.put(f"/items/{item['id']}", json={"name": "Renamed"}).json()
    assert body["created_at"] == item["created_at"]


def test_created_at_returned_on_search(client, item):
    results = client.get("/search", params={"q": "widget"}).json()
    assert [i["created_at"] for i in results] == [item["created_at"]]


# --- clients cannot set or change it ---------------------------------------------


def test_created_at_rejected_on_create(client):
    r = client.post(
        "/items",
        json={"sku": "TS-2", "name": "x", "created_at": "1999-01-01T00:00:00Z"},
    )
    # ItemCreate forbids unknown/server-managed fields entirely.
    assert r.status_code == 422
    assert client.get("/items").json()["items"] == []


def test_created_at_ignored_on_put(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]
    assert client.get(f"/items/{item['id']}").json()["created_at"] == item["created_at"]


def test_created_at_ignored_on_put_alongside_real_updates(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"name": "Renamed", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["created_at"] == item["created_at"]
    body = client.get(f"/items/{item['id']}").json()
    assert body["name"] == "Renamed"
    assert body["created_at"] == item["created_at"]


def test_update_does_not_touch_created_at(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 9.99, "active": False})
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]


# --- migration of pre-created_at databases ---------------------------------------


def test_legacy_db_without_created_at_is_migrated_and_backfilled(tmp_path):
    import sqlite3

    from inventory import db as db_module

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
            reorder_level INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            barcode TEXT UNIQUE
        )
        """
    )
    conn.execute("INSERT INTO items (sku, name) VALUES ('OLD-1', 'Old')")
    conn.commit()
    conn.close()

    db_module.init_db(path)
    conn = db_module.connect(path)
    try:
        row = conn.execute(
            "SELECT created_at FROM items WHERE sku = 'OLD-1'"
        ).fetchone()
    finally:
        conn.close()
    assert row["created_at"] is not None
    assert ISO_Z.match(row["created_at"])
