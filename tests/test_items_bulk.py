"""Bulk item creation: POST /items/bulk (T022)."""


def test_bulk_create_returns_201_with_created_items(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "BULK-1", "name": "One", "unit_price": 1.0},
            {"sku": "BULK-2", "name": "Two", "unit_price": 2.0, "reorder_level": 3},
        ],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert [i["sku"] for i in body] == ["BULK-1", "BULK-2"]
    assert body[0]["name"] == "One"
    assert body[1]["reorder_level"] == 3
    # created items all have ids and are retrievable individually
    for created in body:
        assert client.get(f"/items/{created['id']}").json() == created


def test_bulk_create_items_persisted(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "P-1", "name": "A"}, {"sku": "P-2", "name": "B"}],
    )
    assert r.status_code == 201
    listing = client.get("/items")
    assert listing.headers["X-Total-Count"] == "2"
    assert [i["sku"] for i in listing.json()["items"]] == ["P-1", "P-2"]


def test_bulk_create_existing_sku_conflicts_and_creates_nothing(client, item):
    # item fixture already holds sku WIDGET-1
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "NEW-1", "name": "New"},
            {"sku": item["sku"], "name": "Dup"},
            {"sku": "NEW-2", "name": "Also New"},
        ],
    )
    assert r.status_code == 409
    assert item["sku"] in r.json()["error"]["message"]
    # atomic: nothing from the batch was created
    listing = client.get("/items")
    assert [i["sku"] for i in listing.json()["items"]] == [item["sku"]]
    assert listing.headers["X-Total-Count"] == "1"
    assert client.get("/items/by-sku/NEW-1").status_code == 404
    assert client.get("/items/by-sku/NEW-2").status_code == 404


def test_bulk_create_duplicate_sku_within_payload_conflicts_and_creates_nothing(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "SAME-1", "name": "First"},
            {"sku": "SAME-1", "name": "Second"},
        ],
    )
    assert r.status_code == 409
    listing = client.get("/items")
    assert listing.json()["items"] == []
    assert listing.headers["X-Total-Count"] == "0"


def test_bulk_create_empty_list_returns_422(client):
    r = client.post("/items/bulk", json=[])
    assert r.status_code == 422
    assert client.get("/items").json()["items"] == []


def test_bulk_create_invalid_entry_returns_422_and_creates_nothing(client):
    r = client.post(
        "/items/bulk",
        json=[{"sku": "OK-1", "name": "Fine"}, {"sku": "", "name": "Bad"}],
    )
    assert r.status_code == 422
    assert client.get("/items").json()["items"] == []


def test_bulk_create_normalises_sku(client):
    r = client.post("/items/bulk", json=[{"sku": "  bulk-x ", "name": "X"}])
    assert r.status_code == 201
    assert r.json()[0]["sku"] == "BULK-X"
