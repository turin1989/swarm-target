from inventory import db


def test_fresh_db_records_version_1(tmp_path):
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


def test_init_db_is_idempotent(tmp_path):
    path = str(tmp_path / "v.db")
    db.init_db(path)
    db.init_db(path)
    assert db.get_schema_version(path) == 1
    conn = db.connect(path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    finally:
        conn.close()
    assert count == 1


def test_init_db_twice_preserves_data(tmp_path):
    path = str(tmp_path / "v.db")
    db.init_db(path)
    conn = db.connect(path)
    try:
        conn.execute(
            "INSERT INTO items (sku, name) VALUES (?, ?)", ("SKU-1", "Thing")
        )
        conn.commit()
    finally:
        conn.close()
    db.init_db(path)
    conn = db.connect(path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM items").fetchone()
    finally:
        conn.close()
    assert count == 1
