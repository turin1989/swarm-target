"""Tests for GET /locations/{id}/stock (task T014)."""


def _receive(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "qty": qty, "to_location_id": location_id},
    )
    assert r.status_code == 201, r.text


def _ship(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "ship", "qty": qty, "from_location_id": location_id},
    )
    assert r.status_code == 201, r.text


def test_location_stock_lists_levels_ordered_by_item_id(client, loc_a):
    # Create items in an order that doesn't match insertion order of stock rows.
    ids = []
    for sku in ("SKU-C", "SKU-A", "SKU-B"):
        r = client.post("/items", json={"sku": sku, "name": sku})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    # Receive in reverse item_id order so ordering must come from the query.
    _receive(client, ids[2], loc_a["id"], 7)
    _receive(client, ids[1], loc_a["id"], 3)
    _receive(client, ids[0], loc_a["id"], 5)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["location_id"] == loc_a["id"]
    assert [lvl["item_id"] for lvl in body["levels"]] == sorted(ids)
    by_item = {lvl["item_id"]: lvl for lvl in body["levels"]}
    assert by_item[ids[0]]["qty"] == 5
    assert by_item[ids[1]]["qty"] == 3
    assert by_item[ids[2]]["qty"] == 7
    for lvl in body["levels"]:
        assert lvl["location_id"] == loc_a["id"]


def test_location_stock_omits_zero_quantity_levels(client, item, loc_a):
    r = client.post("/items", json={"sku": "SKU-Z", "name": "Zeroed"})
    assert r.status_code == 201, r.text
    zero_item = r.json()

    _receive(client, item["id"], loc_a["id"], 4)
    _receive(client, zero_item["id"], loc_a["id"], 6)
    _ship(client, zero_item["id"], loc_a["id"], 6)  # back down to zero

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "qty": 4}
    ]


def test_location_stock_empty_location(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    assert r.json() == {"location_id": loc_a["id"], "levels": []}


def test_location_stock_unknown_location_404(client):
    r = client.get("/locations/99999/stock")
    assert r.status_code == 404
