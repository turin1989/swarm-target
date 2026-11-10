"""Bulk item creation (T022)."""


def test_bulk_create_returns_201_with_created_items(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "B-1", "name": "Bulk One", "unit_price": 1.5},
            {"sku": "B-2", "name": "Bulk Two", "reorder_point": 3},
        ],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert [i["sku"] for i in body] == ["B-1", "B-2"]
    assert body[0]["name"] == "Bulk One"
    assert body[0]["unit_price"] == 1.5
    assert body[0]["active"] is True
    assert body[1]["reorder_point"] == 3
    assert all(i["id"] for i in body)

    # all items are persisted
    listed = client.get("/items").json()
    assert [i["sku"] for i in listed] == ["B-1", "B-2"]


def test_bulk_create_duplicate_existing_sku_conflicts_and_creates_nothing(client, item):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "NEW-1", "name": "New One"},
            {"sku": item["sku"], "name": "Dup"},
            {"sku": "NEW-2", "name": "New Two"},
        ],
    )
    assert r.status_code == 409
    assert item["sku"] in r.json()["detail"]
    # atomic: nothing from the batch was created
    listed = client.get("/items").json()
    assert [i["sku"] for i in listed] == [item["sku"]]


def test_bulk_create_duplicate_sku_within_payload_conflicts_and_creates_nothing(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "SAME", "name": "First"},
            {"sku": "SAME", "name": "Second"},
        ],
    )
    assert r.status_code == 409
    assert client.get("/items").json() == []


def test_bulk_create_empty_list_422(client):
    r = client.post("/items/bulk", json=[])
    assert r.status_code == 422
    assert client.get("/items").json() == []


def test_bulk_create_invalid_entry_422_and_creates_nothing(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "OK-1", "name": "Ok"}, {"name": "missing sku"}],
    )
    assert r.status_code == 422
    assert client.get("/items").json() == []
