"""GET /locations/{id}/stock — all items held at a location."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _item(client, sku, name="Thing"):
    r = client.post("/items", json={"sku": sku, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_unknown_location_404(client):
    r = client.get("/locations/999/stock")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "999" in body["error"]["message"]


def test_empty_location_returns_no_levels(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    assert r.json() == {"location_id": loc_a["id"], "levels": []}


def test_levels_ordered_by_item_id(client, loc_a):
    item_c = _item(client, "SKU-C")
    item_a = _item(client, "SKU-A")
    item_b = _item(client, "SKU-B")
    # receive in non-sorted item order
    _move(client, item_id=item_b["id"], kind="receive", quantity=2, to_location_id=loc_a["id"])
    _move(client, item_id=item_c["id"], kind="receive", quantity=3, to_location_id=loc_a["id"])
    _move(client, item_id=item_a["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    body = r.json()
    assert body["location_id"] == loc_a["id"]
    expected_order = sorted([item_a["id"], item_b["id"], item_c["id"]])
    assert [lvl["item_id"] for lvl in body["levels"]] == expected_order
    assert body["levels"] == [
        {"item_id": item_c["id"], "location_id": loc_a["id"], "quantity": 3},
        {"item_id": item_a["id"], "location_id": loc_a["id"], "quantity": 1},
        {"item_id": item_b["id"], "location_id": loc_a["id"], "quantity": 2},
    ]


def test_zero_qty_levels_omitted(client, loc_a):
    item_x = _item(client, "SKU-X")
    item_y = _item(client, "SKU-Y")
    _move(client, item_id=item_x["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(client, item_id=item_y["id"], kind="receive", quantity=4, to_location_id=loc_a["id"])
    # ship all of item_x out, leaving a quantity-0 stock_levels row
    _move(client, item_id=item_x["id"], kind="ship", quantity=5, from_location_id=loc_a["id"])

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    assert r.json() == {
        "location_id": loc_a["id"],
        "levels": [{"item_id": item_y["id"], "location_id": loc_a["id"], "quantity": 4}],
    }


def test_only_levels_for_requested_location(client, loc_a, loc_b):
    item = _item(client, "SKU-Z")
    _move(client, item_id=item["id"], kind="receive", quantity=6, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=9, to_location_id=loc_b["id"])

    r = client.get(f"/locations/{loc_b['id']}/stock")
    assert r.status_code == 200
    assert r.json() == {
        "location_id": loc_b["id"],
        "levels": [{"item_id": item["id"], "location_id": loc_b["id"], "quantity": 9}],
    }
