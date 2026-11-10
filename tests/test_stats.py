"""GET /stats report."""


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


def test_stats_counts_entities_and_units(client, item, loc_a, loc_b):
    # a second, inactive item
    r = client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    assert r.status_code == 201
    inactive = r.json()
    r = client.put(f"/items/{inactive['id']}", json={"active": False})
    assert r.status_code == 200
    assert r.json()["active"] is False

    # stock movements: 10 into A, 4 into B -> total_units = 14
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 10, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 4, "to_location_id": loc_b["id"]},
    )
    assert r.status_code == 201

    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 2,
        "active_items": 1,
        "locations": 2,
        "movements": 2,
        "total_units": 14,
    }


def test_stats_total_units_sums_stock_levels_after_ship(client, item, loc_a):
    for kind, qty, key in (("receive", 9, "to_location_id"), ("ship", 3, "from_location_id")):
        r = client.post(
            "/movements",
            json={"item_id": item["id"], "kind": kind, "quantity": qty, key: loc_a["id"]},
        )
        assert r.status_code == 201, r.text

    body = client.get("/stats").json()
    assert body["total_units"] == 6
    assert body["movements"] == 2
