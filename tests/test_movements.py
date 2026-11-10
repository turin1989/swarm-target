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


def test_adjust_creates_level_when_missing(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=8, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 8
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 8}]


def test_adjust_only_touches_target_location(client, item, loc_a, loc_b):
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


@pytest.mark.parametrize("qty", [0, -1, -10])
@pytest.mark.parametrize("kind", ["receive", "ship", "transfer", "adjust"])
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
    # No movement row must be written.
    assert client.get("/movements").json() == []


def test_non_positive_qty_does_not_change_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=-3, from_location_id=loc_a["id"])
    assert r.status_code == 422
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5
    assert len(client.get("/movements").json()) == 1


def test_apply_movement_rejects_non_positive_qty_directly():
    """The shared stock service guards against qty <= 0 even when the
    Pydantic validation layer is bypassed."""
    from inventory.models import MovementCreate
    from inventory.services import stock

    bad = MovementCreate.model_construct(
        item_id=1,
        kind="receive",
        qty=0,
        from_location_id=None,
        to_location_id=1,
        note="",
    )
    with pytest.raises(stock.StockError) as exc_info:
        stock.apply_movement(conn=_fake_conn(), m=bad)
    assert exc_info.value.status_code == 422


class _fake_conn:
    """apply_movement must reject before touching the database."""

    def execute(self, *a, **kw):  # pragma: no cover - should never be called
        raise AssertionError("database must not be touched for invalid qty")


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


# --- get single movement ---------------------------------------------------------


def test_get_movement_matches_post_response(client, item, loc_a):
    created = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=7,
        to_location_id=loc_a["id"],
        note="restock",
    ).json()
    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_movement_unknown_id_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "movement 999 not found"


# --- per-item movement history -------------------------------------------------


def test_item_movements_only_returns_that_items_history(client, item, loc_a):
    other = client.post(
        "/items", json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0}
    ).json()
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=other["id"], kind="receive", qty=9, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])

    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == [1, 3]
    assert all(m["item_id"] == item["id"] for m in body)
    assert [m["kind"] for m in body] == ["receive", "ship"]


def test_item_movements_ordered_by_id(client, item, loc_a):
    for qty in (1, 2, 3):
        _move(client, item_id=item["id"], kind="receive", qty=qty, to_location_id=loc_a["id"])
    body = client.get(f"/items/{item['id']}/movements").json()
    assert [m["id"] for m in body] == [1, 2, 3]
    assert [m["qty"] for m in body] == [1, 2, 3]


def test_item_movements_pagination(client, item, loc_a):
    for _ in range(5):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 1})
    assert [m["id"] for m in r.json()] == [2, 3]
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 10, "offset": 4})
    assert [m["id"] for m in r.json()] == [5]


def test_item_movements_empty_for_item_without_history(client, item):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    assert r.json() == []


def test_item_movements_unknown_item_404(client):
    r = client.get("/items/999/movements")
    assert r.status_code == 404


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


# --- optional reference --------------------------------------------------------


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
    per_item = client.get(f"/items/{item['id']}/movements").json()
    assert per_item[0]["reference"] == "PO-12345"


def test_movement_reference_defaults_to_null(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert r.json()["reference"] is None
    assert client.get("/movements").json()[0]["reference"] is None


def test_movement_reference_explicit_null_ok(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        reference=None,
    )
    assert r.status_code == 201
    assert r.json()["reference"] is None


def test_movement_reference_max_length_ok(client, item, loc_a):
    ref = "R" * 64
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        reference=ref,
    )
    assert r.status_code == 201
    assert r.json()["reference"] == ref


def test_movement_reference_too_long_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=1,
        to_location_id=loc_a["id"],
        reference="R" * 65,
    )
    assert r.status_code == 422
    assert client.get("/movements").json() == []


def test_movement_note_max_length_ok(client, item, loc_a):
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


# --- reverse a movement -----------------------------------------------------------


def test_reverse_receive_creates_ship(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"]
    ).json()
    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != original["id"]
    assert body["kind"] == "ship"
    assert body["item_id"] == item["id"]
    assert body["qty"] == 10
    assert body["from_location_id"] == loc_a["id"]
    assert body["to_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"
    # stock returns to zero
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
    # stock back to pre-ship level
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


def test_reverse_is_persisted_as_new_movement(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"]
    ).json()
    created = client.post(f"/movements/{original['id']}/reverse").json()
    fetched = client.get(f"/movements/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created
    movements = client.get("/movements").json()
    assert [m["id"] for m in movements] == [original["id"], created["id"]]


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404
    assert r.json()["detail"] == "movement 999 not found"


def test_reverse_movement_service_function(client, item, loc_a):
    """reverse_movement is exposed on the shared stock service."""
    from inventory.services import stock

    assert callable(stock.reverse_movement)


def test_reverse_movement_of_inactive_item_409(client, item, loc_a):
    """A reversal is a new movement, so it must also refuse inactive items."""
    original = _move(
        client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"]
    ).json()
    r = client.put(f"/items/{item['id']}", json={"active": False})
    assert r.status_code == 200
    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 409
    assert "inactive" in r.json()["detail"]
    # No reversal row was written; stock is unchanged.
    assert [m["id"] for m in client.get("/movements").json()] == [original["id"]]
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


# --- inactive items (T041) -----------------------------------------------------


def _deactivate(client, item_id):
    r = client.put(f"/items/{item_id}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
        ("adjust", {"to_location_id": 1}),
    ],
)
def test_movement_for_inactive_item_409(client, item, loc_a, loc_b, kind, payload):
    _deactivate(client, item["id"])
    r = _move(client, item_id=item["id"], kind=kind, qty=1, **payload)
    assert r.status_code == 409
    assert "inactive" in r.json()["detail"]
    # No movement row must be written.
    assert client.get("/movements").json() == []


def test_inactive_item_movement_does_not_change_stock(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _deactivate(client, item["id"])

    for kind, payload in [
        ("receive", {"to_location_id": loc_a["id"]}),
        ("ship", {"from_location_id": loc_a["id"]}),
        ("transfer", {"from_location_id": loc_a["id"], "to_location_id": loc_b["id"]}),
        ("adjust", {"to_location_id": loc_a["id"]}),
    ]:
        r = _move(client, item_id=item["id"], kind=kind, qty=3, **payload)
        assert r.status_code == 409
        assert "inactive" in r.json()["detail"]

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 5}]
    assert len(client.get("/movements").json()) == 1


def test_reactivated_item_accepts_movements_again(client, item, loc_a):
    _deactivate(client, item["id"])
    assert (
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"]).status_code
        == 409
    )
    r = client.put(f"/items/{item['id']}", json={"active": True})
    assert r.status_code == 200
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 1
