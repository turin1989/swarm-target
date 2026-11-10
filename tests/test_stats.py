"""GET /stats entity counts report."""


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


def test_stats_counts_entities_and_total_units(client, item, loc_a, loc_b):
    # a second, inactive item
    r = client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    assert r.status_code == 201
    other = r.json()
    r = client.put(f"/items/{other['id']}", json={"active": False})
    assert r.status_code == 200

    # movements: receive 10 into A, transfer 4 to B, ship 3 from A
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 10, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "quantity": 4,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
        },
    )
    assert r.status_code == 201
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 3, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201

    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 2,
        "active_items": 1,
        "locations": 2,
        "movements": 3,
        "total_units": 7,  # 10 received - 3 shipped; transfer does not change the total
    }


def test_stats_total_units_sums_across_items_and_locations(client, item, loc_a, loc_b):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 5, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 2, "to_location_id": loc_b["id"]},
    )
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_units"] == 7
    assert body["items"] == 1
    assert body["active_items"] == 1
    assert body["locations"] == 2
    assert body["movements"] == 2
