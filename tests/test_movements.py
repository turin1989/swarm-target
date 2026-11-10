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
    r = _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["kind"] == "receive"
    assert body["quantity"] == 10
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 10
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 10}]


def test_receive_accumulates(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=6, to_location_id=loc_a["id"])
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_ship_decreases_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", quantity=3, from_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 7


def test_stock_split_across_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=7, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 12
    assert [lvl["quantity"] for lvl in s["levels"]] == [5, 7]


def test_transfer_is_recorded(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
        note="rebalance",
    )
    assert r.status_code == 201
    assert r.json()["note"] == "rebalance"
    movements = client.get("/movements").json()
    assert len(movements) == 2
    assert movements[1]["kind"] == "transfer"


def test_transfer_moves_stock_between_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201

    s = client.get(f"/items/{item['id']}/stock").json()
    # total stock is unchanged by a transfer
    assert s["total"] == 5
    # from_location decreases by N, to_location increases by N
    levels = {lvl["location_id"]: lvl["quantity"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 3
    assert levels[loc_b["id"]] == 2


def test_transfer_same_location_rejected(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "same location" in body["error"]["message"]
    # no movement row written for the rejected transfer
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"
    # stock is unchanged
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


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
    r = _move(client, item_id=item["id"], kind=kind, quantity=1, **payload)
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]


def test_movement_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=123)
    assert r.status_code == 404


def test_movement_unknown_item_404(client, loc_a):
    r = _move(client, item_id=123, kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 404


def test_movement_invalid_kind_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="explode", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 422


def test_movement_rejected_for_inactive_item(client, item, loc_a):
    # seed some stock while the item is still active
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    client.put(f"/items/{item['id']}", json={"active": False})

    r = _move(client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"])
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    # the error detail mentions the item is inactive
    assert "inactive" in body["error"]["message"]
    assert "inactive" in r.text

    # stock levels are unchanged
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 5}]

    # no movement row was written for the rejected movement
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
    ],
)
def test_all_movement_kinds_rejected_for_inactive_item(client, item, loc_a, loc_b, kind, payload):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    client.put(f"/items/{item['id']}", json={"active": False})

    r = _move(client, item_id=item["id"], kind=kind, quantity=2, **payload)
    assert r.status_code == 409
    assert "inactive" in r.json()["error"]["message"]
    # stock is unchanged for every rejected kind
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_movement_allowed_again_after_reactivation(client, item, loc_a):
    client.put(f"/items/{item['id']}", json={"active": False})
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 409

    client.put(f"/items/{item['id']}", json={"active": True})
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 1


def test_movement_with_old_qty_field_rejected_422(client, item, loc_a):
    """The old field name ``qty`` is no longer accepted."""
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movement_with_both_qty_and_quantity_rejected_422(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "qty": 1,
            "quantity": 1,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 422
    assert client.get("/movements").json() == []


def test_movement_and_stock_responses_use_quantity_not_qty(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["quantity"] == 4
    assert "qty" not in body

    listed = client.get("/movements").json()
    assert listed[0]["quantity"] == 4
    assert "qty" not in listed[0]

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 4}]
    assert "qty" not in s["levels"][0]


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


@pytest.mark.parametrize("quantity", [0, -1, -10])
def test_movement_non_positive_quantity_rejected_422(client, item, loc_a, quantity):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=quantity,
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 422
    # no movement row is written
    assert client.get("/movements").json() == []
    # stock is unchanged
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
    ],
)
def test_all_movement_kinds_reject_zero_quantity(client, item, loc_a, loc_b, kind, payload):
    r = _move(client, item_id=item["id"], kind=kind, quantity=0, **payload)
    assert r.status_code == 422
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_apply_movement_rejects_non_positive_quantity_in_service():
    """The service layer also guards against qty <= 0 when bypassing the model."""
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.errors import ValidationError
    from inventory.services.stock import apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    bad = MovementCreate.model_construct(
        item_id=1, kind="receive", quantity=0, from_location_id=None, to_location_id=1, note=""
    )
    with pytest.raises(ValidationError):
        apply_movement(conn, bad)
    assert conn.execute("SELECT COUNT(*) AS c FROM movements").fetchone()["c"] == 0


def test_movement_note_longer_than_500_chars_rejected_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        note="x" * 501,
    )
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movement_note_exactly_500_chars_accepted(client, item, loc_a):
    note = "x" * 500
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        note=note,
    )
    assert r.status_code == 201
    assert r.json()["note"] == note
