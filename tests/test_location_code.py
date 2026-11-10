import pytest


def _create(client, code):
    return client.post("/locations", json={"code": code, "name": "Loc"})


@pytest.mark.parametrize(
    "code",
    [
        "WH-A",
        "A",
        "0",
        "WH-B-2",
        "A" * 32,
        "A" + "-" * 31,
    ],
)
def test_valid_location_codes_accepted(client, code):
    r = _create(client, code)
    assert r.status_code == 201, r.text
    assert r.json()["code"] == code


@pytest.mark.parametrize(
    "code",
    [
        "",            # empty
        "-WH",         # cannot start with hyphen
        "wh-a",        # lowercase not allowed
        "WH A",        # spaces not allowed
        "WH_A",        # underscore not allowed
        "WH.A",        # dot not allowed
        "A" * 33,      # too long (max 32 chars)
        "WH-A\n",      # trailing newline not allowed
    ],
)
def test_invalid_location_codes_rejected(client, code):
    r = _create(client, code)
    assert r.status_code == 422, r.text


# --- duplicate codes (T007) ----------------------------------------------------


def test_duplicate_location_code_returns_409(client):
    r = _create(client, "WH-A")
    assert r.status_code == 201, r.text
    r = client.post("/locations", json={"code": "WH-A", "name": "Another name"})
    assert r.status_code == 409, r.text


def test_duplicate_location_code_error_detail_mentions_code(client):
    _create(client, "WH-DUP")
    r = _create(client, "WH-DUP")
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "WH-DUP" in body["error"]["message"]


def test_duplicate_code_does_not_create_second_location(client):
    _create(client, "WH-A")
    _create(client, "WH-A")
    r = client.get("/locations")
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_locations_code_column_is_unique_in_schema(tmp_path):
    """The locations.code column carries a UNIQUE constraint at the DB level."""
    import sqlite3

    from inventory.db import connect, init_db

    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = connect(db_path)
    try:
        # Inserting directly (bypassing the API) must still be rejected.
        conn.execute("INSERT INTO locations (code, name) VALUES ('WH-X', 'One')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO locations (code, name) VALUES ('WH-X', 'Two')")
        # And the schema itself declares code UNIQUE (column constraint or index).
        table_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='locations'"
        ).fetchone()["sql"]
        unique_indexes = conn.execute(
            "PRAGMA index_list(locations)"
        ).fetchall()
        has_unique_index = any(ix["unique"] for ix in unique_indexes)
        assert "UNIQUE" in table_sql.upper() or has_unique_index
    finally:
        conn.close()


def test_unique_index_applied_to_pre_existing_database(tmp_path):
    """Databases created before the UNIQUE constraint gain it via init_db."""
    import sqlite3

    from inventory.db import init_db

    db_path = str(tmp_path / "legacy.db")
    legacy = sqlite3.connect(db_path)
    legacy.executescript(
        """
        CREATE TABLE locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT NOT NULL
        );
        """
    )
    legacy.commit()
    legacy.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO locations (code, name) VALUES ('WH-L', 'Legacy')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO locations (code, name) VALUES ('WH-L', 'Again')")
    finally:
        conn.close()
