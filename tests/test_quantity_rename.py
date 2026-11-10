"""T047: movement/stock field `qty` is renamed to `quantity` in the JSON API."""


def test_post_movement_with_quantity_succeeds_and_echoes_quantity(client, item, loc_a):
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


def test_post_movement_with_old_qty_name_returns_422(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 422


def test_old_qty_name_writes_no_movement_row(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    assert client.get("/movements").json() == []


def test_get_movement_uses_quantity(client, item, loc_a):
    created = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 3,
            "to_location_id": loc_a["id"],
        },
    ).json()
    body = client.get(f"/movements/{created['id']}").json()
    assert body["quantity"] == 3
    assert "qty" not in body


def test_movement_listings_use_quantity(client, item, loc_a):
    client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 4,
            "to_location_id": loc_a["id"],
        },
    )
    for url in ("/movements", f"/items/{item['id']}/movements"):
        movements = client.get(url).json()
        assert movements, url
        assert all(m["quantity"] == 4 and "qty" not in m for m in movements)


def test_stock_levels_use_quantity(client, item, loc_a):
    client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 7,
            "to_location_id": loc_a["id"],
        },
    )
    item_stock = client.get(f"/items/{item['id']}/stock").json()
    assert item_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 7}
    ]
    loc_stock = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert loc_stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 7}
    ]


def test_bulk_created_item_movements_use_quantity(client, loc_a):
    """T047 x T022: items created via the bulk endpoint move stock via `quantity`."""
    created = client.post(
        "/items/bulk",
        json=[{"sku": "BULK-QTY-1", "name": "Bulk item"}],
    )
    assert created.status_code == 201, created.text
    item_id = created.json()[0]["id"]

    old_name = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "qty": 6, "to_location_id": loc_a["id"]},
    )
    assert old_name.status_code == 422

    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "quantity": 6, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["quantity"] == 6
    assert "qty" not in r.json()

    stock = client.get(f"/items/{item_id}/stock").json()
    assert stock["levels"] == [{"item_id": item_id, "location_id": loc_a["id"], "quantity": 6}]


def test_database_column_remains_qty(client, item, loc_a, tmp_path):
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
    conn.row_factory = sqlite3.Row
    try:
        movement_cols = {r["name"] for r in conn.execute("PRAGMA table_info(movements)")}
        stock_cols = {r["name"] for r in conn.execute("PRAGMA table_info(stock_levels)")}
        assert "qty" in movement_cols and "quantity" not in movement_cols
        assert "qty" in stock_cols and "quantity" not in stock_cols
        row = conn.execute("SELECT qty FROM movements").fetchone()
        assert row["qty"] == 2
    finally:
        conn.close()
