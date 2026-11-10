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
    """Transfer of N decreases `from` by N and increases `to` by N (T003)."""
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
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 3
    assert levels[loc_b["id"]] == 2


def test_transfer_preserves_total_stock(client, item, loc_a, loc_b):
    """The item's total stock is unchanged by a transfer (T003)."""
    _move(client, item_id=item["id"], kind="receive", qty=9, to_location_id=loc_a["id"])
    before = client.get(f"/items/{item['id']}/stock").json()["total"]
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    after = client.get(f"/items/{item['id']}/stock").json()["total"]
    assert before == after == 9


def test_transfer_reflected_in_stock_endpoint_for_both_locations(client, item, loc_a, loc_b):
    """GET /items/{id}/stock shows a level row for both locations after a transfer (T003)."""
    _move(client, item_id=item["id"], kind="receive", qty=6, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=6,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 6
    assert s["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "qty": 0},
        {"item_id": item["id"], "location_id": loc_b["id"], "qty": 6},
    ]


def test_transfer_to_same_location_rejected(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    before = client.get(f"/items/{item['id']}/stock").json()

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

    # No movement row was written and stock is unchanged.
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert client.get(f"/items/{item['id']}/stock").json() == before


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


# --- non-positive quantities (T040) --------------------------------------------


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
    # Seed some stock so the rejection isn't caused by anything else.
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    before = client.get(f"/items/{item['id']}/stock").json()

    r = _move(client, item_id=item["id"], kind=kind, qty=qty, **payload)
    assert r.status_code == 422

    # No movement row was written and stock is unchanged.
    assert len(client.get("/movements").json()) == 1
    assert client.get(f"/items/{item['id']}/stock").json() == before


def test_apply_movement_rejects_non_positive_qty_directly():
    """The service layer guards against qty <= 0 even if validation is bypassed."""
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.stock import StockError, apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")

    m = MovementCreate.model_construct(
        item_id=1, kind="receive", qty=0, from_location_id=None, to_location_id=1, note=""
    )
    with pytest.raises(StockError) as exc:
        apply_movement(conn, m)
    assert exc.value.status_code == 422
    assert conn.execute("SELECT COUNT(*) AS n FROM movements").fetchone()["n"] == 0


# --- insufficient stock rejected with 409 (T005) --------------------------------


def test_ship_more_than_on_hand_409(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    before = client.get(f"/items/{item['id']}/stock").json()

    r = _move(client, item_id=item["id"], kind="ship", qty=6, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]

    # No movement row was written and stock levels are unchanged.
    assert len(client.get("/movements").json()) == 1
    assert client.get(f"/items/{item['id']}/stock").json() == before


def test_ship_with_no_stock_at_all_409(client, item, loc_a):
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


def test_transfer_more_than_source_stock_409(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    before = client.get(f"/items/{item['id']}/stock").json()

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

    # No movement row was written and stock levels are unchanged.
    assert len(client.get("/movements").json()) == 1
    assert client.get(f"/items/{item['id']}/stock").json() == before


def test_transfer_checks_source_not_destination(client, item, loc_a, loc_b):
    # Plenty of stock at B, none at A; transferring from A must still fail.
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_b["id"])

    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=1,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]


def test_transfer_exactly_source_stock_succeeds(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 0
    assert levels[loc_b["id"]] == 3


def test_apply_movement_rejects_insufficient_stock_directly():
    """The service layer raises StockError(409) and writes nothing."""
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.stock import StockError, apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    conn.execute("INSERT INTO stock_levels (item_id, location_id, qty) VALUES (1, 1, 2)")

    m = MovementCreate(item_id=1, kind="ship", qty=3, from_location_id=1)
    with pytest.raises(StockError) as exc:
        apply_movement(conn, m)
    assert exc.value.status_code == 409
    assert "insufficient" in str(exc.value)
    assert conn.execute("SELECT COUNT(*) AS n FROM movements").fetchone()["n"] == 0
    row = conn.execute(
        "SELECT qty FROM stock_levels WHERE item_id = 1 AND location_id = 1"
    ).fetchone()
    assert row["qty"] == 2


def test_movement_invalid_kind_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="explode", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 422


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
    ],
)
def test_movement_for_inactive_item_409(client, item, loc_a, loc_b, kind, payload):
    # Seed some stock while the item is still active, then deactivate it.
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = client.put(f"/items/{item['id']}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False

    before = client.get(f"/items/{item['id']}/stock").json()

    r = _move(client, item_id=item["id"], kind=kind, qty=3, **payload)
    assert r.status_code == 409
    assert "inactive" in r.json()["detail"]

    # Stock levels are unchanged and no movement was recorded.
    after = client.get(f"/items/{item['id']}/stock").json()
    assert after == before
    assert len(client.get("/movements").json()) == 1


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
    # No movement was recorded.
    assert client.get("/movements").json() == []


def test_movement_note_at_limit_accepted(client, item, loc_a):
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


# --- 'adjust' movement kind (T039) ---------------------------------------------


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


def test_adjust_creates_stock_row_when_none_exists(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=7, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 7
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 7}]


def test_adjust_is_absolute_not_delta(client, item, loc_a):
    _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=loc_a["id"])
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


def test_adjust_only_affects_target_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=4, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=9, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 13
    assert [lvl["qty"] for lvl in s["levels"]] == [4, 9]


def test_adjust_requires_to_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=5)
    assert r.status_code == 400
    assert "required" in r.json()["detail"]
    assert client.get("/movements").json() == []


def test_adjust_rejects_from_location(client, item, loc_a, loc_b):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=5,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 400
    assert "from_location_id" in r.json()["detail"]
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_adjust_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=123)
    assert r.status_code == 404


def test_adjust_recorded_in_movements_list(client, item, loc_a):
    _move(client, item_id=item["id"], kind="adjust", qty=2, to_location_id=loc_a["id"], note="count")
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "adjust"
    assert movements[0]["qty"] == 2
    assert movements[0]["note"] == "count"


# --- GET /items/{id}/movements (T032) -------------------------------------------


def test_item_movements_empty(client, item):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    assert r.json() == []


def test_item_movements_ordered_by_id(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_b["id"])

    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [1, 2, 3]
    assert [m["kind"] for m in movements] == ["receive", "transfer", "ship"]
    assert all(m["item_id"] == item["id"] for m in movements)


def test_item_movements_only_includes_that_item(client, item, loc_a):
    other = client.post(
        "/items",
        json={"sku": "OTHER-1", "name": "Other", "unit_price": 1.0, "reorder_point": 0},
    ).json()
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=other["id"], kind="receive", qty=9, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])

    movements = client.get(f"/items/{item['id']}/movements").json()
    assert [m["id"] for m in movements] == [1, 3]
    assert all(m["item_id"] == item["id"] for m in movements)

    other_movements = client.get(f"/items/{other['id']}/movements").json()
    assert [m["id"] for m in other_movements] == [2]


def test_item_movements_pagination(client, item, loc_a):
    for _ in range(5):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 2})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [3, 4]

    r = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 4})
    assert [m["id"] for m in r.json()] == [5]


def test_item_movements_unknown_item_404(client):
    r = client.get("/items/999/movements")
    assert r.status_code == 404


def test_item_movements_invalid_pagination_422(client, item):
    assert client.get(f"/items/{item['id']}/movements", params={"limit": 0}).status_code == 422
    assert client.get(f"/items/{item['id']}/movements", params={"offset": -1}).status_code == 422


def test_list_movements_service_filters_by_item():
    """stock.list_movements supports an item_id filter at the service layer."""
    from inventory.db import SCHEMA, connect
    from inventory.services.stock import list_movements

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S2', 'Gadget', '', 1.0, 0, 1)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    for item_id in (1, 2, 1):
        conn.execute(
            "INSERT INTO movements (item_id, kind, qty, to_location_id) "
            "VALUES (?, 'receive', 1, 1)",
            (item_id,),
        )

    assert [m.id for m in list_movements(conn, item_id=1)] == [1, 3]
    assert [m.id for m in list_movements(conn, item_id=2)] == [2]
    assert [m.id for m in list_movements(conn)] == [1, 2, 3]
    assert [m.id for m in list_movements(conn, item_id=1, limit=1, offset=1)] == [3]


# --- DELETE /locations/{id} (T013) --------------------------------------------


def test_delete_location_empty(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404
    assert loc_a["id"] not in [loc["id"] for loc in client.get("/locations").json()]


def test_delete_location_unknown_id(client):
    assert client.delete("/locations/999").status_code == 404


def test_delete_location_with_stock_conflict(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409
    # location must remain
    assert client.get(f"/locations/{loc_a['id']}").status_code == 200


def test_delete_location_with_zero_qty_stock_row(client, item, loc_a):
    # Receive then ship everything out: stock_levels row exists with qty == 0.
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=5, from_location_id=loc_a["id"])
    levels = client.get(f"/items/{item['id']}/stock").json()["levels"]
    assert all(lvl["qty"] == 0 for lvl in levels if lvl["location_id"] == loc_a["id"])
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


# --- optional reference (T043) ------------------------------------------------


def test_movement_with_reference_returned_on_post(client, item, loc_a):
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


def test_movement_reference_defaults_to_none(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert r.json()["reference"] is None


def test_movement_reference_returned_on_get(client, item, loc_a):
    _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=5,
        to_location_id=loc_a["id"],
        reference="PO-777",
    )
    _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])

    listed = client.get("/movements").json()
    assert [m["reference"] for m in listed] == ["PO-777", None]

    by_item = client.get(f"/items/{item['id']}/movements").json()
    assert [m["reference"] for m in by_item] == ["PO-777", None]


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


def test_movement_reference_persisted_in_db_column(client, item, loc_a, tmp_path):
    _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=2,
        to_location_id=loc_a["id"],
        reference="PO-DB",
    )
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        (ref,) = conn.execute("SELECT reference FROM movements WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert ref == "PO-DB"


def test_init_db_adds_reference_column_to_existing_db(tmp_path):
    import sqlite3

    from inventory import db

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                qty INTEGER NOT NULL,
                from_location_id INTEGER,
                to_location_id INTEGER,
                note TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(path)
    db.init_db(path)  # idempotent

    conn = sqlite3.connect(path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(movements)").fetchall()}
    finally:
        conn.close()
    assert "reference" in cols


# --- POST /movements/{id}/reverse (T045) -----------------------------------------


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

    # Stock is back to zero.
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

    # Stock is restored to the pre-ship level.
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_reverse_transfer_swaps_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=8, to_location_id=loc_a["id"])
    original = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    ).json()

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "transfer"
    assert body["qty"] == 3
    assert body["from_location_id"] == loc_b["id"]
    assert body["to_location_id"] == loc_a["id"]
    assert body["note"] == f"reversal of {original['id']}"

    # Stock is back at the original location.
    s = client.get(f"/items/{item['id']}/stock").json()
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 8
    assert levels[loc_b["id"]] == 0


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404
    assert client.get("/movements").json() == []


def test_reverse_is_persisted_in_movement_list(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", qty=2, to_location_id=loc_a["id"]
    ).json()
    reversal = client.post(f"/movements/{original['id']}/reverse").json()

    movements = client.get("/movements").json()
    assert [m["id"] for m in movements] == [original["id"], reversal["id"]]
    assert movements[1]["note"] == f"reversal of {original['id']}"


def test_reverse_receive_with_insufficient_stock_409(client, item, loc_a):
    # Receive 5, then ship 3; reversing the receive would ship 5 > 2 on hand.
    original = _move(
        client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"]
    ).json()
    _move(client, item_id=item["id"], kind="ship", qty=3, from_location_id=loc_a["id"])

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]
    # Nothing was written.
    assert len(client.get("/movements").json()) == 2


def test_reverse_adjust_rejected(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="adjust", qty=5, to_location_id=loc_a["id"]
    ).json()
    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 400
    assert len(client.get("/movements").json()) == 1


def test_reverse_movement_service_directly():
    """stock.reverse_movement works at the service layer."""
    import pytest as _pytest

    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.stock import StockError, apply_movement, reverse_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-B', 'Warehouse B')")

    original = apply_movement(
        conn, MovementCreate(item_id=1, kind="receive", qty=6, to_location_id=1)
    )
    reversal = reverse_movement(conn, original.id)
    assert reversal.kind == "ship"
    assert reversal.qty == 6
    assert reversal.from_location_id == 1
    assert reversal.to_location_id is None
    assert reversal.note == f"reversal of {original.id}"

    with _pytest.raises(StockError) as exc:
        reverse_movement(conn, 999)
    assert exc.value.status_code == 404
