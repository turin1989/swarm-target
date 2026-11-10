"""T047: movement/stock field is named `quantity` (was `qty`) in the JSON API."""


def test_post_movement_with_old_qty_name_returns_422(client, item, loc_a):
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
    # No movement was recorded.
    assert client.get("/movements").json() == []


def test_movement_response_uses_quantity(client, item, loc_a):
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

    listed = client.get("/movements").json()
    assert listed[0]["quantity"] == 5
    assert "qty" not in listed[0]

    per_item = client.get(f"/items/{item['id']}/movements").json()
    assert per_item[0]["quantity"] == 5
    assert "qty" not in per_item[0]


def test_stock_level_responses_use_quantity(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 7,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 201, r.text

    item_stock = client.get(f"/items/{item['id']}/stock").json()
    assert item_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 7}
    ]

    loc_stock = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert loc_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 7}
    ]
