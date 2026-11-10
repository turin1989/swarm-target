"""Item persistence helpers in inventory.services.items (T030)."""

import sqlite3

import pytest

from inventory.db import connect, init_db
from inventory.models import Item, ItemCreate, ItemUpdate
from inventory.services import items as items_service


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def test_create_item_returns_item_model(conn):
    item = items_service.create_item(
        conn,
        ItemCreate(sku="svc-1", name="Service One", unit_price=3.5, reorder_point=2),
    )
    assert isinstance(item, Item)
    assert item.id > 0
    assert item.sku == "SVC-1"  # sku normalisation still applies
    assert item.name == "Service One"
    assert item.unit_price == 3.5
    assert item.reorder_point == 2
    assert item.active is True
    assert item.barcode is None


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    items_service.create_item(conn, ItemCreate(sku="DUP-1", name="One"))
    with pytest.raises(sqlite3.IntegrityError):
        items_service.create_item(conn, ItemCreate(sku="DUP-1", name="Two"))


def test_get_item_returns_item_or_none(conn):
    created = items_service.create_item(conn, ItemCreate(sku="GET-1", name="Get"))
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created
    assert items_service.get_item(conn, 9999) is None


def test_update_item_applies_changes(conn):
    created = items_service.create_item(conn, ItemCreate(sku="UPD-1", name="Before"))
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="After", unit_price=9.99, active=False)
    )
    assert updated is not None
    assert updated.name == "After"
    assert updated.unit_price == 9.99
    assert updated.active is False
    # persisted, not just returned
    assert items_service.get_item(conn, created.id) == updated


def test_update_item_missing_returns_none(conn):
    assert items_service.update_item(conn, 12345, ItemUpdate(name="Nope")) is None


def test_update_item_empty_payload_is_noop(conn):
    created = items_service.create_item(conn, ItemCreate(sku="NOOP-1", name="Same"))
    assert items_service.update_item(conn, created.id, ItemUpdate()) == created


def test_delete_item_returns_true_then_false(conn):
    created = items_service.create_item(conn, ItemCreate(sku="DEL-1", name="Del"))
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None
    assert items_service.delete_item(conn, created.id) is False


# --- api.py delegates to the service ------------------------------------------


def test_api_create_and_get_use_service(client, monkeypatch):
    calls = {"create": 0, "get": 0}
    real_create = items_service.create_item
    real_get = items_service.get_item

    def spy_create(conn, payload):
        calls["create"] += 1
        return real_create(conn, payload)

    def spy_get(conn, item_id):
        calls["get"] += 1
        return real_get(conn, item_id)

    monkeypatch.setattr(items_service, "create_item", spy_create)
    monkeypatch.setattr(items_service, "get_item", spy_get)

    r = client.post("/items", json={"sku": "API-1", "name": "Api"})
    assert r.status_code == 201
    assert calls["create"] == 1

    item_id = r.json()["id"]
    assert client.get(f"/items/{item_id}").status_code == 200
    assert calls["get"] >= 1


def test_api_update_and_delete_use_service(client, monkeypatch):
    calls = {"update": 0, "delete": 0}
    real_update = items_service.update_item
    real_delete = items_service.delete_item

    def spy_update(conn, item_id, payload):
        calls["update"] += 1
        return real_update(conn, item_id, payload)

    def spy_delete(conn, item_id):
        calls["delete"] += 1
        return real_delete(conn, item_id)

    monkeypatch.setattr(items_service, "update_item", spy_update)
    monkeypatch.setattr(items_service, "delete_item", spy_delete)

    r = client.post("/items", json={"sku": "API-2", "name": "Api Two"})
    item_id = r.json()["id"]

    r = client.put(f"/items/{item_id}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert calls["update"] == 1

    assert client.delete(f"/items/{item_id}").status_code == 204
    assert calls["delete"] == 1
    assert client.get(f"/items/{item_id}").status_code == 404
