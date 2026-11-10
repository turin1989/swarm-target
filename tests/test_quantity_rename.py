"""T047: movement/stock field renamed from `qty` to `quantity` in the JSON API."""


def test_movement_create_accepts_quantity(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 5,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["quantity"] == 5
    assert "qty" not in body


def test_movement_create_with_old_qty_name_422(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "qty": 5,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movement_list_and_get_use_quantity(client, item, loc_a):
    client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 3,
            "to_location_id": loc_a["id"],
        },
    )
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["quantity"] == 3
    assert "qty" not in movements[0]


def test_stock_level_responses_use_quantity(client, item, loc_a):
    client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 4,
            "to_location_id": loc_a["id"],
        },
    )
    item_stock = client.get(f"/items/{item['id']}/stock").json()
    assert item_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 4}
    ]
    loc_stock = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert loc_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 4}
    ]


def test_reverse_movement_response_uses_quantity(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 2,
            "to_location_id": loc_a["id"],
        },
    )
    movement_id = r.json()["id"]
    rev = client.post(f"/movements/{movement_id}/reverse")
    assert rev.status_code == 201, rev.text
    body = rev.json()
    assert body["quantity"] == 2
    assert "qty" not in body
