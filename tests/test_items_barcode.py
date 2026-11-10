"""Tests for the optional unique barcode on items (T025)."""


def _create(client, sku, barcode=None, **extra):
    payload = {"sku": sku, "name": f"Item {sku}", **extra}
    if barcode is not None:
        payload["barcode"] = barcode
    return client.post("/items", json=payload)


def test_create_item_without_barcode_defaults_to_null(client):
    r = _create(client, "NOBAR-1")
    assert r.status_code == 201, r.text
    assert r.json()["barcode"] is None


def test_create_item_with_barcode_round_trips(client):
    r = _create(client, "BAR-1", barcode="0123456789012")
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["barcode"] == "0123456789012"

    # Returned on fetch by id too.
    r = client.get(f"/items/{created['id']}")
    assert r.status_code == 200
    assert r.json()["barcode"] == "0123456789012"


def test_duplicate_barcode_returns_409(client):
    r = _create(client, "BAR-A", barcode="DUP-CODE")
    assert r.status_code == 201, r.text
    r = _create(client, "BAR-B", barcode="DUP-CODE")
    assert r.status_code == 409, r.text
    assert "barcode" in r.json()["detail"]


def test_multiple_items_without_barcode_are_allowed(client):
    assert _create(client, "NULL-1").status_code == 201
    assert _create(client, "NULL-2").status_code == 201
    assert _create(client, "NULL-3", barcode=None).status_code == 201


def test_get_items_filtered_by_barcode(client):
    a = _create(client, "FILT-A", barcode="CODE-A").json()
    _create(client, "FILT-B", barcode="CODE-B")
    _create(client, "FILT-C")

    r = client.get("/items", params={"barcode": "CODE-A"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == a["id"]
    assert body[0]["barcode"] == "CODE-A"
    assert r.headers["X-Total-Count"] == "1"


def test_get_items_filtered_by_unknown_barcode_returns_empty(client):
    _create(client, "FILT-D", barcode="CODE-D")
    r = client.get("/items", params={"barcode": "NO-SUCH-CODE"})
    assert r.status_code == 200
    assert r.json() == []


def test_bulk_create_with_duplicate_barcode_returns_409_and_rolls_back(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "BULK-1", "name": "Bulk 1", "barcode": "BULK-CODE"},
            {"sku": "BULK-2", "name": "Bulk 2", "barcode": "BULK-CODE"},
        ],
    )
    assert r.status_code == 409, r.text
    assert "barcode" in r.json()["detail"]
    # Nothing was persisted.
    r = client.get("/items", params={"sku": "BULK-1"})
    assert r.json() == []


def test_bulk_create_with_barcodes_persists_them(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "BULK-3", "name": "Bulk 3", "barcode": "BULK-CODE-3"},
            {"sku": "BULK-4", "name": "Bulk 4"},
        ],
    )
    assert r.status_code == 201, r.text
    by_sku = {i["sku"]: i for i in r.json()}
    assert by_sku["BULK-3"]["barcode"] == "BULK-CODE-3"
    assert by_sku["BULK-4"]["barcode"] is None


def test_barcode_migration_for_existing_database(tmp_path):
    """Databases created before the barcode column existed are migrated."""
    import sqlite3

    from fastapi.testclient import TestClient

    from inventory.main import create_app

    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            unit_price REAL NOT NULL DEFAULT 0,
            reorder_point INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );
        INSERT INTO items (sku, name) VALUES ('LEGACY-1', 'Legacy');
        """
    )
    conn.commit()
    conn.close()

    app = create_app(str(db_path))
    with TestClient(app) as client:
        r = client.get("/items", params={"sku": "LEGACY-1"})
        assert r.status_code == 200
        assert r.json()[0]["barcode"] is None

        r = _create(client, "NEW-1", barcode="MIGRATED-CODE")
        assert r.status_code == 201, r.text
        r = _create(client, "NEW-2", barcode="MIGRATED-CODE")
        assert r.status_code == 409
