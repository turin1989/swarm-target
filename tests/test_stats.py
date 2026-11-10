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
    # a second item, which we then deactivate
    r = client.post(
        "/items",
        json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0},
    )
    assert r.status_code == 201, r.text
    inactive = r.json()
    r = client.put(f"/items/{inactive['id']}", json={"active": False})
    assert r.status_code == 200, r.text

    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=7, to_location_id=loc_b["id"])
    _move(client, item_id=item["id"], kind="ship", quantity=3, from_location_id=loc_a["id"])

    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 2,
        "active_items": 1,
        "locations": 2,
        "movements": 3,
        # total_units sums all stock level quantities: (10 - 3) + 7
        "total_units": 14,
    }
