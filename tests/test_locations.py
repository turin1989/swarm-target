"""Tests for location endpoints (T007: duplicate location codes)."""

import sqlite3

from inventory.db import SCHEMA


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text


def test_duplicate_location_code_detail_mentions_code(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    assert "WH-A" in r.json()["error"]["message"]


def test_duplicate_location_does_not_create_second_row(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409
    rows = client.get("/locations").json()
    assert [loc["code"] for loc in rows] == ["WH-A"]


def test_distinct_location_codes_still_accepted(client, loc_a, loc_b):
    assert loc_a["code"] == "WH-A"
    assert loc_b["code"] == "WH-B"


def test_locations_code_column_is_unique_in_schema():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        import pytest

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
    finally:
        conn.close()


# --- T013: DELETE /locations/{id} ---------------------------------------------


def test_delete_empty_location_returns_204_and_removes_it(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404
    assert loc_a["id"] not in [loc["id"] for loc in client.get("/locations").json()]


def test_delete_unknown_location_returns_404(client):
    r = client.delete("/locations/9999")
    assert r.status_code == 404, r.text


def test_delete_location_holding_stock_returns_409(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 7, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409, r.text
    # location must still exist
    assert client.get(f"/locations/{loc_a['id']}").status_code == 200


def test_delete_location_with_zero_qty_stock_row_succeeds(client, item, loc_a):
    # receive then ship everything out: stock_levels row exists with qty == 0
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 4, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 4, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


def test_delete_location_does_not_touch_other_locations_stock(client, item, loc_a, loc_b):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_b["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    levels = client.get(f"/locations/{loc_b['id']}/stock").json()["levels"]
    assert levels == [{"item_id": item["id"], "location_id": loc_b["id"], "qty": 3}]
