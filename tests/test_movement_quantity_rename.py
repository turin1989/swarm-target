"""T047: movement/stock field `qty` is renamed to `quantity` in the JSON API."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_post_movement_with_old_qty_name_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_post_movement_with_both_qty_and_quantity_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        quantity=5,
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 422
    assert client.get("/movements").json() == []


def test_movement_request_and_response_use_quantity(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["quantity"] == 5
    assert "qty" not in body

    got = client.get(f"/movements/{body['id']}").json()
    assert got["quantity"] == 5
    assert "qty" not in got

    listed = client.get("/movements").json()
    assert [m["quantity"] for m in listed] == [5]
    assert all("qty" not in m for m in listed)


def test_stock_levels_use_quantity(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=7, to_location_id=loc_a["id"])

    item_stock = client.get(f"/items/{item['id']}/stock").json()
    assert item_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 7}
    ]

    loc_stock = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert loc_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 7}
    ]


def test_quantity_still_validated_positive(client, item, loc_a):
    for bad in (0, -1):
        r = _move(
            client, item_id=item["id"], kind="receive", quantity=bad, to_location_id=loc_a["id"]
        )
        assert r.status_code == 422
