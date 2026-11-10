"""Locations, movements, stock levels."""

from datetime import datetime, timezone

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
    r = _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["kind"] == "receive"
    assert body["quantity"] == 10
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 10
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 10}]


def test_receive_accumulates(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=6, to_location_id=loc_a["id"])
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_ship_decreases_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", quantity=3, from_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 7


def test_stock_split_across_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=7, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 12
    assert [lvl["quantity"] for lvl in s["levels"]] == [5, 7]


def test_transfer_is_recorded(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
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
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201

    s = client.get(f"/items/{item['id']}/stock").json()
    # total stock is unchanged by a transfer
    assert s["total"] == 5
    # from_location decreases by N, to_location increases by N
    levels = {lvl["location_id"]: lvl["quantity"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 3
    assert levels[loc_b["id"]] == 2


def test_transfer_same_location_rejected(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "same location" in body["error"]["message"]
    # no movement row written for the rejected transfer
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"
    # stock is unchanged
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


def test_adjust_sets_stock_to_absolute_quantity(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", quantity=3, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "adjust"
    assert body["quantity"] == 3
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None

    # quantity is absolute, not a delta
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 3}]


def test_adjust_creates_stock_level_when_none_exists(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", quantity=7, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 7
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 7}]


def test_adjust_only_affects_target_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=8, to_location_id=loc_b["id"])
    r = _move(client, item_id=item["id"], kind="adjust", quantity=2, to_location_id=loc_b["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    levels = {lvl["location_id"]: lvl["quantity"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 5
    assert levels[loc_b["id"]] == 2
    assert s["total"] == 7


def test_adjust_requires_to_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", quantity=3)
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]
    assert client.get("/movements").json() == []


def test_adjust_rejects_from_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        quantity=3,
        from_location_id=loc_b["id"],
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "from_location_id must be null" in body["error"]["message"]
    # no movement row written and stock unchanged
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


def test_adjust_is_recorded_as_adjust(client, item, loc_a):
    _move(client, item_id=item["id"], kind="adjust", quantity=4, to_location_id=loc_a["id"])
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "adjust"
    assert movements[0]["quantity"] == 4
    assert movements[0]["to_location_id"] == loc_a["id"]
    assert movements[0]["from_location_id"] is None


def test_adjust_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="adjust", quantity=1, to_location_id=123)
    assert r.status_code == 404


def test_adjust_rejected_for_inactive_item(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    client.put(f"/items/{item['id']}", json={"active": False})
    r = _move(client, item_id=item["id"], kind="adjust", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 409
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


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
    r = _move(client, item_id=item["id"], kind=kind, quantity=1, **payload)
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]


def test_movement_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=123)
    assert r.status_code == 404


def test_movement_unknown_item_404(client, loc_a):
    r = _move(client, item_id=123, kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 404


def test_movement_invalid_kind_422(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="explode", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 422


def test_movement_rejected_for_inactive_item(client, item, loc_a):
    # seed some stock while the item is still active
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    client.put(f"/items/{item['id']}", json={"active": False})

    r = _move(client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"])
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    # the error detail mentions the item is inactive
    assert "inactive" in body["error"]["message"]
    assert "inactive" in r.text

    # stock levels are unchanged
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 5}]

    # no movement row was written for the rejected movement
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
    ],
)
def test_all_movement_kinds_rejected_for_inactive_item(client, item, loc_a, loc_b, kind, payload):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    client.put(f"/items/{item['id']}", json={"active": False})

    r = _move(client, item_id=item["id"], kind=kind, quantity=2, **payload)
    assert r.status_code == 409
    assert "inactive" in r.json()["error"]["message"]
    # stock is unchanged for every rejected kind
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 10


def test_movement_allowed_again_after_reactivation(client, item, loc_a):
    client.put(f"/items/{item['id']}", json={"active": False})
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 409

    client.put(f"/items/{item['id']}", json={"active": True})
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 1


def test_movement_with_old_qty_field_rejected_422(client, item, loc_a):
    """The old field name ``qty`` is no longer accepted."""
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movement_with_both_qty_and_quantity_rejected_422(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "qty": 1,
            "quantity": 1,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 422
    assert client.get("/movements").json() == []


def test_movement_and_stock_responses_use_quantity_not_qty(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_a["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["quantity"] == 4
    assert "qty" not in body

    listed = client.get("/movements").json()
    assert listed[0]["quantity"] == 4
    assert "qty" not in listed[0]

    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 4}]
    assert "qty" not in s["levels"][0]


def test_list_movements_pagination(client, item, loc_a):
    for _ in range(4):
        _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    r = client.get("/movements", params={"limit": 2, "offset": 2})
    assert [m["id"] for m in r.json()] == [3, 4]


@pytest.mark.parametrize("quantity", [0, -1, -10])
def test_movement_non_positive_quantity_rejected_422(client, item, loc_a, quantity):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=quantity,
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 422
    # no movement row is written
    assert client.get("/movements").json() == []
    # stock is unchanged
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("receive", {"to_location_id": 1}),
        ("ship", {"from_location_id": 1}),
        ("transfer", {"from_location_id": 1, "to_location_id": 2}),
    ],
)
def test_all_movement_kinds_reject_zero_quantity(client, item, loc_a, loc_b, kind, payload):
    r = _move(client, item_id=item["id"], kind=kind, quantity=0, **payload)
    assert r.status_code == 422
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_apply_movement_rejects_non_positive_quantity_in_service():
    """The service layer also guards against qty <= 0 when bypassing the model."""
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.errors import ValidationError
    from inventory.services.stock import apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    bad = MovementCreate.model_construct(
        item_id=1, kind="receive", quantity=0, from_location_id=None, to_location_id=1, note=""
    )
    with pytest.raises(ValidationError):
        apply_movement(conn, bad)
    assert conn.execute("SELECT COUNT(*) AS c FROM movements").fetchone()["c"] == 0


def test_movement_note_longer_than_500_chars_rejected_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        note="x" * 501,
    )
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movement_response_includes_created_at(client, item, loc_a):
    before = datetime.now(timezone.utc)
    r = _move(client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"])
    after = datetime.now(timezone.utc)
    assert r.status_code == 201
    body = r.json()
    assert "created_at" in body
    # created_at parses as an ISO-8601 timestamp in UTC
    created = datetime.fromisoformat(body["created_at"])
    assert created.tzinfo is not None
    assert created.utcoffset().total_seconds() == 0
    # set at the time the movement was applied
    assert before.replace(microsecond=0) <= created <= after


def test_listed_movements_include_created_at(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=2, to_location_id=loc_a["id"])
    movements = client.get("/movements").json()
    assert len(movements) == 2
    for m in movements:
        created = datetime.fromisoformat(m["created_at"])
        assert created.tzinfo is not None
        assert created.utcoffset().total_seconds() == 0


def test_movements_created_at_column_persisted(client, item, loc_a):
    """The created_at value is stored in the movements table itself."""
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.stock import apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(movements)").fetchall()]
    assert "created_at" in columns

    conn.execute("INSERT INTO items (sku, name) VALUES ('S-1', 'Thing')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    m = apply_movement(
        conn, MovementCreate(item_id=1, kind="receive", quantity=2, to_location_id=1)
    )
    row = conn.execute("SELECT created_at FROM movements WHERE id = ?", (m.id,)).fetchone()
    assert row["created_at"] == m.created_at
    created = datetime.fromisoformat(row["created_at"])
    assert created.utcoffset().total_seconds() == 0


def test_movement_reference_round_trips_on_post_and_get(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=2,
        to_location_id=loc_a["id"],
        reference="PO-12345",
    )
    assert r.status_code == 201
    body = r.json()
    assert body["reference"] == "PO-12345"

    listed = client.get("/movements").json()
    assert len(listed) == 1
    assert listed[0]["reference"] == "PO-12345"


def test_movement_reference_defaults_to_null(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert "reference" in r.json()
    assert r.json()["reference"] is None
    assert client.get("/movements").json()[0]["reference"] is None


def test_movement_reference_explicit_null_accepted(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        reference=None,
    )
    assert r.status_code == 201
    assert r.json()["reference"] is None


def test_movement_reference_exactly_64_chars_accepted(client, item, loc_a):
    ref = "R" * 64
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        reference=ref,
    )
    assert r.status_code == 201
    assert r.json()["reference"] == ref


def test_movement_reference_longer_than_64_chars_rejected_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        reference="R" * 65,
    )
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movements_reference_column_persisted():
    """The reference value is stored in a movements table column."""
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.stock import apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(movements)").fetchall()]
    assert "reference" in columns

    conn.execute("INSERT INTO items (sku, name) VALUES ('S-1', 'Thing')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    m = apply_movement(
        conn,
        MovementCreate(
            item_id=1, kind="receive", quantity=2, to_location_id=1, reference="PO-999"
        ),
    )
    assert m.reference == "PO-999"
    row = conn.execute("SELECT reference FROM movements WHERE id = ?", (m.id,)).fetchone()
    assert row["reference"] == "PO-999"


def test_init_db_adds_reference_column_to_old_database(tmp_path):
    """init_db migrates pre-existing databases that lack movements.reference."""
    import sqlite3

    from inventory import db

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            qty INTEGER NOT NULL,
            from_location_id INTEGER,
            to_location_id INTEGER,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(movements)").fetchall()]
    finally:
        conn.close()
    assert "reference" in columns


def test_movement_note_exactly_500_chars_accepted(client, item, loc_a):
    note = "x" * 500
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        note=note,
    )
    assert r.status_code == 201
    assert r.json()["note"] == note
