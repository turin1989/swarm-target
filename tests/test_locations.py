"""Tests for location endpoints (T007: duplicate location codes)."""

import sqlite3


def test_create_location(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "WH-A"
    assert body["name"] == "Warehouse A"


def test_duplicate_location_code_returns_409(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text

    dup = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert dup.status_code == 409, dup.text


def test_duplicate_location_code_detail_mentions_code(client):
    r = client.post("/locations", json={"code": "WH-X", "name": "Warehouse X"})
    assert r.status_code == 201, r.text

    dup = client.post("/locations", json={"code": "WH-X", "name": "Duplicate"})
    assert dup.status_code == 409, dup.text
    body = dup.json()
    assert body["error"]["code"] == "conflict"
    assert "WH-X" in body["error"]["message"]


def test_duplicate_does_not_create_extra_location(client):
    client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    client.post("/locations", json={"code": "WH-A", "name": "Duplicate"})

    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_locations_code_column_is_unique_in_schema(tmp_path):
    from inventory.db import init_db

    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        # The UNIQUE constraint on locations.code must exist at the schema level.
        indexes = conn.execute("PRAGMA index_list('locations')").fetchall()
        unique_cols = set()
        for idx in indexes:
            # idx: (seq, name, unique, origin, partial)
            if idx[2]:  # unique
                for col in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall():
                    unique_cols.add(col[2])
        assert "code" in unique_cols

        conn.execute("INSERT INTO locations (code, name) VALUES ('DUP', 'first')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('DUP', 'second')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected IntegrityError for duplicate location code")
    finally:
        conn.close()


# --- T034: location code format validation ------------------------------------


def test_valid_codes_accepted(client):
    for code in ["WH-A", "A", "0", "WH-1-SHELF-2", "X" * 32, "9-ZONE"]:
        r = client.post("/locations", json={"code": code, "name": f"Loc {code}"})
        assert r.status_code == 201, f"{code!r}: {r.text}"
        assert r.json()["code"] == code


def test_lowercase_code_rejected_422(client):
    r = client.post("/locations", json={"code": "wh-a", "name": "Lowercase"})
    assert r.status_code == 422, r.text


def test_code_starting_with_hyphen_rejected_422(client):
    r = client.post("/locations", json={"code": "-WH", "name": "Leading hyphen"})
    assert r.status_code == 422, r.text


def test_code_with_invalid_characters_rejected_422(client):
    for code in ["WH_A", "WH A", "WH.A", "WH/A", "WHÄ"]:
        r = client.post("/locations", json={"code": code, "name": "Bad chars"})
        assert r.status_code == 422, f"{code!r}: {r.text}"


def test_code_longer_than_32_chars_rejected_422(client):
    r = client.post("/locations", json={"code": "A" * 33, "name": "Too long"})
    assert r.status_code == 422, r.text


def test_empty_code_rejected_422(client):
    r = client.post("/locations", json={"code": "", "name": "Empty"})
    assert r.status_code == 422, r.text


def test_invalid_code_does_not_create_location(client):
    client.post("/locations", json={"code": "bad-code", "name": "Invalid"})
    r = client.get("/locations")
    assert r.status_code == 200
    assert all(loc["code"] != "bad-code" for loc in r.json())


def test_invalid_code_uses_uniform_error_shape(client):
    # T034 validation errors must follow the T050 error envelope.
    r = client.post("/locations", json={"code": "wh a", "name": "Bad"})
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "validation_error"
    assert "code" in body["error"]["message"]


# --- T026: locations can be deactivated ----------------------------------------


def test_new_location_is_active_by_default(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    assert r.json()["active"] is True

    got = client.get(f"/locations/{r.json()['id']}")
    assert got.status_code == 200
    assert got.json()["active"] is True


def test_locations_active_column_defaults_to_1_in_schema(tmp_path):
    from inventory.db import init_db

    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info('locations')")}
        assert "active" in cols
        conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'A')")
        active = conn.execute(
            "SELECT active FROM locations WHERE code = 'WH-A'"
        ).fetchone()[0]
        assert active == 1
    finally:
        conn.close()


def test_put_location_can_deactivate(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False

    got = client.get(f"/locations/{loc_a['id']}")
    assert got.status_code == 200
    assert got.json()["active"] is False


def test_put_location_can_reactivate(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True


def test_put_location_without_active_leaves_it_unchanged(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["active"] is False
    assert body["code"] == loc_a["code"]


def test_put_unknown_location_returns_404(client):
    r = client.put("/locations/9999", json={"active": False})
    assert r.status_code == 404, r.text


def test_list_locations_filters_by_active(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})

    active = client.get("/locations", params={"active": "true"})
    assert active.status_code == 200
    assert [loc["id"] for loc in active.json()] == [loc_a["id"]]
    assert all(loc["active"] is True for loc in active.json())

    inactive = client.get("/locations", params={"active": "false"})
    assert inactive.status_code == 200
    assert [loc["id"] for loc in inactive.json()] == [loc_b["id"]]
    assert all(loc["active"] is False for loc in inactive.json())


def test_list_locations_without_filter_returns_all(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})
    r = client.get("/locations")
    assert r.status_code == 200
    assert {loc["id"] for loc in r.json()} == {loc_a["id"], loc_b["id"]}


# --- T012: PUT /locations/{id} renames a location --------------------------------


def test_location_update_model_exists_with_optional_name_and_code():
    from inventory.models import LocationUpdate

    fields = LocationUpdate.model_fields
    assert "name" in fields
    assert "code" in fields
    # both optional: an empty payload must validate
    empty = LocationUpdate()
    assert empty.name is None
    assert empty.code is None


def test_put_location_renames_name(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Main Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Main Warehouse"
    assert body["code"] == loc_a["code"]  # code unchanged

    got = client.get(f"/locations/{loc_a['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "Main Warehouse"


def test_put_location_updates_code(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-NEW"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-NEW"
    assert body["name"] == loc_a["name"]  # name unchanged

    got = client.get(f"/locations/{loc_a['id']}")
    assert got.status_code == 200
    assert got.json()["code"] == "WH-NEW"


def test_put_location_updates_name_and_code_together(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "Renamed", "code": "WH-R"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["code"] == "WH-R"


def test_put_location_empty_payload_is_noop(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == loc_a["name"]
    assert body["code"] == loc_a["code"]


def test_put_location_unknown_id_returns_404(client):
    r = client.put("/locations/424242", json={"name": "Ghost", "code": "GH-1"})
    assert r.status_code == 404, r.text


def test_put_location_invalid_code_rejected_422(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "bad code"})
    assert r.status_code == 422, r.text
    # unchanged
    got = client.get(f"/locations/{loc_a['id']}")
    assert got.json()["code"] == loc_a["code"]


def test_put_location_duplicate_code_returns_409(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"code": loc_a["code"]})
    assert r.status_code == 409, r.text
    # unchanged
    got = client.get(f"/locations/{loc_b['id']}")
    assert got.json()["code"] == loc_b["code"]


# --- T013: DELETE /locations/{id} ----------------------------------------------


def _receive(client, item, loc, qty):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": qty, "to_location_id": loc["id"]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_location_returns_204_and_location_is_gone(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text

    got = client.get(f"/locations/{loc_a['id']}")
    assert got.status_code == 404

    listed = client.get("/locations")
    assert listed.status_code == 200
    assert all(loc["id"] != loc_a["id"] for loc in listed.json())


def test_delete_unknown_location_returns_404(client):
    r = client.delete("/locations/9999")
    assert r.status_code == 404, r.text


def test_delete_location_with_stock_returns_409(client, item, loc_a):
    _receive(client, item, loc_a, 5)

    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409, r.text

    # location still exists
    got = client.get(f"/locations/{loc_a['id']}")
    assert got.status_code == 200


def test_delete_location_allowed_when_stock_level_is_zero(client, item, loc_a):
    # Create a stock_levels row for loc_a, then bring its qty back to 0.
    _receive(client, item, loc_a, 5)
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 5, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text

    s = client.get(f"/locations/{loc_a['id']}/stock").json()
    assert all(lvl["quantity"] == 0 for lvl in s["levels"])

    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


def test_delete_location_409_only_for_that_location(client, item, loc_a, loc_b):
    # stock in loc_a must not block deleting empty loc_b
    _receive(client, item, loc_a, 3)

    r = client.delete(f"/locations/{loc_b['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_b['id']}").status_code == 404
    # loc_a with stock still refuses deletion
    assert client.delete(f"/locations/{loc_a['id']}").status_code == 409
