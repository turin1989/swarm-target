"""Tests for POST /items/bulk."""


def _bulk(client, items):
    return client.post("/items/bulk", json=items)


def test_bulk_create_returns_201_with_created_items(client):
    payload = [
        {"sku": "BULK-1", "name": "Bulk One", "unit_price": 1.0},
        {"sku": "BULK-2", "name": "Bulk Two", "unit_price": 2.0, "barcode": "B2"},
    ]
    r = _bulk(client, payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert [i["sku"] for i in body] == ["BULK-1", "BULK-2"]
    assert all("id" in i for i in body)
    assert body[1]["barcode"] == "B2"

    # items are actually persisted
    for created in body:
        got = client.get(f"/items/{created['id']}")
        assert got.status_code == 200
        assert got.json()["sku"] == created["sku"]


def test_bulk_create_duplicate_sku_is_atomic(client):
    r = client.post("/items", json={"sku": "EXISTS-1", "name": "Existing"})
    assert r.status_code == 201, r.text

    payload = [
        {"sku": "NEW-1", "name": "New One"},
        {"sku": "EXISTS-1", "name": "Dup"},
        {"sku": "NEW-2", "name": "New Two"},
    ]
    r = _bulk(client, payload)
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "EXISTS-1" in body["error"]["message"]

    # nothing from the batch was created
    listing = client.get("/items").json()
    skus = {i["sku"] for i in listing["items"]}
    assert skus == {"EXISTS-1"}
    assert listing["total"] == 1


def test_bulk_create_duplicate_sku_within_batch_is_atomic(client):
    payload = [
        {"sku": "SAME-1", "name": "First"},
        {"sku": "SAME-1", "name": "Second"},
    ]
    r = _bulk(client, payload)
    assert r.status_code == 409, r.text

    listing = client.get("/items").json()
    assert listing["total"] == 0


def test_bulk_create_empty_list_returns_422(client):
    r = _bulk(client, [])
    assert r.status_code == 422, r.text

    listing = client.get("/items").json()
    assert listing["total"] == 0


def test_bulk_create_invalid_payload_returns_422(client):
    # missing required fields
    r = _bulk(client, [{"sku": "ONLY-SKU"}])
    assert r.status_code == 422, r.text
