"""Bulk item creation (POST /items/bulk)."""


def test_bulk_create_returns_201_and_items(client):
    payload = [
        {"sku": "B-1", "name": "Bulk One", "unit_price": 1.0},
        {"sku": "B-2", "name": "Bulk Two", "unit_price": 2.0, "reorder_point": 3},
    ]
    r = client.post("/items/bulk", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert [i["sku"] for i in body] == ["B-1", "B-2"]
    assert [i["name"] for i in body] == ["Bulk One", "Bulk Two"]
    assert body[0]["unit_price"] == 1.0
    assert body[1]["reorder_point"] == 3
    assert all(i["active"] is True for i in body)
    # items are actually persisted
    assert [i["sku"] for i in client.get("/items").json()] == ["B-1", "B-2"]


def test_bulk_create_duplicate_existing_sku_conflicts(client, item):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "NEW-1", "name": "New"}, {"sku": item["sku"], "name": "Dup"}],
    )
    assert r.status_code == 409
    assert item["sku"] in r.json()["detail"]


def test_bulk_create_is_atomic_on_conflict(client, item):
    before = client.get("/items").json()
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "NEW-1", "name": "New One"},
            {"sku": item["sku"], "name": "Dup"},
            {"sku": "NEW-2", "name": "New Two"},
        ],
    )
    assert r.status_code == 409
    # nothing was created, not even the valid entries before/after the duplicate
    assert client.get("/items").json() == before


def test_bulk_create_duplicate_sku_within_payload_conflicts_and_creates_nothing(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "SAME", "name": "First"}, {"sku": "SAME", "name": "Second"}],
    )
    assert r.status_code == 409
    assert client.get("/items").json() == []


def test_bulk_create_empty_list_returns_422(client):
    r = client.post("/items/bulk", json=[])
    assert r.status_code == 422
    assert client.get("/items").json() == []


def test_bulk_create_invalid_item_returns_422(client):
    r = client.post("/items/bulk", json=[{"sku": "OK-1", "name": "Ok"}, {"name": "missing sku"}])
    assert r.status_code == 422
    assert client.get("/items").json() == []
