"""Tests for GET /locations/{id}/stock (task T014)."""


def _receive(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "qty": qty, "to_location_id": location_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _ship(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "ship", "qty": qty, "from_location_id": location_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_location_stock_lists_levels_ordered_by_item_id(client, item, loc_a):
    # Create a second item and receive it *first* so insertion order differs
    # from item_id order.
    r = client.post("/items", json={"sku": "WIDGET-2", "name": "Widget 2"})
    assert r.status_code == 201, r.text
    item2 = r.json()
    assert item2["id"] > item["id"]

    _receive(client, item2["id"], loc_a["id"], 7)
    _receive(client, item["id"], loc_a["id"], 3)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["location_id"] == loc_a["id"]
    assert body["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "qty": 3},
        {"item_id": item2["id"], "location_id": loc_a["id"], "qty": 7},
    ]


def test_location_stock_empty_location(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    assert r.json() == {"location_id": loc_a["id"], "levels": []}


def test_location_stock_omits_zero_qty_levels(client, item, loc_a):
    r = client.post("/items", json={"sku": "WIDGET-2", "name": "Widget 2"})
    assert r.status_code == 201, r.text
    item2 = r.json()

    _receive(client, item["id"], loc_a["id"], 5)
    _receive(client, item2["id"], loc_a["id"], 4)
    # Ship everything of item2 out so its level at loc_a is exactly 0.
    _ship(client, item2["id"], loc_a["id"], 4)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}
    ]


def test_location_stock_only_includes_that_location(client, item, loc_a, loc_b):
    _receive(client, item["id"], loc_a["id"], 2)
    _receive(client, item["id"], loc_b["id"], 9)

    r = client.get(f"/locations/{loc_b['id']}/stock")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "location_id": loc_b["id"],
        "levels": [{"item_id": item["id"], "location_id": loc_b["id"], "qty": 9}],
    }


def test_location_stock_unknown_location_404(client):
    r = client.get("/locations/9999/stock")
    assert r.status_code == 404
