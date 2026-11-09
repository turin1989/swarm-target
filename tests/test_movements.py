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


def test_update_location_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "Main Warehouse", "code": "WH-MAIN"}
    )
    assert r.status_code == 200
    assert r.json() == {"id": loc_a["id"], "code": "WH-MAIN", "name": "Main Warehouse"}
    # persisted
    assert client.get(f"/locations/{loc_a['id']}").json() == r.json()


def test_update_location_partial(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json() == {"id": loc_a["id"], "code": "WH-A", "name": "Renamed"}

    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-X"})
    assert r.status_code == 200
    assert r.json() == {"id": loc_a["id"], "code": "WH-X", "name": "Renamed"}


def test_update_location_empty_payload_is_noop(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200
    assert r.json() == loc_a


def test_update_location_unknown_id_404(client):
    assert client.put("/locations/999", json={"name": "nope"}).status_code == 404


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


def test_ship_more_than_on_hand_rejected_409(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=6, from_location_id=loc_a["id"])
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]
    # no movement row written and stock unchanged
    movements = client.get("/movements").json()
    assert len(movements) == 1
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]


def test_ship_from_empty_location_rejected_409(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_ship_exact_stock_allowed(client, item, loc_a):
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
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]
    # no movement row written and stock unchanged
    movements = client.get("/movements").json()
    assert len(movements) == 1  # only the receive
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 3}]


def test_transfer_checks_source_not_destination(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_b["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]

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
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]


def test_movement_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=123)
    assert r.status_code == 404


def test_movement_unknown_item_404(client, loc_a):
    r = _move(client, item_id=123, kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 404


@pytest.mark.parametrize("qty", [0, -1, -10])
def test_movement_non_positive_qty_422(client, item, loc_a, qty):
    r = _move(client, item_id=item["id"], kind="receive", qty=qty, to_location_id=loc_a["id"])
    assert r.status_code == 422
    # no movement row was written and stock is untouched
    assert client.get("/movements").json() == []
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 0
    assert s["levels"] == []


def test_movement_invalid_kind_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="explode", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 422


def test_movement_has_created_at(client, item, loc_a):
    from datetime import datetime, timezone

    before = datetime.now(timezone.utc)
    r = _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    after = datetime.now(timezone.utc)
    assert r.status_code == 201
    body = r.json()
    assert "created_at" in body
    created = datetime.fromisoformat(body["created_at"])
    assert created.tzinfo is not None
    assert created.utcoffset().total_seconds() == 0  # UTC
    assert before <= created <= after

    # also present when listing movements
    movements = client.get("/movements").json()
    assert movements[0]["created_at"] == body["created_at"]


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


# --- item movements ------------------------------------------------------------


def test_item_movements_only_returns_that_items_history(client, item, loc_a):
    other = client.post(
        "/items",
        json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0, "reorder_point": 2},
    ).json()
    _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    _move(client, item_id=other["id"], kind="receive", qty=9, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])

    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == [1, 3]
    assert all(m["item_id"] == item["id"] for m in body)
    assert [m["kind"] for m in body] == ["receive", "ship"]


def test_item_movements_pagination(client, item, loc_a):
    for _ in range(5):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [2, 3]


def test_item_movements_empty_for_fresh_item(client, item):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    assert r.json() == []


def test_item_movements_unknown_item_404(client):
    r = client.get("/items/999/movements")
    assert r.status_code == 404
