"""Tests for POST /movements/{id}/reverse (T045)."""


def _stock(client, item_id):
    r = client.get(f"/items/{item_id}/stock")
    assert r.status_code == 200, r.text
    return r.json()


def _receive(client, item, loc, quantity=10):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": quantity, "to_location_id": loc["id"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_reverse_receive_creates_ship(client, item, loc_a):
    original = _receive(client, item, loc_a, quantity=10)

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201, r.text
    reversal = r.json()
    assert reversal["id"] != original["id"]
    assert reversal["kind"] == "ship"
    assert reversal["quantity"] == 10
    assert reversal["from_location_id"] == loc_a["id"]
    assert reversal["to_location_id"] is None
    assert reversal["note"] == f"reversal of {original['id']}"
    assert reversal["item_id"] == item["id"]

    # stock is back to zero
    assert _stock(client, item["id"])["total"] == 0


def test_reverse_ship_creates_receive(client, item, loc_a):
    _receive(client, item, loc_a, quantity=10)
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 4, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    original = r.json()

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201, r.text
    reversal = r.json()
    assert reversal["kind"] == "receive"
    assert reversal["quantity"] == 4
    assert reversal["to_location_id"] == loc_a["id"]
    assert reversal["from_location_id"] is None
    assert reversal["note"] == f"reversal of {original['id']}"

    assert _stock(client, item["id"])["total"] == 10


def test_reverse_transfer_swaps_locations(client, item, loc_a, loc_b):
    _receive(client, item, loc_a, quantity=10)
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "quantity": 6,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
        },
    )
    assert r.status_code == 201, r.text
    original = r.json()

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201, r.text
    reversal = r.json()
    assert reversal["kind"] == "transfer"
    assert reversal["quantity"] == 6
    assert reversal["from_location_id"] == loc_b["id"]
    assert reversal["to_location_id"] == loc_a["id"]
    assert reversal["note"] == f"reversal of {original['id']}"

    levels = {lvl["location_id"]: lvl["quantity"] for lvl in _stock(client, item["id"])["levels"]}
    assert levels.get(loc_a["id"], 0) == 10
    assert levels.get(loc_b["id"], 0) == 0


def test_reversal_is_persisted_and_retrievable(client, item, loc_a):
    original = _receive(client, item, loc_a, quantity=3)
    reversal = client.post(f"/movements/{original['id']}/reverse").json()

    r = client.get(f"/movements/{reversal['id']}")
    assert r.status_code == 200, r.text
    assert r.json() == reversal


def test_reverse_unknown_movement_returns_404(client):
    r = client.post("/movements/9999/reverse")
    assert r.status_code == 404
