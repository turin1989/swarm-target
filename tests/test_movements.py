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


# --- GET /movements filters (T044) ------------------------------------------------


@pytest.fixture()
def _mixed_movements(client, item, loc_a, loc_b):
    """Two items with a mix of movement kinds; returns (item, other)."""
    r = client.post("/items", json={"sku": "OTHER-1", "name": "Other"})
    assert r.status_code == 201, r.text
    other = r.json()
    # id 1: item receive, id 2: other receive, id 3: item ship,
    # id 4: other ship, id 5: item transfer
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    _move(client, item_id=other["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    _move(client, item_id=other["id"], kind="ship", qty=2, from_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    return item, other


def test_list_movements_filter_by_item_id(client, _mixed_movements):
    item, other = _mixed_movements
    r = client.get("/movements", params={"item_id": item["id"]})
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [1, 3, 5]
    assert all(m["item_id"] == item["id"] for m in movements)

    r = client.get("/movements", params={"item_id": other["id"]})
    assert [m["id"] for m in r.json()] == [2, 4]


def test_list_movements_filter_by_kind(client, _mixed_movements):
    r = client.get("/movements", params={"kind": "ship"})
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [3, 4]
    assert all(m["kind"] == "ship" for m in movements)

    r = client.get("/movements", params={"kind": "transfer"})
    assert [m["id"] for m in r.json()] == [5]

    r = client.get("/movements", params={"kind": "adjust"})
    assert r.json() == []


def test_list_movements_invalid_kind_422(client, _mixed_movements):
    assert client.get("/movements", params={"kind": "bogus"}).status_code == 422


def test_list_movements_filters_combine(client, _mixed_movements):
    item, other = _mixed_movements
    r = client.get("/movements", params={"item_id": item["id"], "kind": "ship"})
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [3]
    assert movements[0]["item_id"] == item["id"]
    assert movements[0]["kind"] == "ship"

    r = client.get("/movements", params={"item_id": other["id"], "kind": "transfer"})
    assert r.json() == []


def test_list_movements_filters_with_pagination(client, item, loc_a):
    for i in range(4):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
        _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_a["id"])
    # ship movements have even ids 2, 4, 6, 8
    r = client.get(
        "/movements",
        params={"item_id": item["id"], "kind": "ship", "limit": 2, "offset": 1},
    )
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [4, 6]


def test_list_movements_no_filters_returns_all(client, _mixed_movements):
    r = client.get("/movements")
    assert [m["id"] for m in r.json()] == [1, 2, 3, 4, 5]
