"""Tests for the movements.created_at timestamp (T042)."""

import re
from datetime import datetime, timezone

import pytest

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _assert_valid_created_at(value):
    assert isinstance(value, str)
    assert ISO_Z.match(value), f"not ISO-8601 UTC with Z suffix: {value!r}"
    # must parse as a real datetime
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    # sanity: roughly "now" (within a day, to be robust against clock skew)
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 86400


@pytest.fixture()
def movement(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": 7,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_movement_sets_created_at(movement):
    _assert_valid_created_at(movement["created_at"])


def test_get_movement_returns_created_at(client, movement):
    r = client.get(f"/movements/{movement['id']}")
    assert r.status_code == 200
    body = r.json()
    _assert_valid_created_at(body["created_at"])
    assert body["created_at"] == movement["created_at"]


def test_list_movements_returns_created_at(client, movement):
    r = client.get("/movements")
    assert r.status_code == 200
    rows = r.json()
    assert rows
    for row in rows:
        _assert_valid_created_at(row["created_at"])


def test_item_movements_returns_created_at(client, item, movement):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    rows = r.json()
    assert rows
    for row in rows:
        _assert_valid_created_at(row["created_at"])


def test_reversal_gets_its_own_created_at(client, movement):
    r = client.post(f"/movements/{movement['id']}/reverse")
    assert r.status_code == 201, r.text
    _assert_valid_created_at(r.json()["created_at"])


def test_created_at_persisted_in_db(client, movement):
    # the column is stored on the row itself, not derived in the response
    import sqlite3

    db_path = client.app.state.db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT created_at FROM movements WHERE id = ?", (movement["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    _assert_valid_created_at(row["created_at"])
    assert row["created_at"] == movement["created_at"]
