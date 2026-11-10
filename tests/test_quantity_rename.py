"""T047: movement/stock field ``qty`` renamed to ``quantity`` in the API.

The database columns keep their old ``qty`` names; only the JSON contract
(MovementCreate, Movement, StockLevel) changes.
"""


def _receive(client, item_id, location_id, quantity):
    return client.post(
        "/movements",
        json={
            "item_id": item_id,
            "kind": "receive",
            "quantity": quantity,
            "to_location_id": location_id,
        },
    )


def test_post_movements_accepts_quantity(client, item, loc_a):
    r = _receive(client, item["id"], loc_a["id"], 7)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["quantity"] == 7
    assert "qty" not in body


def test_post_movements_with_old_qty_name_returns_422(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "qty": 7,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 422
    # Nothing was recorded.
    assert client.get("/movements").json() == []


def test_movement_responses_use_quantity(client, item, loc_a):
    created = _receive(client, item["id"], loc_a["id"], 4).json()

    fetched = client.get(f"/movements/{created['id']}").json()
    assert fetched["quantity"] == 4
    assert "qty" not in fetched

    listed = client.get("/movements").json()
    assert [m["quantity"] for m in listed] == [4]
    assert all("qty" not in m for m in listed)

    item_movements = client.get(f"/items/{item['id']}/movements").json()
    assert [m["quantity"] for m in item_movements] == [4]
    assert all("qty" not in m for m in item_movements)


def test_stock_level_responses_use_quantity(client, item, loc_a):
    _receive(client, item["id"], loc_a["id"], 9)

    stock = client.get(f"/items/{item['id']}/stock").json()
    assert stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 9}
    ]

    loc_stock = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert loc_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 9}
    ]


def test_database_columns_keep_qty_name(client, item, loc_a, tmp_path):
    import sqlite3

    _receive(client, item["id"], loc_a["id"], 3)
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        movement_cols = [r[1] for r in conn.execute("PRAGMA table_info(movements)")]
        stock_cols = [r[1] for r in conn.execute("PRAGMA table_info(stock_levels)")]
    finally:
        conn.close()
    assert "qty" in movement_cols and "quantity" not in movement_cols
    assert "qty" in stock_cols and "quantity" not in stock_cols
