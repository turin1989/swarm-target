"""Tests for T020: items carry a server-managed created_at timestamp."""

import re
import sqlite3
from datetime import datetime, timezone

ISO_UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def assert_valid_created_at(value):
    assert isinstance(value, str)
    assert ISO_UTC_Z.match(value), f"created_at {value!r} is not ISO-8601 UTC with Z"
    # Parses as a real timestamp.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_create_item_returns_created_at(client):
    r = client.post("/items", json={"sku": "TS-1", "name": "Thing"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "created_at" in body
    assert_valid_created_at(body["created_at"])
    # Roughly "now".
    parsed = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 60


def test_created_at_persisted_in_items_table(client, item, tmp_path):
    conn = sqlite3.connect(tmp_path / "test.db")
    conn.row_factory = sqlite3.Row
    columns = [r["name"] for r in conn.execute("PRAGMA table_info(items)").fetchall()]
    assert "created_at" in columns
    row = conn.execute(
        "SELECT created_at FROM items WHERE id = ?", (item["id"],)
    ).fetchone()
    conn.close()
    assert_valid_created_at(row["created_at"])
    assert row["created_at"] == item["created_at"]


def test_get_item_returns_created_at(client, item):
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]
    assert_valid_created_at(r.json()["created_at"])


def test_get_item_by_sku_returns_created_at(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]


def test_list_items_returns_created_at(client, item):
    r = client.get("/items")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    for entry in items:
        assert_valid_created_at(entry["created_at"])


def test_search_returns_created_at(client, item):
    r = client.get("/search", params={"q": "Widget"})
    assert r.status_code == 200
    results = r.json()
    assert results
    for entry in results:
        assert_valid_created_at(entry["created_at"])


def test_bulk_create_returns_created_at(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "B-1", "name": "One"}, {"sku": "B-2", "name": "Two"}],
    )
    assert r.status_code == 201, r.text
    for entry in r.json():
        assert_valid_created_at(entry["created_at"])


def test_put_cannot_change_created_at(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"name": "Renamed", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed"
    # Client-supplied created_at is ignored; the original value is kept.
    assert body["created_at"] == item["created_at"]


def test_put_created_at_only_is_ignored(client, item):
    r = client.put(f"/items/{item['id']}", json={"created_at": "1999-01-01T00:00:00Z"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_at"] == item["created_at"]
    assert body["name"] == item["name"]


def test_put_without_created_at_preserves_it(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 9.99})
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]


def test_post_cannot_set_created_at(client):
    r = client.post(
        "/items",
        json={"sku": "TS-2", "name": "Thing", "created_at": "1999-01-01T00:00:00Z"},
    )
    # Unknown/extra fields on create are rejected outright.
    assert r.status_code == 422
