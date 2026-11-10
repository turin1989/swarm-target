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


def test_delete_location(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404
    assert client.get("/locations").json() == []


def test_delete_location_unknown_id_404(client):
    assert client.delete("/locations/99").status_code == 404


def test_delete_location_with_stock_409(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409
    # location is still there
    assert client.get(f"/locations/{loc_a['id']}").status_code == 200


def test_delete_location_with_zero_qty_stock_row_ok(client, item, loc_a):
    # Receiving then shipping everything leaves a stock_levels row with qty == 0.
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=5, from_location_id=loc_a["id"])
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


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
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]


def test_movement_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=123)
    assert r.status_code == 404


def test_movement_unknown_item_404(client, loc_a):
    r = _move(client, item_id=123, kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 404


def test_movement_invalid_kind_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="explode", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 422


def test_movement_reference_stored_and_returned(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        to_location_id=loc_a["id"],
        reference="PO-12345",
    )
    assert r.status_code == 201
    assert r.json()["reference"] == "PO-12345"

    movements = client.get("/movements").json()
    assert movements[0]["reference"] == "PO-12345"


def test_movement_reference_defaults_to_none(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert r.json()["reference"] is None
    assert client.get("/movements").json()[0]["reference"] is None


def test_movement_reference_max_length_64(client, item, loc_a):
    ok = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        reference="R" * 64,
    )
    assert ok.status_code == 201
    assert ok.json()["reference"] == "R" * 64

    too_long = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        reference="R" * 65,
    )
    assert too_long.status_code == 422


def test_get_movement_by_id(client, item, loc_a):
    created = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        to_location_id=loc_a["id"],
        note="initial",
        reference="PO-1",
    ).json()
    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    # same shape (and content) as the POST response
    assert r.json() == created


def test_get_movement_unknown_id_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    # uniform error shape (T050): {"error": {"code": ..., "message": ...}}
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "movement 999 not found"


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


@pytest.mark.parametrize("qty", [0, -1, -10])
@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
    ],
)
def test_movement_non_positive_qty_422(client, item, loc_a, loc_b, kind, payload, qty):
    r = _move(client, item_id=item["id"], kind=kind, qty=qty, **payload)
    assert r.status_code == 422
    # no movement row is written
    assert client.get("/movements").json() == []


def test_movement_non_positive_qty_leaves_stock_untouched(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=0, from_location_id=loc_a["id"])
    assert r.status_code == 422

    # only the initial receive exists; stock is unchanged
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


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
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "same location" in body["error"]["message"]

    # no movement row was written for the rejected transfer
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"

    # stock is untouched
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]


# --- GET /movements filters (T044) --------------------------------------------


def _seed_movements(client, item, loc_a, loc_b):
    """Create a second item plus a mix of movements for both items."""
    item2 = client.post(
        "/items",
        json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0, "reorder_level": 2},
    ).json()
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    _move(client, item_id=item2["id"], kind="receive", qty=8, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])
    _move(client, item_id=item2["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    return item2


def test_list_movements_filter_by_item_id(client, item, loc_a, loc_b):
    item2 = _seed_movements(client, item, loc_a, loc_b)

    r = client.get("/movements", params={"item_id": item["id"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert all(m["item_id"] == item["id"] for m in body)

    r2 = client.get("/movements", params={"item_id": item2["id"]})
    assert r2.status_code == 200
    assert [m["item_id"] for m in r2.json()] == [item2["id"], item2["id"]]


def test_list_movements_filter_by_item_id_no_matches(client, item, loc_a, loc_b):
    _seed_movements(client, item, loc_a, loc_b)
    r = client.get("/movements", params={"item_id": 9999})
    assert r.status_code == 200
    assert r.json() == []


def test_list_movements_filter_by_kind(client, item, loc_a, loc_b):
    _seed_movements(client, item, loc_a, loc_b)

    r = client.get("/movements", params={"kind": "ship"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(m["kind"] == "ship" for m in body)

    r2 = client.get("/movements", params={"kind": "transfer"})
    assert [m["kind"] for m in r2.json()] == ["transfer"]


def test_list_movements_invalid_kind_422(client, item, loc_a, loc_b):
    _seed_movements(client, item, loc_a, loc_b)
    r = client.get("/movements", params={"kind": "explode"})
    assert r.status_code == 422


def test_list_movements_filters_combine(client, item, loc_a, loc_b):
    item2 = _seed_movements(client, item, loc_a, loc_b)

    r = client.get("/movements", params={"item_id": item["id"], "kind": "ship"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["item_id"] == item["id"]
    assert body[0]["kind"] == "ship"

    # item2 never had a transfer
    r2 = client.get("/movements", params={"item_id": item2["id"], "kind": "transfer"})
    assert r2.status_code == 200
    assert r2.json() == []


def test_list_movements_filters_with_pagination(client, item, loc_a, loc_b):
    _seed_movements(client, item, loc_a, loc_b)
    for _ in range(3):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])

    # item has 4 receive movements total (ids 1, 6, 7, 8)
    all_ids = [
        m["id"]
        for m in client.get(
            "/movements", params={"item_id": item["id"], "kind": "receive"}
        ).json()
    ]
    assert len(all_ids) == 4

    page1 = client.get(
        "/movements",
        params={"item_id": item["id"], "kind": "receive", "limit": 2, "offset": 0},
    ).json()
    page2 = client.get(
        "/movements",
        params={"item_id": item["id"], "kind": "receive", "limit": 2, "offset": 2},
    ).json()
    assert [m["id"] for m in page1] == all_ids[:2]
    assert [m["id"] for m in page2] == all_ids[2:]
    assert all(m["item_id"] == item["id"] and m["kind"] == "receive" for m in page1 + page2)
