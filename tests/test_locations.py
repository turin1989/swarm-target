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
