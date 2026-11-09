"""Regression tests for T003: transfer must credit the destination, not the source.

The buggy behaviour was: after POST /movements {kind: transfer, qty: N, from: A, to: B}
location A was unchanged (debited then re-credited) and B received nothing.
"""

import pytest

from inventory.db import connect, init_db
from inventory.models import MovementCreate
from inventory.models import ItemCreate
from inventory.services.items import create_item
from inventory.services.stock import apply_movement, get_stock_level, total_stock


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _level(stock_body, location_id):
    for lvl in stock_body["levels"]:
        if lvl["location_id"] == location_id:
            return lvl["quantity"]
    return 0


def test_transfer_debits_source_and_credits_destination(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])

    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201, r.text

    s = client.get(f"/items/{item['id']}/stock").json()
    # source decreased by N (the buggy version left it unchanged at 5)
    assert _level(s, loc_a["id"]) == 3
    # destination increased by N (the buggy version left it at 0)
    assert _level(s, loc_b["id"]) == 2


def test_transfer_credits_destination_with_preexisting_stock(client, item, loc_a, loc_b):
    """With stock already at both ends, a source-crediting bug is unambiguous."""
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_b["id"])

    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201, r.text

    s = client.get(f"/items/{item['id']}/stock").json()
    assert _level(s, loc_a["id"]) == 7  # 10 - 3
    assert _level(s, loc_b["id"]) == 7  # 4 + 3


def test_transfer_total_stock_unchanged(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=8, to_location_id=loc_a["id"])
    before = client.get(f"/items/{item['id']}/stock").json()["total"]

    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=5,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )

    after = client.get(f"/items/{item['id']}/stock").json()
    assert after["total"] == before == 8


def test_item_stock_endpoint_reflects_both_locations_after_transfer(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )

    r = client.get(f"/items/{item['id']}/stock")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 3},
        {"item_id": item["id"], "location_id": loc_b["id"], "quantity": 2},
    ]


def test_repeated_transfers_accumulate_at_destination(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=6, to_location_id=loc_a["id"])

    for _ in range(3):
        r = _move(
            client,
            item_id=item["id"],
            kind="transfer",
            quantity=2,
            from_location_id=loc_a["id"],
            to_location_id=loc_b["id"],
        )
        assert r.status_code == 201, r.text

    s = client.get(f"/items/{item['id']}/stock").json()
    assert _level(s, loc_a["id"]) == 0
    assert _level(s, loc_b["id"]) == 6
    assert s["total"] == 6


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    c = connect(path)
    try:
        yield c
    finally:
        c.close()


def test_apply_movement_transfer_service_level(conn):
    """Exercise the service function directly: the transfer must debit the
    source row and credit the destination row in stock_levels."""
    item = create_item(conn, ItemCreate(sku="SKU-T003", name="Widget"))
    cur = conn.execute("INSERT INTO locations (code, name) VALUES ('A', 'A')")
    loc_a = cur.lastrowid
    cur = conn.execute("INSERT INTO locations (code, name) VALUES ('B', 'B')")
    loc_b = cur.lastrowid

    apply_movement(
        conn,
        MovementCreate(item_id=item.id, kind="receive", quantity=5, to_location_id=loc_a),
    )
    apply_movement(
        conn,
        MovementCreate(
            item_id=item.id,
            kind="transfer",
            quantity=2,
            from_location_id=loc_a,
            to_location_id=loc_b,
        ),
    )

    assert get_stock_level(conn, item.id, loc_a) == 3
    assert get_stock_level(conn, item.id, loc_b) == 2
    assert total_stock(conn, item.id) == 5
