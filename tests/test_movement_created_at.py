"""Tests for movements.created_at (T042)."""

import re
from datetime import datetime, timezone

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _assert_valid_created_at(value):
    assert isinstance(value, str)
    assert ISO_UTC.match(value), f"not ISO-8601 UTC: {value!r}"
    datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


def _receive(client, item, loc, qty=10):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_movement_sets_created_at(client, item, loc_a):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    body = _receive(client, item, loc_a)
    after = datetime.now(timezone.utc).replace(microsecond=0)
    _assert_valid_created_at(body["created_at"])
    ts = datetime.strptime(body["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    assert before <= ts <= after


def test_get_movement_returns_created_at(client, item, loc_a):
    movement = _receive(client, item, loc_a)
    r = client.get(f"/movements/{movement['id']}")
    assert r.status_code == 200
    _assert_valid_created_at(r.json()["created_at"])
    assert r.json()["created_at"] == movement["created_at"]


def test_list_movements_returns_created_at(client, item, loc_a, loc_b):
    _receive(client, item, loc_a)
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "qty": 3,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
        },
    )
    assert r.status_code == 201, r.text
    rows = client.get("/movements").json()
    assert len(rows) >= 2
    for row in rows:
        _assert_valid_created_at(row["created_at"])


def test_reverse_movement_sets_created_at(client, item, loc_a):
    movement = _receive(client, item, loc_a)
    r = client.post(f"/movements/{movement['id']}/reverse")
    assert r.status_code == 201, r.text
    _assert_valid_created_at(r.json()["created_at"])
