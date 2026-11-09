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
        assert body == {"id": loc_a["id"], "name": "Main Warehouse", "code": "WH-MAIN"}

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
