"""GET /stats entity counts."""


def _move(client, **kw):
    r = client.post("/movements", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


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


def test_stats_counts_entities(client, item, loc_a, loc_b):
    other = client.post(
        "/items",
        json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0},
    )
    assert other.status_code == 201
    # deactivate the second item
    r = client.put(f"/items/{other.json()['id']}", json={"active": False})
    assert r.status_code == 200

    _move(client, item_id=item["id"], kind="receive", quantity=7, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_b["id"])

    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 2,
        "active_items": 1,
        "locations": 2,
        "movements": 2,
        "total_units": 10,
    }


def test_stats_total_units_sums_all_stock_levels(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=8, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    _move(client, item_id=item["id"], kind="ship", quantity=2, from_location_id=loc_b["id"])

    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_units"] == 6  # 8 received - 2 shipped, split across locations
    assert body["movements"] == 3
