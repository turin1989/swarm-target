"""Tests for location endpoints (T007: duplicate location codes)."""


def test_create_location(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "WH-A"
    assert body["name"] == "Warehouse A"


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text


def test_duplicate_location_error_detail_mentions_code(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    assert "WH-A" in r.json()["detail"]


def test_duplicate_does_not_create_extra_location(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Dup"})
    assert r.status_code == 409
    locations = client.get("/locations").json()
    assert [loc["code"] for loc in locations] == ["WH-A"]


def test_distinct_codes_still_allowed(client, loc_a, loc_b):
    codes = {loc["code"] for loc in client.get("/locations").json()}
    assert codes == {"WH-A", "WH-B"}


def test_locations_code_column_is_unique_in_schema(client, tmp_path):
    import sqlite3

    # The app fixture initialised the schema in tmp_path/test.db.
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        (ddl,) = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'locations'"
        ).fetchone()
    finally:
        conn.close()
    # The code column must carry a UNIQUE constraint.
    assert "UNIQUE" in ddl.upper()
    code_line = next(line for line in ddl.splitlines() if "code" in line)
    assert "UNIQUE" in code_line.upper()
