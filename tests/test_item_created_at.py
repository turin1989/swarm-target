"""Tests for T020: items carry a server-assigned created_at timestamp."""

import re
import sqlite3
from datetime import datetime, timezone

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def assert_valid_created_at(value):
    assert isinstance(value, str)
    assert ISO_Z.fullmatch(value), f"not ISO-8601 UTC with Z suffix: {value!r}"
    # Parses as a real timestamp and is UTC.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


# --- set on insert and persisted in the DB -----------------------------------


def test_create_sets_created_at(client):
    r = client.post("/items", json={"sku": "TS-1", "name": "Timestamped"})
    assert r.status_code == 201, r.text
    assert_valid_created_at(r.json()["created_at"])


def test_created_at_close_to_now(client):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    r = client.post("/items", json={"sku": "TS-NOW", "name": "Now"})
    after = datetime.now(timezone.utc).replace(microsecond=0)
    created = datetime.fromisoformat(r.json()["created_at"].replace("Z", "+00:00"))
    assert before <= created <= after


def test_created_at_column_persisted(client, item, tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    try:
        columns = [r["name"] for r in conn.execute("PRAGMA table_info(items)")]
        assert "created_at" in columns
        row = conn.execute(
            "SELECT created_at FROM items WHERE id = ?", (item["id"],)
        ).fetchone()
        assert row["created_at"] == item["created_at"]
        assert_valid_created_at(row["created_at"])
    finally:
        conn.close()


# --- returned by every endpoint that returns an Item ---------------------------


def test_get_item_returns_created_at(client, item):
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]


def test_get_item_by_sku_returns_created_at(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]


def test_list_items_returns_created_at(client, item):
    r = client.get("/items")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    for it in items:
        assert_valid_created_at(it["created_at"])


def test_put_response_includes_created_at(client, item):
    r = client.put(f"/items/{item['id']}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]


def test_bulk_create_sets_created_at(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "BULK-TS-1", "name": "One"},
            {"sku": "BULK-TS-2", "name": "Two"},
        ],
    )
    assert r.status_code == 201, r.text
    for it in r.json():
        assert_valid_created_at(it["created_at"])


def test_search_returns_created_at(client, item):
    r = client.get("/search", params={"q": "Widget"})
    assert r.status_code == 200
    results = r.json()
    assert results
    for it in results:
        assert_valid_created_at(it["created_at"])


# --- clients cannot set or change created_at ----------------------------------


def test_put_ignores_created_at(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"name": "Tampered", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Tampered"
    assert body["created_at"] == item["created_at"]
    # Still unchanged on a fresh read.
    assert client.get(f"/items/{item['id']}").json()["created_at"] == item["created_at"]


def test_put_only_created_at_changes_nothing(client, item):
    r = client.put(f"/items/{item['id']}", json={"created_at": "1999-01-01T00:00:00Z"})
    assert r.status_code == 200, r.text
    assert r.json()["created_at"] == item["created_at"]


def test_post_cannot_set_created_at(client):
    r = client.post(
        "/items",
        json={"sku": "TS-POST", "name": "X", "created_at": "1999-01-01T00:00:00Z"},
    )
    # Either rejected outright or ignored — but never honoured.
    if r.status_code == 201:
        assert r.json()["created_at"] != "1999-01-01T00:00:00Z"
    else:
        assert r.status_code == 422
