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
