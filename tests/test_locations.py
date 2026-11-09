import pytest


class TestCreateLocation:
    def test_duplicate_code_returns_409(self, client, loc_a):
        r = client.post("/locations", json={"code": loc_a["code"], "name": "Another"})
        assert r.status_code == 409, r.text
        assert loc_a["code"] in r.json()["detail"]

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


class TestUpdateLocation:
    def test_rename_location(self, client, loc_a):
        r = client.put(f"/locations/{loc_a['id']}", json={"name": "Main Warehouse"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Main Warehouse"
        assert body["code"] == loc_a["code"]
        assert body["id"] == loc_a["id"]

    def test_update_code(self, client, loc_a):
        r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-MAIN"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["code"] == "WH-MAIN"
        assert body["name"] == loc_a["name"]

    def test_update_both_fields(self, client, loc_a):
        r = client.put(
            f"/locations/{loc_a['id']}",
            json={"name": "Main Warehouse", "code": "WH-MAIN"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {
            "id": loc_a["id"],
            "name": "Main Warehouse",
            "code": "WH-MAIN",
            "active": True,
        }

    def test_empty_payload_is_noop(self, client, loc_a):
        r = client.put(f"/locations/{loc_a['id']}", json={})
        assert r.status_code == 200, r.text
        assert r.json() == loc_a

    def test_update_persists(self, client, loc_a):
        client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
        r = client.get(f"/locations/{loc_a['id']}")
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_unknown_id_returns_404(self, client):
        r = client.put("/locations/9999", json={"name": "Nope"})
        assert r.status_code == 404


class TestLocationActive:
    def test_new_location_is_active_by_default(self, client, loc_a):
        assert loc_a["active"] is True

    def test_deactivate_location(self, client, loc_a):
        r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
        assert r.status_code == 200, r.text
        assert r.json()["active"] is False

    def test_deactivation_persists(self, client, loc_a):
        client.put(f"/locations/{loc_a['id']}", json={"active": False})
        r = client.get(f"/locations/{loc_a['id']}")
        assert r.status_code == 200
        assert r.json()["active"] is False

    def test_reactivate_location(self, client, loc_a):
        client.put(f"/locations/{loc_a['id']}", json={"active": False})
        r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
        assert r.status_code == 200, r.text
        assert r.json()["active"] is True

    def test_deactivate_does_not_touch_other_fields(self, client, loc_a):
        r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
        body = r.json()
        assert body["code"] == loc_a["code"]
        assert body["name"] == loc_a["name"]

    def test_list_filter_active_true(self, client, loc_a, loc_b):
        client.put(f"/locations/{loc_b['id']}", json={"active": False})
        r = client.get("/locations", params={"active": "true"})
        assert r.status_code == 200
        ids = [loc["id"] for loc in r.json()]
        assert ids == [loc_a["id"]]

    def test_list_filter_active_false(self, client, loc_a, loc_b):
        client.put(f"/locations/{loc_b['id']}", json={"active": False})
        r = client.get("/locations", params={"active": "false"})
        assert r.status_code == 200
        ids = [loc["id"] for loc in r.json()]
        assert ids == [loc_b["id"]]

    def test_list_without_filter_returns_all(self, client, loc_a, loc_b):
        client.put(f"/locations/{loc_b['id']}", json={"active": False})
        r = client.get("/locations")
        assert r.status_code == 200
        ids = [loc["id"] for loc in r.json()]
        assert ids == [loc_a["id"], loc_b["id"]]

    def test_active_column_migration_for_old_databases(self, tmp_path):
        import sqlite3

        from inventory.db import init_db

        db_path = str(tmp_path / "old.db")
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL
                )
                """
            )
            conn.execute("INSERT INTO locations (code, name) VALUES ('OLD', 'Old loc')")
            conn.commit()
        finally:
            conn.close()
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM locations WHERE code = 'OLD'").fetchone()
            assert row["active"] == 1
        finally:
            conn.close()
