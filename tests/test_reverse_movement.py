"""Reversing a movement (T045)."""

import pytest


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_reverse_receive_creates_ship(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"]
    ).json()

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != original["id"]
    assert body["kind"] == "ship"
    assert body["item_id"] == item["id"]
    assert body["quantity"] == 10
    assert body["from_location_id"] == loc_a["id"]
    assert body["to_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"

    # stock is back to zero
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_reverse_ship_creates_receive(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    original = _move(
        client, item_id=item["id"], kind="ship", quantity=4, from_location_id=loc_a["id"]
    ).json()

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "receive"
    assert body["quantity"] == 4
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"

    # stock is restored
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_reverse_transfer_swaps_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    original = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    ).json()

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "transfer"
    assert body["quantity"] == 2
    assert body["from_location_id"] == loc_b["id"]
    assert body["to_location_id"] == loc_a["id"]
    assert body["note"] == f"reversal of {original['id']}"

    # all stock is back at loc_a
    s = client.get(f"/items/{item['id']}/stock").json()
    levels = {lvl["location_id"]: lvl["quantity"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 5
    assert levels.get(loc_b["id"], 0) == 0


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "movement 999 not found"


def test_reversal_is_persisted_and_retrievable(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"]
    ).json()
    created = client.post(f"/movements/{original['id']}/reverse").json()

    fetched = client.get(f"/movements/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created

    movements = client.get("/movements").json()
    assert [m["id"] for m in movements] == [original["id"], created["id"]]


def test_reverse_route_delegates_to_service(client):
    """The route delegates to stock.reverse_movement."""
    import inspect

    from inventory import api

    source = inspect.getsource(api.reverse_movement)
    assert "stock.reverse_movement" in source


def test_service_reverse_movement_direct():
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.errors import NotFoundError
    from inventory.services.stock import apply_movement, reverse_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO items (sku, name) VALUES ('S-1', 'Thing')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    original = apply_movement(
        conn, MovementCreate(item_id=1, kind="receive", quantity=2, to_location_id=1)
    )

    reversed_m = reverse_movement(conn, original.id)
    assert reversed_m.kind == "ship"
    assert reversed_m.quantity == 2
    assert reversed_m.from_location_id == 1
    assert reversed_m.to_location_id is None
    assert reversed_m.note == f"reversal of {original.id}"

    with pytest.raises(NotFoundError, match="movement 42 not found"):
        reverse_movement(conn, 42)
