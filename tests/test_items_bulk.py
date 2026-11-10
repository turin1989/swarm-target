"""Bulk item creation endpoint (POST /items/bulk)."""


def test_bulk_create_returns_201_and_items(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "B-1", "name": "Bulk One", "unit_price": 1.5, "reorder_point": 2},
            {"sku": "B-2", "name": "Bulk Two"},
        ],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert [i["sku"] for i in body] == ["B-1", "B-2"]
    assert body[0]["name"] == "Bulk One"
    assert body[0]["unit_price"] == 1.5
    assert body[0]["reorder_point"] == 2
    assert body[1]["name"] == "Bulk Two"
    assert all(i["active"] is True for i in body)
    assert all("id" in i for i in body)
    # items are persisted
    assert [i["sku"] for i in client.get("/items").json()] == ["B-1", "B-2"]


def test_bulk_create_existing_sku_conflicts_and_creates_nothing(client, item):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "NEW-1", "name": "New One"},
            {"sku": item["sku"], "name": "Duplicate"},
            {"sku": "NEW-2", "name": "New Two"},
        ],
    )
    assert r.status_code == 409
    # atomic: nothing from the batch was created, not even NEW-1
    skus = [i["sku"] for i in client.get("/items").json()]
    assert skus == [item["sku"]]


def test_bulk_create_duplicate_sku_within_payload_conflicts_and_creates_nothing(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "DUP", "name": "First"},
            {"sku": "DUP", "name": "Second"},
        ],
    )
    assert r.status_code == 409
    assert client.get("/items").json() == []


def test_bulk_create_empty_list_422(client):
    r = client.post("/items/bulk", json=[])
    assert r.status_code == 422
    assert client.get("/items").json() == []


def test_bulk_create_invalid_item_422(client):
    r = client.post("/items/bulk", json=[{"sku": "OK-1", "name": "Ok"}, {"name": "missing sku"}])
    assert r.status_code == 422
    assert client.get("/items").json() == []


def test_bulk_create_does_not_break_single_create(client):
    assert client.post("/items", json={"sku": "SINGLE", "name": "Single"}).status_code == 201
