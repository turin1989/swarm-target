"""GET /stats entity counts."""


def _move(client, item, kind, quantity, *, frm=None, to=None):
    payload = {"item_id": item["id"], "kind": kind, "quantity": quantity}
    if frm is not None:
        payload["from_location_id"] = frm["id"]
    if to is not None:
        payload["to_location_id"] = to["id"]
    r = client.post("/movements", json=payload)
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


def test_stats_counts_entities_and_sums_units(client, item, loc_a, loc_b):
    # A second, inactive item.
    r = client.post(
        "/items",
        json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0, "reorder_level": 0},
    )
    assert r.status_code == 201, r.text
    other = r.json()
    r = client.put(f"/items/{other['id']}", json={"active": False})
    assert r.status_code == 200, r.text

    _move(client, item, "receive", 10, to=loc_a)
    _move(client, item, "receive", 5, to=loc_b)
    _move(client, item, "ship", 3, frm=loc_a)
    _move(client, item, "transfer", 2, frm=loc_a, to=loc_b)

    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 2,
        "active_items": 1,
        "locations": 2,
        "movements": 4,
        "total_units": 12,  # 10 + 5 - 3 (transfer does not change the total)
    }
