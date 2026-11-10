"""Tests for PUT /locations/{id} (rename a location)."""

import sqlite3

from inventory.db import init_db


# --- POST /locations duplicate codes (T007) ------------------------------------


def test_create_location_duplicate_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": loc_a["code"], "name": "Another"})
    assert r.status_code == 409, r.text
    # the error detail mentions the duplicate code
    assert loc_a["code"] in r.json()["detail"]


def test_create_location_duplicate_code_does_not_create_row(client, loc_a):
    client.post("/locations", json={"code": loc_a["code"], "name": "Another"})
    codes = [loc["code"] for loc in client.get("/locations").json()]
    assert codes.count(loc_a["code"]) == 1


def test_create_location_distinct_codes_still_allowed(client, loc_a):
    r = client.post("/locations", json={"code": "WH-Z", "name": "Warehouse Z"})
    assert r.status_code == 201, r.text


def test_locations_code_column_is_unique_in_schema(tmp_path):
    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        # a unique index on locations(code) must exist
        indexes = conn.execute("PRAGMA index_list('locations')").fetchall()
        unique_columns = set()
        for _, index_name, is_unique, *_ in indexes:
            if is_unique:
                cols = [
                    row[2]
                    for row in conn.execute(f"PRAGMA index_info('{index_name}')")
                ]
                if len(cols) == 1:
                    unique_columns.add(cols[0])
        assert "code" in unique_columns

        # and the constraint is enforced at the database level
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate location code was accepted by the schema")
    finally:
        conn.close()


def test_update_location_name_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Main Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Main Warehouse"
    assert body["code"] == loc_a["code"]  # unchanged


def test_update_location_code_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-MAIN"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-MAIN"
    assert body["name"] == loc_a["name"]  # unchanged


def test_update_location_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "Depot", "code": "DEP-1"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Depot"
    assert body["code"] == "DEP-1"

    # change is persisted
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json() == body


def test_update_location_empty_payload_returns_unchanged(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_location_unknown_id_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Ghost"})
    assert r.status_code == 404


# --- DELETE /locations/{id} ---------------------------------------------------


def test_delete_location_returns_204_and_location_is_gone(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert r.content == b""

    # location is gone
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404
    codes = [loc["code"] for loc in client.get("/locations").json()]
    assert loc_a["code"] not in codes


def test_delete_location_with_stock_returns_409(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text

    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409, r.text

    # location still exists
    assert client.get(f"/locations/{loc_a['id']}").status_code == 200


def test_delete_location_with_zero_qty_stock_row_succeeds(client, item, loc_a):
    # receive then ship everything: a stock_levels row remains with qty == 0
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 5, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text

    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


def test_delete_location_unknown_id_returns_404(client):
    r = client.delete("/locations/9999")
    assert r.status_code == 404
