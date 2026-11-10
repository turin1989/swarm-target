"""Locations, movements, stock levels."""

import pytest


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_create_and_list_locations(client, loc_a, loc_b):
    r = client.get("/locations")
    assert r.status_code == 200
    assert [loc["code"] for loc in r.json()] == ["WH-A", "WH-B"]
    assert loc_a == {"id": 1, "code": "WH-A", "name": "Warehouse A", "active": True}


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


def test_transfer_moves_stock_between_locations(client, item, loc_a, loc_b):
    """T003: transfer debits from_location and credits to_location."""
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201

    s = client.get(f"/items/{item['id']}/stock").json()
    # total stock is unchanged by the transfer
    assert s["total"] == 5
    # source decreased by 2, destination increased by 2; both locations visible
    assert s["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "qty": 3},
        {"item_id": item["id"], "location_id": loc_b["id"], "qty": 2},
    ]


def test_transfer_entire_stock_empties_source(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=4, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 4
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 0
    assert levels[loc_b["id"]] == 4


def test_repeated_transfers_accumulate_at_destination(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    for _ in range(3):
        r = _move(
            client,
            item_id=item["id"],
            kind="transfer",
            qty=2,
            from_location_id=loc_a["id"],
            to_location_id=loc_b["id"],
        )
        assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 10
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 4
    assert levels[loc_b["id"]] == 6


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
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]
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
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]
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
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]
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


# --- non-positive quantities rejected (T040) ------------------------------------


@pytest.mark.parametrize("qty", [0, -1, -100])
@pytest.mark.parametrize(
    "kind,locations",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
        ("adjust", {"to_location_id": 1}),
    ],
)
def test_movement_non_positive_qty_rejected_422(client, item, loc_a, loc_b, kind, locations, qty):
    r = _move(client, item_id=item["id"], kind=kind, qty=qty, **locations)
    assert r.status_code == 422
    # no movement row is written
    assert client.get("/movements").json() == []
    # and stock is untouched
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movement_non_positive_qty_does_not_write_row_with_existing_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=0, from_location_id=loc_a["id"])
    assert r.status_code == 422
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]


def test_movement_positive_qty_still_accepted(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert r.json()["qty"] == 1


# --- adjust movements (T039) ---------------------------------------------------


def test_adjust_sets_absolute_stock_from_empty(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=7, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "adjust"
    assert body["qty"] == 7
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 7
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 7}]


def test_adjust_overwrites_existing_stock_not_a_delta(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=3, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    # absolute set: 3, not 10 + 3
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 3}]


def test_adjust_only_affects_target_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=9, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 14
    assert s["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "qty": 5},
        {"item_id": item["id"], "location_id": loc_b["id"], "qty": 9},
    ]


def test_adjust_requires_to_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=1)
    assert r.status_code == 400
    assert "required" in r.json()["error"]["message"]
    assert client.get("/movements").json() == []


def test_adjust_rejects_from_location(client, item, loc_a, loc_b):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=1,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 400
    assert "from_location_id must be null" in r.json()["error"]["message"]
    # nothing is recorded and no stock changes
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_adjust_is_recorded_with_kind_adjust(client, item, loc_a):
    _move(client, item_id=item["id"], kind="adjust", qty=4, to_location_id=loc_a["id"])
    movements = client.get("/movements").json()
    assert len(movements) == 1
    m = movements[0]
    assert m["kind"] == "adjust"
    assert m["qty"] == 4
    assert m["to_location_id"] == loc_a["id"]
    assert m["from_location_id"] is None

    # also visible in the per-item history
    hist = client.get(f"/items/{item['id']}/movements").json()
    assert [h["kind"] for h in hist] == ["adjust"]


def test_adjust_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="adjust", qty=1, to_location_id=321)
    assert r.status_code == 404


# --- per-item movement history (T032) -----------------------------------------


def test_item_movements_lists_only_that_item_ordered_by_id(client, item, loc_a):
    other = client.post(
        "/items",
        json={"sku": "OTHER-1", "name": "Other", "unit_price": 1.0, "reorder_point": 1},
    ).json()
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=other["id"], kind="receive", qty=2, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])

    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    body = r.json()
    assert [m["item_id"] for m in body] == [item["id"], item["id"]]
    assert [m["id"] for m in body] == [1, 3]
    assert [m["kind"] for m in body] == ["receive", "ship"]

    r = client.get(f"/items/{other['id']}/movements")
    assert [m["id"] for m in r.json()] == [2]


def test_item_movements_empty_for_item_without_movements(client, item):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    assert r.json() == []


def test_item_movements_pagination(client, item, loc_a):
    for _ in range(5):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [2, 3]
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 10, "offset": 4})
    assert [m["id"] for m in r.json()] == [5]


def test_item_movements_unknown_item_404(client):
    r = client.get("/items/999/movements")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "not found" in body["error"]["message"]


def test_item_movements_invalid_pagination_422(client, item):
    assert client.get(f"/items/{item['id']}/movements", params={"limit": 0}).status_code == 422
    assert client.get(f"/items/{item['id']}/movements", params={"offset": -1}).status_code == 422


# --- GET /movements filters (T044) ----------------------------------------------


@pytest.fixture
def mixed_movements(client, item, loc_a, loc_b):
    """Two items with a mix of movement kinds; returns both item dicts."""
    other = client.post(
        "/items",
        json={"sku": "OTHER-44", "name": "Other", "unit_price": 1.0, "reorder_point": 1},
    ).json()
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])  # id 1
    _move(client, item_id=other["id"], kind="receive", qty=5, to_location_id=loc_a["id"])  # id 2
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])  # id 3
    _move(client, item_id=other["id"], kind="ship", qty=1, from_location_id=loc_a["id"])  # id 4
    _move(  # id 5
        client,
        item_id=item["id"],
        kind="transfer",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])  # id 6
    return item, other


def test_list_movements_filter_by_item_id(client, mixed_movements):
    item, other = mixed_movements
    r = client.get("/movements", params={"item_id": item["id"]})
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == [1, 3, 5, 6]
    assert all(m["item_id"] == item["id"] for m in body)

    r = client.get("/movements", params={"item_id": other["id"]})
    assert [m["id"] for m in r.json()] == [2, 4]


def test_list_movements_filter_by_item_id_unknown_item_empty(client, mixed_movements):
    r = client.get("/movements", params={"item_id": 9999})
    assert r.status_code == 200
    assert r.json() == []


def test_list_movements_filter_by_kind(client, mixed_movements):
    r = client.get("/movements", params={"kind": "ship"})
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == [3, 4, 6]
    assert all(m["kind"] == "ship" for m in body)

    r = client.get("/movements", params={"kind": "transfer"})
    assert [m["id"] for m in r.json()] == [5]

    r = client.get("/movements", params={"kind": "adjust"})
    assert r.json() == []


def test_list_movements_invalid_kind_422(client, mixed_movements):
    r = client.get("/movements", params={"kind": "explode"})
    assert r.status_code == 422


def test_list_movements_filters_combine(client, mixed_movements):
    item, other = mixed_movements
    r = client.get("/movements", params={"item_id": item["id"], "kind": "ship"})
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == [3, 6]
    assert all(m["item_id"] == item["id"] and m["kind"] == "ship" for m in body)

    r = client.get("/movements", params={"item_id": other["id"], "kind": "transfer"})
    assert r.json() == []


def test_list_movements_filters_with_pagination(client, mixed_movements):
    item, _ = mixed_movements
    r = client.get(
        "/movements", params={"item_id": item["id"], "limit": 2, "offset": 1}
    )
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [3, 5]

    r = client.get("/movements", params={"kind": "ship", "limit": 2, "offset": 1})
    assert [m["id"] for m in r.json()] == [4, 6]

    r = client.get(
        "/movements",
        params={"item_id": item["id"], "kind": "ship", "limit": 1, "offset": 1},
    )
    assert [m["id"] for m in r.json()] == [6]


def test_list_movements_no_filters_returns_all(client, mixed_movements):
    r = client.get("/movements")
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [1, 2, 3, 4, 5, 6]


# --- movements rejected for inactive items (T041) --------------------------------


@pytest.fixture
def inactive_item(client, item, loc_a):
    """An item with existing stock that has been deactivated."""
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = client.put(f"/items/{item['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    return r.json()


@pytest.mark.parametrize(
    "kind,locations",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
        ("adjust", {"to_location_id": 1}),
    ],
)
def test_movement_for_inactive_item_rejected_409(
    client, inactive_item, loc_a, loc_b, kind, locations
):
    r = _move(client, item_id=inactive_item["id"], kind=kind, qty=1, **locations)
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "inactive" in body["error"]["message"]


def test_movement_for_inactive_item_leaves_stock_unchanged(
    client, inactive_item, loc_a, loc_b
):
    before = client.get(f"/items/{inactive_item['id']}/stock").json()
    assert before["total"] == 5

    for kind, locations in [
        ("receive", {"to_location_id": loc_a["id"]}),
        ("ship", {"from_location_id": loc_a["id"]}),
        (
            "transfer",
            {"from_location_id": loc_a["id"], "to_location_id": loc_b["id"]},
        ),
        ("adjust", {"to_location_id": loc_a["id"]}),
    ]:
        r = _move(client, item_id=inactive_item["id"], kind=kind, qty=3, **locations)
        assert r.status_code == 409

    after = client.get(f"/items/{inactive_item['id']}/stock").json()
    assert after == before
    assert after["total"] == 5
    assert after["levels"] == [
        {"item_id": inactive_item["id"], "location_id": loc_a["id"], "qty": 5}
    ]


def test_movement_for_inactive_item_writes_no_movement_row(client, inactive_item, loc_a):
    r = _move(
        client, item_id=inactive_item["id"], kind="receive", qty=1, to_location_id=loc_a["id"]
    )
    assert r.status_code == 409
    movements = client.get("/movements").json()
    assert len(movements) == 1  # only the original receive from the fixture
    assert movements[0]["kind"] == "receive"


def test_movement_allowed_again_after_reactivation(client, inactive_item, loc_a):
    r = client.put(f"/items/{inactive_item['id']}", json={"active": True})
    assert r.status_code == 200
    r = _move(
        client, item_id=inactive_item["id"], kind="receive", qty=2, to_location_id=loc_a["id"]
    )
    assert r.status_code == 201
    assert client.get(f"/items/{inactive_item['id']}/stock").json()["total"] == 7
