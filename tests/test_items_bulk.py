"""Tests for POST /items/bulk."""


def _bulk_payload():
    return [
        {"sku": "BULK-1", "name": "Bulk One", "unit_price": 1.0, "reorder_level": 1},
        {"sku": "BULK-2", "name": "Bulk Two", "unit_price": 2.0},
        {"sku": "BULK-3", "name": "Bulk Three"},
    ]


def test_bulk_create_returns_201_with_created_items(client):
    r = client.post("/items/bulk", json=_bulk_payload())
    assert r.status_code == 201, r.text
    items = r.json()
    assert [i["sku"] for i in items] == ["BULK-1", "BULK-2", "BULK-3"]
    assert [i["name"] for i in items] == ["Bulk One", "Bulk Two", "Bulk Three"]
    for i in items:
        assert isinstance(i["id"], int)
        assert i["active"] is True
    # items are persisted and retrievable
    for i in items:
        got = client.get(f"/items/{i['id']}")
        assert got.status_code == 200
        assert got.json()["sku"] == i["sku"]


def test_bulk_create_conflict_with_existing_sku_creates_nothing(client, item):
    before = client.get("/items").json()["total"]
    payload = [
        {"sku": "NEW-1", "name": "New One"},
        {"sku": item["sku"], "name": "Duplicate"},  # already exists -> conflict
        {"sku": "NEW-2", "name": "New Two"},
    ]
    r = client.post("/items/bulk", json=payload)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "conflict"
    # atomic: nothing was created
    after = client.get("/items").json()["total"]
    assert after == before
    assert client.get("/items/by-sku/NEW-1").status_code == 404
    assert client.get("/items/by-sku/NEW-2").status_code == 404


def test_bulk_create_conflict_with_duplicate_sku_within_payload(client):
    payload = [
        {"sku": "DUP-1", "name": "First"},
        {"sku": "DUP-1", "name": "Second"},
    ]
    r = client.post("/items/bulk", json=payload)
    assert r.status_code == 409, r.text
    # atomic: not even the first one was created
    assert client.get("/items/by-sku/DUP-1").status_code == 404


def test_bulk_create_empty_list_returns_422(client):
    r = client.post("/items/bulk", json=[])
    assert r.status_code == 422, r.text
    assert client.get("/items").json()["total"] == 0


def test_bulk_create_invalid_entry_returns_422_and_creates_nothing(client):
    payload = [
        {"sku": "OK-1", "name": "Fine"},
        {"sku": "", "name": "Bad sku"},
    ]
    r = client.post("/items/bulk", json=payload)
    assert r.status_code == 422, r.text
    assert client.get("/items").json()["total"] == 0
