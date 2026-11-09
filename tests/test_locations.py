"""Tests for location endpoints, including activation/deactivation."""

import pytest


def test_create_location_defaults_to_active(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active"] is True


class TestCreateLocation:
    def test_duplicate_code_returns_409(self, client, loc_a):
        r = client.post("/locations", json={"code": loc_a["code"], "name": "Another"})
        assert r.status_code == 409, r.text
        assert loc_a["code"] in r.json()["error"]["message"]

    def test_duplicate_code_does_not_create_location(self, client, loc_a):
        client.post("/locations", json={"code": loc_a["code"], "name": "Another"})
        r = client.get("/locations")
        assert r.status_code == 200
        codes = [loc["code"] for loc in r.json()]
        assert codes.count(loc_a["code"]) == 1

    def test_distinct_codes_are_accepted(self, client, loc_a):
        r = client.post("/locations", json={"code": "WH-Z", "name": "Warehouse Z"})
        assert r.status_code == 201, r.text
        assert r.json()["code"] == "WH-Z"


class TestLocationCodeFormat:
    @pytest.mark.parametrize(
        "code",
        ["WH-A", "A", "0", "WH-MAIN-01", "X" * 32, "A" + "-" * 31],
    )
    def test_valid_codes_are_accepted(self, client, code):
        r = client.post("/locations", json={"code": code, "name": "Some place"})
        assert r.status_code == 201, r.text
        assert r.json()["code"] == code

    @pytest.mark.parametrize(
        "code",
        [
            "wh-a",  # lowercase not allowed
            "-WH",  # must not start with a hyphen
            "WH A",  # spaces not allowed
            "WH_A",  # underscores not allowed
            "WH.A",  # dots not allowed
            "X" * 33,  # too long
            "",  # empty
        ],
    )
    def test_invalid_codes_return_422(self, client, code):
        r = client.post("/locations", json={"code": code, "name": "Some place"})
        assert r.status_code == 422, r.text

    def test_update_with_invalid_code_returns_422(self, client, loc_a):
        r = client.put(f"/locations/{loc_a['id']}", json={"code": "bad code"})
        assert r.status_code == 422, r.text

    def test_update_with_valid_code_still_works(self, client, loc_a):
        r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-A2"})
        assert r.status_code == 200, r.text
        assert r.json()["code"] == "WH-A2"

    def test_invalid_code_does_not_create_location(self, client):
        client.post("/locations", json={"code": "bad!", "name": "Nope"})
        r = client.get("/locations")
        assert r.status_code == 200
        assert r.json() == []


class TestLocationsSchema:
    def test_locations_code_is_unique_in_schema(self, tmp_path):
        import sqlite3

        from inventory.db import init_db

        db_path = str(tmp_path / "schema.db")
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
            import pytest

            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
        finally:
            conn.close()


def test_get_location_includes_active(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_put_location_can_deactivate_and_reactivate(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False

    r = client.get(f"/locations/{loc_a['id']}")
    assert r.json()["active"] is False

    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_put_location_can_update_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"code": "WH-A2", "name": "Warehouse A2"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-A2"
    assert body["name"] == "Warehouse A2"
    assert body["active"] is True


def test_put_location_404_for_missing(client):
    r = client.put("/locations/9999", json={"active": False})
    assert r.status_code == 404


def test_list_locations_filters_by_active(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"active": False})
    assert r.status_code == 200

    r = client.get("/locations")
    assert r.status_code == 200
    assert {loc["id"] for loc in r.json()} == {loc_a["id"], loc_b["id"]}

    r = client.get("/locations", params={"active": "true"})
    assert r.status_code == 200
    assert [loc["id"] for loc in r.json()] == [loc_a["id"]]

    r = client.get("/locations", params={"active": "false"})
    assert r.status_code == 200
    assert [loc["id"] for loc in r.json()] == [loc_b["id"]]


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "WH-A" in body["error"]["message"]


def test_distinct_location_codes_allowed(client, loc_a):
    r = client.post("/locations", json={"code": "WH-C", "name": "Warehouse C"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "WH-C"


def test_locations_code_column_is_unique_in_schema():
    import sqlite3

    from inventory.db import SCHEMA

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        indexes = conn.execute("PRAGMA index_list('locations')").fetchall()
        unique_cols = set()
        for idx in indexes:
            if idx[2]:  # unique flag
                for info in conn.execute(f"PRAGMA index_info('{idx[1]}')"):
                    unique_cols.add(info[2])
        assert "code" in unique_cols
    finally:
        conn.close()
