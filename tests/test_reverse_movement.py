"""Reversing a movement via POST /movements/{id}/reverse (T045)."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_reverse_receive_creates_ship(client, item, loc_a):
    orig = _move(
        client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"]
    ).json()

    r = client.post(f"/movements/{orig['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["id"] != orig["id"]
    assert body["kind"] == "ship"
    assert body["quantity"] == 10
    assert body["from_location_id"] == loc_a["id"]
    assert body["to_location_id"] is None
    assert body["note"] == f"reversal of {orig['id']}"

    # stock is back to zero
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_reverse_ship_creates_receive(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    ship = _move(
        client, item_id=item["id"], kind="ship", quantity=4, from_location_id=loc_a["id"]
    ).json()

    r = client.post(f"/movements/{ship['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "receive"
    assert body["quantity"] == 4
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None
    assert body["note"] == f"reversal of {ship['id']}"

    # stock restored to pre-ship level
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_reverse_transfer_swaps_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    xfer = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    ).json()

    r = client.post(f"/movements/{xfer['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "transfer"
    assert body["quantity"] == 2
    assert body["from_location_id"] == loc_b["id"]
    assert body["to_location_id"] == loc_a["id"]
    assert body["note"] == f"reversal of {xfer['id']}"

    # all stock is back in loc_a
    s = client.get(f"/items/{item['id']}/stock").json()
    levels = {lvl["location_id"]: lvl["quantity"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 5
    assert levels.get(loc_b["id"], 0) == 0


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"


def test_reversal_is_recorded_in_movement_list(client, item, loc_a):
    orig = _move(
        client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"]
    ).json()
    client.post(f"/movements/{orig['id']}/reverse")

    movements = client.get("/movements").json()
    assert len(movements) == 2
    assert movements[1]["kind"] == "ship"
    assert movements[1]["note"] == f"reversal of {orig['id']}"


def test_reverse_movement_service_function():
    """stock.reverse_movement works directly at the service layer."""
    import pytest

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
    reversal = reverse_movement(conn, original.id)
    assert reversal.kind == "ship"
    assert reversal.quantity == 2
    assert reversal.from_location_id == 1
    assert reversal.to_location_id is None
    assert reversal.note == f"reversal of {original.id}"

    with pytest.raises(NotFoundError):
        reverse_movement(conn, 999)
