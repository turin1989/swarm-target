"""Locations, movements, stock levels."""

import re

import pytest

ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


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


def test_movement_with_reference_is_stored_and_returned(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        to_location_id=loc_a["id"],
        reference="PO-12345",
    )
    assert r.status_code == 201
    body = r.json()
    assert body["reference"] == "PO-12345"

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
        reference="x" * 64,
    )
    assert ok.status_code == 201
    assert ok.json()["reference"] == "x" * 64

    too_long = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        reference="x" * 65,
    )
    assert too_long.status_code == 422


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


def test_list_movements_filter_by_item_id(client, item, item2, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item2["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])

    r = client.get("/movements", params={"item_id": item["id"]})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(m["item_id"] == item["id"] for m in body)

    r2 = client.get("/movements", params={"item_id": item2["id"]})
    assert [m["item_id"] for m in r2.json()] == [item2["id"]]


def test_list_movements_filter_by_kind(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])

    r = client.get("/movements", params={"kind": "ship"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert all(m["kind"] == "ship" for m in body)


def test_list_movements_invalid_kind_422(client):
    assert client.get("/movements", params={"kind": "explode"}).status_code == 422


def test_list_movements_filters_combine_with_pagination(client, item, item2, loc_a):
    for _ in range(3):
        _move(client, item_id=item["id"], kind="receive", qty=2, to_location_id=loc_a["id"])
        _move(client, item_id=item2["id"], kind="receive", qty=2, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])

    r = client.get("/movements", params={"item_id": item["id"], "kind": "receive"})
    body = r.json()
    assert len(body) == 3
    assert all(m["item_id"] == item["id"] and m["kind"] == "receive" for m in body)

    paged = client.get(
        "/movements",
        params={"item_id": item["id"], "kind": "receive", "limit": 2, "offset": 1},
    ).json()
    assert [m["id"] for m in paged] == [m["id"] for m in body[1:3]]


def test_get_movement_by_id(client, item, loc_a):
    created = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        to_location_id=loc_a["id"],
        reference="PO-1",
    ).json()
    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_movement_unknown_id_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "movement 999 not found"


# --- insufficient stock -------------------------------------------------------


def test_ship_more_than_on_hand_409(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=6, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]


def test_ship_from_empty_location_409(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]


def test_ship_exactly_on_hand_is_allowed(client, item, loc_a):
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
    assert "insufficient" in r.json()["detail"]


def test_rejected_movement_writes_nothing(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])

    assert (
        _move(
            client, item_id=item["id"], kind="ship", qty=9, from_location_id=loc_a["id"]
        ).status_code
        == 409
    )
    assert (
        _move(
            client,
            item_id=item["id"],
            kind="transfer",
            qty=9,
            from_location_id=loc_a["id"],
            to_location_id=loc_b["id"],
        ).status_code
        == 409
    )

    # No movement rows were written for the rejected requests.
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"

    # Stock levels are unchanged.
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]


def test_transfer_moves_stock_to_destination(client, item, loc_a, loc_b):
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
    assert s["total"] == 5
    assert [lvl["qty"] for lvl in s["levels"]] == [3, 2]


# --- adjust -------------------------------------------------------------------


def test_adjust_sets_stock_to_absolute_qty(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=4, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "adjust"
    assert body["qty"] == 4
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 4
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 4}]


def test_adjust_can_increase_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=9, to_location_id=loc_a["id"])
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 9


def test_adjust_sets_stock_from_zero(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=7, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 7
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 7}]


def test_adjust_only_affects_target_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=8, to_location_id=loc_b["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=2, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 7
    assert [lvl["qty"] for lvl in s["levels"]] == [5, 2]


def test_adjust_requires_to_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=5)
    assert r.status_code == 400
    assert "required" in r.json()["detail"]


def test_adjust_rejects_from_location(client, item, loc_a, loc_b):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=5,
        to_location_id=loc_b["id"],
        from_location_id=loc_a["id"],
    )
    assert r.status_code == 400
    assert "from_location_id" in r.json()["detail"]


def test_adjust_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=123)
    assert r.status_code == 404


def test_adjust_is_recorded_and_listable_by_kind(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    created = _move(
        client, item_id=item["id"], kind="adjust", qty=2, to_location_id=loc_a["id"]
    ).json()
    assert client.get(f"/movements/{created['id']}").json() == created

    r = client.get("/movements", params={"kind": "adjust"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["kind"] == "adjust"
    assert body[0]["qty"] == 2


def test_adjust_cannot_be_reversed(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="adjust", qty=5, to_location_id=loc_a["id"]
    ).json()
    r = client.post(f"/movements/{created['id']}/reverse")
    assert r.status_code == 400
    # stock is untouched by the failed reversal
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


# --- created_at ---------------------------------------------------------------


def test_movement_sets_created_at(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert "created_at" in body
    assert ISO_UTC_RE.match(body["created_at"]), body["created_at"]


def test_movement_created_at_returned_by_all_movement_endpoints(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"]
    ).json()
    created_at = created["created_at"]
    assert ISO_UTC_RE.match(created_at)

    assert client.get(f"/movements/{created['id']}").json()["created_at"] == created_at
    assert client.get("/movements").json()[0]["created_at"] == created_at


# --- reverse ------------------------------------------------------------------


def test_reverse_receive_creates_ship(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"]
    ).json()
    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != original["id"]
    assert body["kind"] == "ship"
    assert body["qty"] == 10
    assert body["from_location_id"] == loc_a["id"]
    assert body["to_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"

    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_reverse_ship_creates_receive(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    original = _move(
        client, item_id=item["id"], kind="ship", qty=4, from_location_id=loc_a["id"]
    ).json()
    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "receive"
    assert body["qty"] == 4
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"

    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_reverse_transfer_swaps_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    original = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    ).json()
    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "transfer"
    assert body["qty"] == 2
    assert body["from_location_id"] == loc_b["id"]
    assert body["to_location_id"] == loc_a["id"]
    assert body["note"] == f"reversal of {original['id']}"


def test_reverse_movement_is_persisted(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"]
    ).json()
    created = client.post(f"/movements/{original['id']}/reverse").json()
    assert client.get(f"/movements/{created['id']}").json() == created


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404
    assert r.json()["detail"] == "movement 999 not found"


def test_list_movements_filter_no_matches(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    assert client.get("/movements", params={"kind": "transfer"}).json() == []
    assert client.get("/movements", params={"item_id": 999}).json() == []


def test_note_too_long_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note="x" * 501,
    )
    assert r.status_code == 422


def test_note_at_max_length_accepted(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        note="x" * 500,
    )
    assert r.status_code == 201
    assert r.json()["note"] == "x" * 500
