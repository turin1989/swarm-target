"""T047: movement/stock field qty is renamed to quantity in the JSON API."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_movement_create_accepts_quantity(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["quantity"] == 5
    assert "qty" not in body


def test_movement_create_with_old_qty_name_returns_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    assert r.status_code == 422


def test_movement_create_with_both_qty_and_quantity_returns_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        quantity=5,
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 422


def test_old_qty_name_writes_no_movement_row(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    assert r.status_code == 422
    assert client.get("/movements").json() == []


def test_get_movement_response_uses_quantity(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"]
    ).json()
    body = client.get(f"/movements/{created['id']}").json()
    assert body["quantity"] == 3
    assert "qty" not in body


def test_list_movements_uses_quantity(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=2, to_location_id=loc_a["id"])
    movements = client.get("/movements").json()
    assert [m["quantity"] for m in movements] == [2]
    assert all("qty" not in m for m in movements)


def test_stock_levels_use_quantity(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_a["id"])

    item_stock = client.get(f"/items/{item['id']}/stock").json()
    assert item_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 4}
    ]

    loc_stock = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert loc_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 4}
    ]
