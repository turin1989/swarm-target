"""GET /stats endpoint."""


def test_stats_empty_db(client):
    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 0,
        "active_items": 0,
        "locations": 0,
        "movements": 0,
        "total_units": 0,
    }


def test_stats_counts_entities_and_sums_units(client, loc_a, loc_b):
    i1 = client.post("/items", json={"sku": "A1", "name": "Alpha"}).json()
    i2 = client.post("/items", json={"sku": "B2", "name": "Beta"}).json()
    client.post("/items", json={"sku": "C3", "name": "Gamma"})

    client.post(
        "/movements",
        json={"item_id": i1["id"], "kind": "receive", "quantity": 7, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": i2["id"], "kind": "receive", "quantity": 5, "to_location_id": loc_b["id"]},
    )

    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 3,
        "active_items": 3,
        "locations": 2,
        "movements": 2,
        "total_units": 12,
    }


def test_stats_active_items_excludes_inactive(client):
    item = client.post("/items", json={"sku": "X1", "name": "X"}).json()
    client.post("/items", json={"sku": "X2", "name": "Y"})
    client.put(f"/items/{item['id']}", json={"active": False})

    body = client.get("/stats").json()
    assert body["items"] == 2
    assert body["active_items"] == 1


def test_stats_total_units_sums_stock_levels_after_ship(client, loc_a):
    item = client.post("/items", json={"sku": "S1", "name": "Ship"}).json()
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 10, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 4, "from_location_id": loc_a["id"]},
    )

    body = client.get("/stats").json()
    assert body["total_units"] == 6
    assert body["movements"] == 2
