"""POST /movements/{id}/reverse."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


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
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 6

    r = client.post(f"/movements/{original['id']}/reverse")
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "receive"
    assert body["qty"] == 4
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"

    # Stock is restored.
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


def test_reverse_is_persisted_in_movement_list(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"]
    ).json()
    reversal = client.post(f"/movements/{original['id']}/reverse").json()

    movements = client.get("/movements").json()
    assert [m["id"] for m in movements] == [original["id"], reversal["id"]]
    assert movements[1]["note"] == f"reversal of {original['id']}"


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404


def test_reversal_is_fetchable_via_get_movement(client, item, loc_a):
    """The reversal record works with GET /movements/{id} from the integration branch."""
    original = _move(
        client, item_id=item["id"], kind="receive", qty=7, to_location_id=loc_a["id"]
    ).json()
    reversal = client.post(f"/movements/{original['id']}/reverse").json()

    r = client.get(f"/movements/{reversal['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == reversal["id"]
    assert body["kind"] == "ship"
    assert body["qty"] == 7
    assert body["note"] == f"reversal of {original['id']}"


def test_reverse_transfer_allowed_despite_same_location_guard(client, item, loc_a, loc_b):
    """Reversing a transfer between distinct locations still works alongside the
    same-location transfer rejection added on the integration branch."""
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
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
    assert r.json()["from_location_id"] == loc_b["id"]
    assert r.json()["to_location_id"] == loc_a["id"]

    # The guard itself still rejects same-location transfers.
    bad = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=1,
        from_location_id=loc_a["id"],
        to_location_id=loc_a["id"],
    )
    assert bad.status_code == 400
