from inventory import db


def test_init_db_records_version_1(tmp_path):
    path = str(tmp_path / "v.db")
    db.init_db(path)
    assert db.get_schema_version(path) == 1


def test_schema_version_table_has_single_row(tmp_path):
    path = str(tmp_path / "v.db")
    db.init_db(path)
    conn = db.connect(path)
    try:
        rows = conn.execute("SELECT version FROM schema_version").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["version"] == 1


def test_init_db_idempotent(tmp_path):
    path = str(tmp_path / "v.db")
    db.init_db(path)
    db.init_db(path)
    assert db.get_schema_version(path) == 1
    conn = db.connect(path)
    try:
        count = conn.execute("SELECT COUNT(*) AS n FROM schema_version").fetchone()["n"]
    finally:
        conn.close()
    assert count == 1
