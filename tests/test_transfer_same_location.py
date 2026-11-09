"""T046: transfers where source equals destination are rejected with 400
and no movement row is written."""

import pytest

from inventory.db import connect, init_db
from inventory.models import MovementCreate
from inventory.services import stock
from inventory.services.errors import ValidationError


# --- API level ------------------------------------------------------------


def _receive(client, item_id, location_id, quantity):
    r = client.post(
        "/movements",
        json={
            "item_id": item_id,
            "kind": "receive",
            "quantity": quantity,
            "to_location_id": location_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _transfer_same(client, item_id, location_id, quantity=1):
    return client.post(
        "/movements",
        json={
            "item_id": item_id,
            "kind": "transfer",
            "quantity": quantity,
            "from_location_id": location_id,
            "to_location_id": location_id,
        },
    )


def test_same_location_transfer_returns_400_with_detail(client, item, loc_a):
    _receive(client, item["id"], loc_a["id"], 5)
    r = _transfer_same(client, item["id"], loc_a["id"], quantity=2)
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    # the error detail must mention "same location"
    assert "same location" in body["error"]["message"]


def test_same_location_transfer_writes_no_movement_row(client, item, loc_a):
    _receive(client, item["id"], loc_a["id"], 5)
    before = client.get("/movements").json()
    r = _transfer_same(client, item["id"], loc_a["id"], quantity=2)
    assert r.status_code == 400
    after = client.get("/movements").json()
    assert after == before
    assert all(m["kind"] != "transfer" for m in after)


def test_same_location_transfer_leaves_stock_untouched(client, item, loc_a):
    _receive(client, item["id"], loc_a["id"], 5)
    r = _transfer_same(client, item["id"], loc_a["id"], quantity=2)
    assert r.status_code == 400
    body = client.get(f"/items/{item['id']}/stock").json()
    assert body["total"] == 5
    assert body["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 5}
    ]


def test_same_location_check_takes_precedence_over_insufficient_stock(
    client, item, loc_a
):
    # No stock at all: the same-location error (400) must win over the
    # insufficient-stock conflict (409).
    r = _transfer_same(client, item["id"], loc_a["id"], quantity=3)
    assert r.status_code == 400
    assert "same location" in r.json()["error"]["message"]


# --- service level ----------------------------------------------------------


@pytest.fixture()
def conn(tmp_path):
    db_path = str(tmp_path / "svc.db")
    init_db(db_path)
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _seed(conn):
    conn.execute(
        "INSERT INTO items (sku, name, active) VALUES ('SVC-1', 'Svc Widget', 1)"
    )
    item_id = conn.execute("SELECT id FROM items WHERE sku = 'SVC-1'").fetchone()["id"]
    conn.execute("INSERT INTO locations (code, name) VALUES ('SVC-A', 'Svc A')")
    loc_id = conn.execute("SELECT id FROM locations WHERE code = 'SVC-A'").fetchone()[
        "id"
    ]
    return item_id, loc_id


def test_apply_movement_rejects_same_location_transfer(conn):
    item_id, loc_id = _seed(conn)
    stock.apply_movement(
        conn,
        MovementCreate(
            item_id=item_id, kind="receive", quantity=4, to_location_id=loc_id
        ),
    )
    with pytest.raises(ValidationError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(
                item_id=item_id,
                kind="transfer",
                quantity=1,
                from_location_id=loc_id,
                to_location_id=loc_id,
            ),
        )
    assert exc_info.value.status_code == 400
    assert "same location" in str(exc_info.value)
    # no movement row was written for the rejected transfer
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM movements WHERE kind = 'transfer'"
    ).fetchone()["n"]
    assert count == 0
    # stock level unchanged
    assert stock.get_stock_level(conn, item_id, loc_id) == 4
