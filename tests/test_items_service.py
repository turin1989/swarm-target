"""Unit tests for the item persistence helpers in inventory.services.items (T030)."""

import sqlite3

import pytest

from inventory.db import connect, init_db
from inventory.models import ItemCreate, ItemUpdate
from inventory.services import items as items_service


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "service.db")
    init_db(path)
    c = connect(path)
    try:
        yield c
    finally:
        c.close()


def test_create_item_returns_item_model(conn):
    item = items_service.create_item(
        conn,
        ItemCreate(sku="SVC-1", name="Service Widget", unit_price=3.5, reorder_point=2),
    )
    assert item.id == 1
    assert item.sku == "SVC-1"
    assert item.name == "Service Widget"
    assert item.unit_price == 3.5
    assert item.reorder_point == 2
    assert item.active is True
    assert item.created_at
    assert item.barcode is None


def test_create_item_stores_barcode(conn):
    item = items_service.create_item(
        conn, ItemCreate(sku="SVC-BC", name="Barcoded", barcode="0123456789012")
    )
    assert item.barcode == "0123456789012"


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    items_service.create_item(conn, ItemCreate(sku="DUP", name="One"))
    with pytest.raises(sqlite3.IntegrityError):
        items_service.create_item(conn, ItemCreate(sku="DUP", name="Two"))


def test_get_item_returns_none_for_missing(conn):
    assert items_service.get_item(conn, 999) is None


def test_get_item_roundtrip(conn):
    created = items_service.create_item(conn, ItemCreate(sku="GET-1", name="Gettable"))
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created


def test_update_item_applies_partial_update(conn):
    created = items_service.create_item(
        conn, ItemCreate(sku="UPD-1", name="Before", unit_price=1.0)
    )
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="After", active=False)
    )
    assert updated is not None
    assert updated.name == "After"
    assert updated.active is False
    # untouched fields preserved
    assert updated.sku == "UPD-1"
    assert updated.unit_price == 1.0


def test_update_item_with_no_fields_returns_unchanged(conn):
    created = items_service.create_item(conn, ItemCreate(sku="UPD-2", name="Same"))
    updated = items_service.update_item(conn, created.id, ItemUpdate())
    assert updated == created


def test_update_item_missing_returns_none(conn):
    assert items_service.update_item(conn, 12345, ItemUpdate(name="x")) is None


def test_delete_item_returns_true_then_false(conn):
    created = items_service.create_item(conn, ItemCreate(sku="DEL-1", name="Doomed"))
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None
    assert items_service.delete_item(conn, created.id) is False


def test_delete_item_missing_returns_false(conn):
    assert items_service.delete_item(conn, 777) is False


# --- api wiring ---------------------------------------------------------------


def test_api_routes_use_service_helpers(client, monkeypatch):
    """The HTTP layer delegates item persistence to inventory.services.items."""
    calls = []

    for name in ("get_item", "create_item", "update_item", "delete_item"):
        original = getattr(items_service, name)

        def tracked(*args, _original=original, _name=name, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(items_service, name, tracked)

    r = client.post("/items", json={"sku": "WIRE-1", "name": "Wired"})
    assert r.status_code == 201
    item_id = r.json()["id"]
    assert "create_item" in calls

    assert client.get(f"/items/{item_id}").status_code == 200
    assert "get_item" in calls

    r = client.put(f"/items/{item_id}", json={"name": "Rewired"})
    assert r.status_code == 200
    assert r.json()["name"] == "Rewired"
    assert "update_item" in calls

    assert client.delete(f"/items/{item_id}").status_code == 204
    assert "delete_item" in calls
    assert client.get(f"/items/{item_id}").status_code == 404
