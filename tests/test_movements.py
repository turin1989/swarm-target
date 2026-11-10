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


def test_transfer_same_location_rejected(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 400
    assert "same location" in r.json()["detail"]
    # no movement row is written for the rejected transfer
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"
    # stock is untouched
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]


def test_ship_more_than_on_hand_rejected_409(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=6, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]
    # no movement row is written for the rejected ship
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"
    # stock is untouched (never driven negative)
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]


def test_ship_from_empty_location_rejected_409(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_ship_exactly_on_hand_succeeds(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=5, from_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_transfer_more_than_source_stock_rejected_409(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]
    # no movement row is written for the rejected transfer
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"
    # stock levels are unchanged at both locations
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 3}]


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


def test_movement_note_too_long_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note="x" * 501,
    )
    assert r.status_code == 422


def test_movement_note_max_length_allowed(client, item, loc_a):
    note = "x" * 500
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note=note,
    )
    assert r.status_code == 201
    assert r.json()["note"] == note


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


@pytest.fixture()
def item2(client):
    r = client.post(
        "/items",
        json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0, "reorder_point": 2},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def mixed_movements(client, item, item2, loc_a):
    """Movements: item receive x2, item ship x1, item2 receive x1, item2 ship x1."""
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])
    _move(client, item_id=item2["id"], kind="receive", qty=4, to_location_id=loc_a["id"])
    _move(client, item_id=item2["id"], kind="ship", qty=1, from_location_id=loc_a["id"])


def test_list_movements_filter_by_item_id(client, item, item2, mixed_movements):
    r = client.get("/movements", params={"item_id": item["id"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert all(m["item_id"] == item["id"] for m in body)

    r2 = client.get("/movements", params={"item_id": item2["id"]})
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2) == 2
    assert all(m["item_id"] == item2["id"] for m in body2)


def test_list_movements_filter_by_kind(client, item, item2, mixed_movements):
    r = client.get("/movements", params={"kind": "ship"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(m["kind"] == "ship" for m in body)

    r2 = client.get("/movements", params={"kind": "receive"})
    assert r2.status_code == 200
    assert [m["kind"] for m in r2.json()] == ["receive"] * 3


def test_list_movements_invalid_kind_422(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"kind": "explode"})
    assert r.status_code == 422


def test_list_movements_filters_combine(client, item, item2, mixed_movements):
    r = client.get("/movements", params={"item_id": item["id"], "kind": "receive"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(m["item_id"] == item["id"] and m["kind"] == "receive" for m in body)

    r2 = client.get("/movements", params={"item_id": item2["id"], "kind": "ship"})
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2) == 1
    assert body2[0]["item_id"] == item2["id"]
    assert body2[0]["kind"] == "ship"


def test_list_movements_filter_with_pagination(client, item, item2, mixed_movements):
    # item has 3 movements (ids 1, 2, 3): filter + paginate within the filtered set
    r = client.get(
        "/movements", params={"item_id": item["id"], "limit": 2, "offset": 1}
    )
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == [2, 3]
    assert all(m["item_id"] == item["id"] for m in body)

    # combined filters + pagination
    r2 = client.get(
        "/movements",
        params={"item_id": item["id"], "kind": "receive", "limit": 1, "offset": 1},
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2) == 1
    assert body2[0]["id"] == 2
    assert body2[0]["kind"] == "receive"


def test_list_movements_filter_no_matches(client, item, mixed_movements):
    r = client.get("/movements", params={"item_id": 999})
    assert r.status_code == 200
    assert r.json() == []
