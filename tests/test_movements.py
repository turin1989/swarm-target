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


# --- optional reference on movements (T043) ------------------------------------


def test_movement_with_reference_returned_on_post_and_get(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=3,
        to_location_id=loc_a["id"],
        reference="PO-12345",
    )
    assert r.status_code == 201
    assert r.json()["reference"] == "PO-12345"

    # also returned on GET
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["reference"] == "PO-12345"


def test_movement_reference_defaults_to_none(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert r.json()["reference"] is None
    assert client.get("/movements").json()[0]["reference"] is None


def test_movement_reference_explicit_null_accepted(client, item, loc_a):
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


def test_movement_reference_at_limit_accepted(client, item, loc_a):
    ref = "P" * 64
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
        reference="P" * 65,
    )
    assert r.status_code == 422
    # No movement was recorded.
    assert client.get("/movements").json() == []


def test_movement_reference_stored_in_db_column(client, item, loc_a, tmp_path):
    """The reference is persisted in a dedicated column on the movements table."""
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.stock import apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(movements)").fetchall()]
    assert "reference" in cols

    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    m = apply_movement(
        conn,
        MovementCreate(item_id=1, kind="receive", qty=2, to_location_id=1, reference="PO-9"),
    )
    assert m.reference == "PO-9"
    row = conn.execute("SELECT reference FROM movements WHERE id = ?", (m.id,)).fetchone()
    assert row["reference"] == "PO-9"


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
