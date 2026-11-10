"""Tests for PUT /locations/{id} (rename a location)."""

import sqlite3

from inventory.db import init_db

# --- POST /locations duplicate codes (T007) ------------------------------------


def test_create_location_duplicate_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": loc_a["code"], "name": "Another"})
    assert r.status_code == 409, r.text
    # uniform error shape: {"error": {"code": ..., "message": ...}}
    err = r.json()["error"]
    assert err["code"] == "conflict"
    # the error message mentions the duplicate code
    assert loc_a["code"] in err["message"]


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
        json={"item_id": item["id"], "kind": "receive", "quantity": 5, "to_location_id": loc_a["id"]},
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
        json={"item_id": item["id"], "kind": "receive", "quantity": 5, "to_location_id": loc_a["id"]},
    )
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 5, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text

    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


def test_delete_location_unknown_id_returns_404(client):
    r = client.delete("/locations/9999")
    assert r.status_code == 404


# --- active flag (deactivation) ------------------------------------------------


def test_new_location_is_active_by_default(client, loc_a):
    assert loc_a["active"] is True

    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_put_can_deactivate_location(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["code"] == loc_a["code"]  # unchanged
    assert body["name"] == loc_a["name"]  # unchanged

    # change is persisted
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_put_can_reactivate_location(client, loc_a):
    assert client.put(f"/locations/{loc_a['id']}", json={"active": False}).status_code == 200

    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True

    r = client.get(f"/locations/{loc_a['id']}")
    assert r.json()["active"] is True


def test_put_active_alongside_other_fields(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "Mothballed", "active": False}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Mothballed"
    assert body["active"] is False


def test_put_without_active_leaves_flag_unchanged(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False


def test_get_locations_filters_by_active(client, loc_a, loc_b):
    assert client.put(f"/locations/{loc_b['id']}", json={"active": False}).status_code == 200

    r = client.get("/locations", params={"active": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [loc["id"] for loc in body] == [loc_a["id"]]
    assert all(loc["active"] is True for loc in body)

    r = client.get("/locations", params={"active": "false"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [loc["id"] for loc in body] == [loc_b["id"]]
    assert all(loc["active"] is False for loc in body)


def test_get_locations_without_filter_returns_all(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})

    r = client.get("/locations")
    assert r.status_code == 200
    ids = [loc["id"] for loc in r.json()]
    assert ids == [loc_a["id"], loc_b["id"]]
