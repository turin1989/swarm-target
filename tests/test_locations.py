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
    detail = r.json()["detail"]
    assert "WH-A" in detail


def test_duplicate_location_not_persisted(client, loc_a):
    client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_new_location_is_active_by_default(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    assert r.json()["active"] is True


def test_put_location_can_deactivate(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["code"] == loc_a["code"]

    # deactivation is persisted
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_put_location_can_reactivate(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True


def test_put_unknown_location_returns_404(client):
    r = client.put("/locations/999", json={"active": False})
    assert r.status_code == 404


def test_list_locations_filters_by_active(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"active": False})
    assert r.status_code == 200, r.text

    r = client.get("/locations", params={"active": "true"})
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-A"]

    r = client.get("/locations", params={"active": "false"})
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-B"]

    # no filter returns everything
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-A", "WH-B"]


def test_locations_active_column_in_schema(tmp_path):
    path = str(tmp_path / "active-schema.db")
    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        cols = {
            r["name"]: r
            for r in conn.execute("PRAGMA table_info(locations)").fetchall()
        }
        assert "active" in cols
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        row = conn.execute(
            "SELECT active FROM locations WHERE code = 'X'"
        ).fetchone()
        assert row["active"] == 1
    finally:
        conn.close()


def test_init_db_migrates_locations_without_active_column(tmp_path):
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
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
        conn.execute("INSERT INTO locations (code, name) VALUES ('OLD', 'Legacy')")
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
