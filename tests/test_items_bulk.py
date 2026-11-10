"""Tests for POST /items/bulk (T022)."""


def _payload(*skus):
    return [
        {"sku": sku, "name": f"Item {sku}", "unit_price": 1.0, "reorder_point": 2}
        for sku in skus
    ]


def test_bulk_create_returns_201_with_created_items(client):
    r = client.post("/items/bulk", json=_payload("BULK-1", "BULK-2", "BULK-3"))
    assert r.status_code == 201, r.text
    items = r.json()
    assert isinstance(items, list)
    assert [i["sku"] for i in items] == ["BULK-1", "BULK-2", "BULK-3"]
    for i in items:
        assert i["id"] > 0
        assert i["active"] is True
        assert i["created_at"]

    # items are persisted and retrievable individually
    for i in items:
        got = client.get(f"/items/{i['id']}")
        assert got.status_code == 200
        assert got.json()["sku"] == i["sku"]


def test_bulk_create_conflict_with_existing_sku_creates_nothing(client, item):
    before = client.get("/items").json()["total"]
    r = client.post("/items/bulk", json=_payload("NEW-1", item["sku"], "NEW-2"))
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert item["sku"] in body["error"]["message"]

    # atomic: nothing was created, not even the items before the conflicting one
    after = client.get("/items").json()["total"]
    assert after == before
    assert client.get("/items/by-sku/NEW-1").status_code == 404
    assert client.get("/items/by-sku/NEW-2").status_code == 404


def test_bulk_create_conflict_within_batch_creates_nothing(client):
    r = client.post("/items/bulk", json=_payload("DUP-1", "DUP-1"))
    assert r.status_code == 409
    assert client.get("/items/by-sku/DUP-1").status_code == 404
    assert client.get("/items").json()["total"] == 0


def test_bulk_create_empty_list_returns_422(client):
    r = client.post("/items/bulk", json=[])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_bulk_create_invalid_item_returns_422_and_creates_nothing(client):
    r = client.post("/items/bulk", json=[{"sku": "OK-1", "name": "ok"}, {"name": "no sku"}])
    assert r.status_code == 422
    assert client.get("/items/by-sku/OK-1").status_code == 404
