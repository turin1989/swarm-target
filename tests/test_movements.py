"""Locations, movements, stock levels."""

import pytest


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_create_and_list_locations(client, loc_a, loc_b):
    r = client.get("/locations")
    assert r.status_code == 200
    assert [loc["code"] for loc in r.json()] == ["WH-A", "WH-B"]
    assert loc_a == {"id": 1, "code": "WH-A", "name": "Warehouse A"}


def test_get_location(client, loc_a):
    assert client.get(f"/locations/{loc_a['id']}").json() == loc_a
    assert client.get("/locations/99").status_code == 404


def test_location_requires_code(client):
    assert client.post("/locations", json={"name": "x"}).status_code == 422


def test_receive_increases_stock(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["kind"] == "receive"
    assert body["qty"] == 10
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 10
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 10}]


def test_receive_accumulates(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=4, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=6, to_location_id=loc_a["id"])
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_ship_decreases_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=3, from_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 7


def test_stock_split_across_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=7, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 12
    assert [lvl["qty"] for lvl in s["levels"]] == [5, 7]


def test_transfer_is_recorded(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
        note="rebalance",
    )
    assert r.status_code == 201
    assert r.json()["note"] == "rebalance"
    movements = client.get("/movements").json()
    assert len(movements) == 2
    assert movements[1]["kind"] == "transfer"


def test_stock_for_missing_item_404(client):
    assert client.get("/items/77/stock").status_code == 404


def test_stock_empty_for_new_item(client, item):
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s == {"item_id": item["id"], "total": 0, "levels": []}


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {}),
        ("ship", {}),
        ("transfer", {"from_location_id": 1}),
    ],
)
def test_movement_requires_locations(client, item, loc_a, kind, payload):
    r = _move(client, item_id=item["id"], kind=kind, qty=1, **payload)
    assert r.status_code == 400
    assert "required" in r.json()["detail"]


def test_movement_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=123)
    assert r.status_code == 404


def test_movement_unknown_item_404(client, loc_a):
    r = _move(client, item_id=123, kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 404


def test_movement_invalid_kind_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="explode", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 422


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


# --- location stock ------------------------------------------------------------


def _receive(client, item_id, location_id, qty):
    r = _move(client, item_id=item_id, kind="receive", qty=qty, to_location_id=location_id)
    assert r.status_code == 201, r.text
    return r


def test_location_stock_empty_for_new_location(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    assert r.json() == {"location_id": loc_a["id"], "levels": []}


def test_location_stock_unknown_location_404(client):
    assert client.get("/locations/999/stock").status_code == 404


def test_location_stock_lists_levels_ordered_by_item_id(client, loc_a, loc_b):
    item_ids = []
    for sku in ("C-SKU", "A-SKU", "B-SKU"):
        r = client.post("/items", json={"sku": sku, "name": sku})
        assert r.status_code == 201, r.text
        item_ids.append(r.json()["id"])
    # receive in a shuffled order so insertion order != item_id order
    for item_id, qty in [(item_ids[2], 3), (item_ids[0], 7), (item_ids[1], 5)]:
        _receive(client, item_id, loc_a["id"], qty)
    # stock at another location should not appear
    _receive(client, item_ids[0], loc_b["id"], 99)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    body = r.json()
    assert body["location_id"] == loc_a["id"]
    assert [lvl["item_id"] for lvl in body["levels"]] == sorted(item_ids)
    by_item = {lvl["item_id"]: lvl for lvl in body["levels"]}
    assert by_item[item_ids[0]]["qty"] == 7
    assert by_item[item_ids[1]]["qty"] == 5
    assert by_item[item_ids[2]]["qty"] == 3
    assert all(lvl["location_id"] == loc_a["id"] for lvl in body["levels"])


def test_location_stock_omits_zero_qty_levels(client, item, loc_a):
    _receive(client, item["id"], loc_a["id"], 4)
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 4, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    body = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert body == {"location_id": loc_a["id"], "levels": []}
