"""Tests for the items.created_at timestamp (T020)."""

import re
from datetime import datetime, timezone

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _assert_valid_created_at(value):
    assert isinstance(value, str)
    assert ISO_Z.match(value), f"not ISO-8601 UTC with Z suffix: {value!r}"
    # must parse as a real datetime
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    # sanity: roughly "now" (within a day, to be robust against clock skew)
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 86400


def test_create_sets_created_at(client):
    r = client.post("/items", json={"sku": "TS-1", "name": "Timestamped"})
    assert r.status_code == 201
    _assert_valid_created_at(r.json()["created_at"])


def test_get_item_returns_created_at(client, item):
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    body = r.json()
    _assert_valid_created_at(body["created_at"])
    assert body["created_at"] == item["created_at"]


def test_list_items_returns_created_at(client, item):
    r = client.get("/items")
    assert r.status_code == 200
    rows = r.json()
    assert rows
    for row in rows:
        _assert_valid_created_at(row["created_at"])


def test_search_returns_created_at(client, item):
    r = client.get("/search", params={"q": item["sku"]})
    assert r.status_code == 200
    rows = r.json()
    assert rows
    for row in rows:
        _assert_valid_created_at(row["created_at"])


def test_put_response_includes_created_at(client, item):
    r = client.put(f"/items/{item['id']}", json={"name": "Renamed"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["created_at"] == item["created_at"]


def test_created_at_ignored_on_put(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"name": "Tampered", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]
    # and it persists unchanged
    r = client.get(f"/items/{item['id']}")
    assert r.json()["created_at"] == item["created_at"]


def test_created_at_ignored_on_create(client):
    r = client.post(
        "/items",
        json={"sku": "TS-2", "name": "ClientClock", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["created_at"] != "1999-01-01T00:00:00Z"
    _assert_valid_created_at(body["created_at"])
