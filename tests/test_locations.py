import sqlite3

import pytest

from inventory.db import init_db


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text


def test_duplicate_location_code_detail_mentions_code(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    assert "WH-A" in r.json()["detail"]


def test_distinct_location_codes_are_accepted(client, loc_a, loc_b):
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-A", "WH-B"]


def test_duplicate_does_not_create_extra_location(client, loc_a):
    client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    r = client.get("/locations")
    assert len(r.json()) == 1


def test_locations_code_column_is_unique_in_schema(tmp_path):
    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
    finally:
        conn.close()


@pytest.mark.parametrize(
    "code",
    [
        "WH-A",
        "WH-B",
        "A",
        "0",
        "A1-B2-C3",
        "X" * 32,
        "9-" + "A" * 30,
    ],
)
def test_valid_location_codes_are_accepted(client, code):
    r = client.post("/locations", json={"code": code, "name": "Some location"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == code


@pytest.mark.parametrize(
    "code",
    [
        "",  # empty
        "-WH",  # cannot start with hyphen
        "wh-a",  # lowercase not allowed
        "WH A",  # spaces not allowed
        "WH_A",  # underscore not allowed
        "WH.A",  # dot not allowed
        " WH-A",  # leading space
        "WH-A ",  # trailing space
        "X" * 33,  # too long (max 32)
        "Ü-1",  # non-ASCII letter
    ],
)
def test_invalid_location_codes_return_422(client, code):
    r = client.post("/locations", json={"code": code, "name": "Bad location"})
    assert r.status_code == 422, r.text


def test_invalid_code_does_not_create_location(client):
    client.post("/locations", json={"code": "bad code", "name": "Bad"})
    r = client.get("/locations")
    assert r.json() == []
