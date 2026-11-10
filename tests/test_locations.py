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
