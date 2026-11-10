import sqlite3

from inventory import db


def test_create_location(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "WH-A"
    assert body["name"] == "Warehouse A"


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    message = r.json()["error"]["message"]
    assert "WH-A" in message


def test_duplicate_location_not_persisted(client, loc_a):
    client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_update_location_name_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Renamed Warehouse"
    assert body["code"] == "WH-A"  # unchanged


def test_update_location_code_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-Z"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-Z"
    assert body["name"] == "Warehouse A"  # unchanged


def test_update_location_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"code": "WH-Z", "name": "Zed Warehouse"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-Z"
    assert body["name"] == "Zed Warehouse"


def test_update_location_empty_payload_returns_location_unchanged(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_location_is_persisted(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed Warehouse"})
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed Warehouse"


def test_update_unknown_location_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Ghost"})
    assert r.status_code == 404, r.text


def test_update_location_duplicate_code_returns_409(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"code": "WH-A"})
    assert r.status_code == 409, r.text


def test_update_location_invalid_code_rejected(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "bad code!"})
    assert r.status_code == 422, r.text


def test_location_update_model_exists():
    from inventory.models import LocationUpdate

    update = LocationUpdate()
    assert update.name is None
    assert update.code is None


def test_locations_code_column_is_unique_in_schema(tmp_path):
    path = str(tmp_path / "schema.db")
    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        unique_cols = set()
        for index in conn.execute("PRAGMA index_list('locations')").fetchall():
            if index["unique"]:
                for col in conn.execute(
                    f"PRAGMA index_info('{index['name']}')"
                ).fetchall():
                    unique_cols.add(col["name"])
        assert "code" in unique_cols

        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate code insert should violate UNIQUE constraint")
    finally:
        conn.close()


# --- T026: locations can be deactivated ---------------------------------------


def test_new_location_is_active_by_default(client):
    r = client.post("/locations", json={"code": "WH-N", "name": "New Warehouse"})
    assert r.status_code == 201, r.text
    assert r.json()["active"] is True


def test_put_can_deactivate_location(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["code"] == loc_a["code"]  # unchanged
    assert body["name"] == loc_a["name"]  # unchanged


def test_put_can_reactivate_location(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True


def test_deactivation_is_persisted(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_put_without_active_leaves_flag_unchanged(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False


def test_list_locations_filters_by_active(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})

    r = client.get("/locations", params={"active": "true"})
    assert r.status_code == 200, r.text
    ids = [loc["id"] for loc in r.json()]
    assert loc_a["id"] in ids
    assert loc_b["id"] not in ids
    assert all(loc["active"] is True for loc in r.json())

    r = client.get("/locations", params={"active": "false"})
    assert r.status_code == 200, r.text
    ids = [loc["id"] for loc in r.json()]
    assert ids == [loc_b["id"]]
    assert all(loc["active"] is False for loc in r.json())


def test_list_locations_without_filter_returns_all(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})
    r = client.get("/locations")
    assert r.status_code == 200
    ids = {loc["id"] for loc in r.json()}
    assert {loc_a["id"], loc_b["id"]} <= ids


def test_locations_active_column_in_schema(tmp_path):
    path = str(tmp_path / "schema.db")
    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        cols = {
            r["name"]: r
            for r in conn.execute("PRAGMA table_info(locations)").fetchall()
        }
        assert "active" in cols
        conn.execute("INSERT INTO locations (code, name) VALUES ('Y', 'default')")
        row = conn.execute(
            "SELECT active FROM locations WHERE code = 'Y'"
        ).fetchone()
        assert row["active"] == 1
    finally:
        conn.close()


def test_locations_active_column_migration(tmp_path):
    """Old databases without locations.active get the column added by init_db."""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE locations ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "code TEXT NOT NULL UNIQUE, "
            "name TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO locations (code, name) VALUES ('OLD', 'legacy')")
        conn.commit()
    finally:
        conn.close()

    db.init_db(path)

    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT active FROM locations WHERE code = 'OLD'"
        ).fetchone()
        assert row["active"] == 1
    finally:
        conn.close()
