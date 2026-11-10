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


@pytest.mark.parametrize(
    "code",
    ["WH-A", "A", "0", "WH-1-SUB-2", "X" * 32, "A" + "-" * 31],
)
def test_location_code_valid_formats(client, code):
    r = client.post("/locations", json={"code": code, "name": "Loc"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == code


@pytest.mark.parametrize(
    "code",
    [
        "wh-a",  # lowercase not allowed
        "-WH",  # cannot start with a hyphen
        "WH A",  # spaces not allowed
        "WH_A",  # underscore not allowed
        "",  # empty
        "X" * 33,  # too long
        "WH.A",  # dot not allowed
        "ВН-А",  # non-ASCII letters not allowed
    ],
)
def test_location_code_invalid_formats(client, code):
    r = client.post("/locations", json={"code": code, "name": "Loc"})
    assert r.status_code == 422, r.text


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
    assert "same location" in r.json()["error"]["message"]
    assert r.json()["error"]["code"] == "bad_request"


def test_transfer_same_location_writes_no_movement(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    before = client.get("/movements").json()
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_a["id"],
    )
    after = client.get("/movements").json()
    assert after == before
    assert len(after) == 1  # only the initial receive
    # stock is untouched as well
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]


def test_ship_more_than_on_hand_409(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=6, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["error"]["message"]


def test_ship_from_empty_location_409(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["error"]["message"]


def test_ship_exact_stock_allowed(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=5, from_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_transfer_more_than_source_stock_409(client, item, loc_a, loc_b):
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
    assert "insufficient" in r.json()["error"]["message"]


def test_insufficient_stock_writes_no_movement_and_leaves_stock_unchanged(
    client, item, loc_a, loc_b
):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    before_movements = client.get("/movements").json()
    before_stock = client.get(f"/items/{item['id']}/stock").json()

    r = _move(client, item_id=item["id"], kind="ship", qty=99, from_location_id=loc_a["id"])
    assert r.status_code == 409
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=99,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409

    assert client.get("/movements").json() == before_movements
    assert len(before_movements) == 1  # only the initial receive
    assert client.get(f"/items/{item['id']}/stock").json() == before_stock


def test_stock_never_goes_negative_via_ship(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=2, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    assert r.status_code == 409
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 0
    assert all(lvl["qty"] >= 0 for lvl in s["levels"])


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
    assert "required" in r.json()["error"]["message"]
    assert r.json()["error"]["code"] == "bad_request"


def test_movement_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=123)
    assert r.status_code == 404


def test_movement_unknown_item_404(client, loc_a):
    r = _move(client, item_id=123, kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 404


def test_movement_invalid_kind_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="explode", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 422


@pytest.mark.parametrize("qty", [0, -1, -10])
@pytest.mark.parametrize("kind", ["receive", "ship", "transfer"])
def test_movement_non_positive_qty_422(client, item, loc_a, loc_b, kind, qty):
    r = _move(
        client,
        item_id=item["id"],
        kind=kind,
        qty=qty,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 422


def test_non_positive_qty_writes_no_movement_row(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=0, to_location_id=loc_a["id"])
    assert r.status_code == 422
    r = _move(client, item_id=item["id"], kind="receive", qty=-5, to_location_id=loc_a["id"])
    assert r.status_code == 422
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


@pytest.fixture()
def item2(client):
    r = client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def mixed_movements(client, item, item2, loc_a):
    """Create a mix of movements across two items and two kinds."""
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])  # id 1
    _move(client, item_id=item2["id"], kind="receive", qty=10, to_location_id=loc_a["id"])  # id 2
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])  # id 3
    _move(client, item_id=item2["id"], kind="ship", qty=2, from_location_id=loc_a["id"])  # id 4
    _move(client, item_id=item["id"], kind="ship", qty=3, from_location_id=loc_a["id"])  # id 5
    _move(client, item_id=item["id"], kind="ship", qty=4, from_location_id=loc_a["id"])  # id 6


def test_filter_movements_by_item_id(client, item, item2, mixed_movements):
    r = client.get("/movements", params={"item_id": item["id"]})
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [1, 3, 5, 6]
    assert all(m["item_id"] == item["id"] for m in movements)

    r2 = client.get("/movements", params={"item_id": item2["id"]})
    assert [m["id"] for m in r2.json()] == [2, 4]


def test_filter_movements_by_kind(client, item, item2, mixed_movements):
    r = client.get("/movements", params={"kind": "ship"})
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [3, 4, 5, 6]
    assert all(m["kind"] == "ship" for m in movements)

    r2 = client.get("/movements", params={"kind": "receive"})
    assert [m["id"] for m in r2.json()] == [1, 2]


def test_filter_movements_invalid_kind_422(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"kind": "explode"})
    assert r.status_code == 422


def test_filter_movements_combined(client, item, item2, mixed_movements):
    r = client.get("/movements", params={"item_id": item["id"], "kind": "ship"})
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [3, 5, 6]
    assert all(m["item_id"] == item["id"] and m["kind"] == "ship" for m in movements)


def test_filter_movements_combined_with_pagination(client, item, item2, mixed_movements):
    r = client.get(
        "/movements",
        params={"item_id": item["id"], "kind": "ship", "limit": 2, "offset": 1},
    )
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [5, 6]


def test_filter_movements_no_matches(client, item, mixed_movements):
    r = client.get("/movements", params={"item_id": 999})
    assert r.status_code == 200
    assert r.json() == []


def test_note_at_max_length_accepted(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note="n" * 500,
    )
    assert r.status_code == 201, r.text
    assert r.json()["note"] == "n" * 500


def test_note_over_max_length_rejected(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note="n" * 501,
    )
    assert r.status_code == 422, r.text
