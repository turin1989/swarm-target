"""Tests for GET /locations/{id}/stock."""


def _receive(client, item_id, location_id, quantity):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "quantity": quantity, "to_location_id": location_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_location_stock_unknown_location_returns_404(client):
    r = client.get("/locations/9999/stock")
    assert r.status_code == 404


def test_location_stock_empty_location(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    assert r.json() == {"location_id": loc_a["id"], "levels": []}


def test_location_stock_lists_levels_ordered_by_item_id(client, loc_a, loc_b):
    items = []
    for sku in ("SKU-C", "SKU-B", "SKU-A"):
        r = client.post("/items", json={"sku": sku, "name": f"Item {sku}"})
        assert r.status_code == 201, r.text
        items.append(r.json())

    # Receive in an order that is not sorted by item_id.
    _receive(client, items[2]["id"], loc_a["id"], 7)
    _receive(client, items[0]["id"], loc_a["id"], 3)
    _receive(client, items[1]["id"], loc_a["id"], 5)
    # Stock at another location must not appear.
    _receive(client, items[0]["id"], loc_b["id"], 99)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    body = r.json()
    assert body["location_id"] == loc_a["id"]
    expected = sorted(
        [
            {"item_id": items[2]["id"], "location_id": loc_a["id"], "quantity": 7},
            {"item_id": items[0]["id"], "location_id": loc_a["id"], "quantity": 3},
            {"item_id": items[1]["id"], "location_id": loc_a["id"], "quantity": 5},
        ],
        key=lambda lvl: lvl["item_id"],
    )
    assert body["levels"] == expected
    item_ids = [lvl["item_id"] for lvl in body["levels"]]
    assert item_ids == sorted(item_ids)


def test_location_stock_omits_zero_quantity_levels(client, item, loc_a):
    _receive(client, item["id"], loc_a["id"], 4)
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 4, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    assert r.json() == {"location_id": loc_a["id"], "levels": []}
