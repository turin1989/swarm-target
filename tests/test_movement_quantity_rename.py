"""T047: movement/stock field `qty` renamed to `quantity` in the JSON API."""


def test_movement_create_and_response_use_quantity(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 10,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["quantity"] == 10
    assert "qty" not in body


def test_movement_with_old_qty_name_returns_422(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "qty": 10,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 422


def test_movement_with_both_qty_and_quantity_returns_422(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "qty": 10,
            "quantity": 10,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 422


def test_movement_read_endpoints_use_quantity(client, item, loc_a):
    created = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 4,
            "to_location_id": loc_a["id"],
        },
    ).json()

    listed = client.get("/movements").json()
    assert listed[0]["quantity"] == 4
    assert "qty" not in listed[0]

    per_item = client.get(f"/items/{item['id']}/movements").json()
    assert per_item[0]["quantity"] == 4
    assert "qty" not in per_item[0]

    reversed_ = client.post(f"/movements/{created['id']}/reverse")
    assert reversed_.status_code == 201
    assert reversed_.json()["quantity"] == 4
    assert "qty" not in reversed_.json()


def test_stock_level_responses_use_quantity(client, item, loc_a):
    client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 6,
            "to_location_id": loc_a["id"],
        },
    )

    item_stock = client.get(f"/items/{item['id']}/stock").json()
    assert item_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 6}
    ]

    location_stock = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert location_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 6}
    ]


def test_database_columns_still_named_qty(client, item, loc_a, tmp_path):
    import sqlite3

    client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 2,
            "to_location_id": loc_a["id"],
        },
    )
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    movement_cols = [row[1] for row in conn.execute("PRAGMA table_info(movements)")]
    stock_cols = [row[1] for row in conn.execute("PRAGMA table_info(stock_levels)")]
    conn.close()
    assert "qty" in movement_cols and "quantity" not in movement_cols
    assert "qty" in stock_cols and "quantity" not in stock_cols
