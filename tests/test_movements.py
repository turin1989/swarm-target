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


def test_transfer_moves_stock_between_locations(client, item, loc_a, loc_b):
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
    # total stock unchanged by a transfer
    assert s["total"] == 5
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    # source decreased by 2, destination increased by 2
    assert levels[loc_a["id"]] == 3
    assert levels[loc_b["id"]] == 2


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


def test_adjust_sets_absolute_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=3, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "adjust"
    assert body["qty"] == 3
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 3}]


def test_adjust_creates_level_when_none_exists(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=8, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 8
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 8}]


def test_adjust_only_affects_target_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=7, to_location_id=loc_b["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=1, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 6
    assert [lvl["qty"] for lvl in s["levels"]] == [5, 1]


def test_adjust_requires_to_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=1)
    assert r.status_code == 400
    assert "required" in r.json()["detail"]


def test_adjust_rejects_from_location(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=1,
        from_location_id=loc_a["id"],
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 400
    assert "from_location_id" in r.json()["detail"]


def test_adjust_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="adjust", qty=1, to_location_id=123)
    assert r.status_code == 404


def test_adjust_is_recorded_in_movement_list(client, item, loc_a):
    _move(client, item_id=item["id"], kind="adjust", qty=4, to_location_id=loc_a["id"])
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "adjust"
    assert movements[0]["qty"] == 4


@pytest.mark.parametrize("qty", [0, -1, -10])
def test_movement_non_positive_qty_422(client, item, loc_a, qty):
    r = _move(client, item_id=item["id"], kind="receive", qty=qty, to_location_id=loc_a["id"])
    assert r.status_code == 422
    # no movement row is written
    assert client.get("/movements").json() == []
    # and stock is untouched
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


@pytest.mark.parametrize("kind,locs", [
    ("ship", {"from_location_id": 1}),
    ("transfer", {"from_location_id": 1, "to_location_id": 2}),
])
def test_non_positive_qty_rejected_for_all_kinds(client, item, loc_a, loc_b, kind, locs):
    r = _move(client, item_id=item["id"], kind=kind, qty=0, **locs)
    assert r.status_code == 422
    assert client.get("/movements").json() == []


def test_adjust_non_positive_qty_422(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=0, to_location_id=loc_a["id"])
    assert r.status_code == 422
    # stock is untouched
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


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

    # returned on GET as well
    movements = client.get("/movements").json()
    assert movements[0]["reference"] == "PO-12345"


def test_movement_reference_defaults_to_none(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert r.json()["reference"] is None
    assert client.get("/movements").json()[0]["reference"] is None


def test_movement_reference_accepts_explicit_null(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        to_location_id=loc_a["id"],
        reference=None,
    )
    assert r.status_code == 201
    assert r.json()["reference"] is None


def test_movement_reference_max_64_chars(client, item, loc_a):
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
    # the rejected movement is not stored
    assert len(client.get("/movements").json()) == 1


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


def test_movement_note_max_500_chars(client, item, loc_a):
    ok = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note="N" * 500,
    )
    assert ok.status_code == 201
    assert ok.json()["note"] == "N" * 500

    too_long = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note="N" * 501,
    )
    assert too_long.status_code == 422
    # the rejected movement is not stored
    assert len(client.get("/movements").json()) == 1
