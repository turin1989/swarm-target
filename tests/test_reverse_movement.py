"""Reversing a movement (T045): POST /movements/{id}/reverse."""


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

    # the stock effect of the original movement is undone
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_reverse_ship_creates_receive(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    original = _move(
        client, item_id=item["id"], kind="ship", quantity=3, from_location_id=loc_a["id"]
    ).json()
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 7

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "receive"
    assert body["quantity"] == 3
    assert body["from_location_id"] is None
    assert body["to_location_id"] == loc_a["id"]
    assert body["note"] == f"reversal of {original['id']}"

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

    # stock is back where it started
    s = client.get(f"/items/{item['id']}/stock").json()
    levels = {lvl["location_id"]: lvl["quantity"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 5
    assert levels.get(loc_b["id"], 0) == 0


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_reversal_is_persisted_as_a_new_movement(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_a["id"]
    ).json()
    reversal = client.post(f"/movements/{original['id']}/reverse").json()

    movements = client.get("/movements").json()
    assert [m["id"] for m in movements] == [original["id"], reversal["id"]]
    fetched = movements[1]
    assert fetched["kind"] == "ship"
    assert fetched["note"] == f"reversal of {original['id']}"


def test_service_reverse_movement_directly():
    """stock.reverse_movement(conn, movement_id) works at the service layer."""
    import pytest

    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.errors import NotFoundError
    from inventory.services.stock import apply_movement, reverse_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO items (sku, name) VALUES ('S-1', 'Thing')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-B', 'Warehouse B')")

    m = apply_movement(
        conn,
        MovementCreate(
            item_id=1, kind="transfer", quantity=2, from_location_id=1, to_location_id=2,
        ),
    )
    rev = reverse_movement(conn, m.id)
    assert rev.kind == "transfer"
    assert rev.from_location_id == 2
    assert rev.to_location_id == 1
    assert rev.quantity == 2
    assert rev.note == f"reversal of {m.id}"

    with pytest.raises(NotFoundError):
        reverse_movement(conn, 999)
