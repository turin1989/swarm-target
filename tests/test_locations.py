import sqlite3

import pytest

from inventory.db import init_db


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text


def test_duplicate_location_code_detail_mentions_code(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    assert "WH-A" in r.json()["detail"]


def test_distinct_location_codes_are_accepted(client, loc_a, loc_b):
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-A", "WH-B"]


def test_duplicate_does_not_create_extra_location(client, loc_a):
    client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    r = client.get("/locations")
    assert len(r.json()) == 1


def _receive(client, item, loc, qty):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
    )
    assert r.status_code == 201, r.text


def _ship(client, item, loc, qty):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": qty, "from_location_id": loc["id"]},
    )
    assert r.status_code == 201, r.text


def test_delete_location_returns_204_and_location_is_gone(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 404
    r = client.get("/locations")
    assert r.json() == []


def test_delete_location_with_stock_returns_409(client, item, loc_a):
    _receive(client, item, loc_a, 3)
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409, r.text
    # location must still exist
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200


def test_delete_location_succeeds_once_stock_is_back_to_zero(client, item, loc_a):
    _receive(client, item, loc_a, 3)
    _ship(client, item, loc_a, 3)
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 404


def test_delete_location_with_negative_stock_returns_409(client, item, loc_a):
    _ship(client, item, loc_a, 2)  # drives qty negative
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409, r.text


def test_delete_unknown_location_returns_404(client):
    r = client.delete("/locations/9999")
    assert r.status_code == 404


def test_delete_location_does_not_touch_other_locations(client, item, loc_a, loc_b):
    _receive(client, item, loc_b, 5)
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    r = client.get("/locations")
    assert [loc["code"] for loc in r.json()] == ["WH-B"]
    # loc_b's stock is untouched
    r = client.get(f"/items/{item['id']}/stock")
    assert r.json()["total"] == 5


def test_locations_code_column_is_unique_in_schema(tmp_path):
    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
    finally:
        conn.close()
