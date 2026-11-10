"""Unit tests for inventory.services.items (T030 refactor)."""

import sqlite3

import pytest

from inventory.db import connect, init_db
from inventory.models import Item, ItemCreate, ItemUpdate
from inventory.services import items as items_service


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    c = connect(path)
    yield c
    c.close()


def _make(conn, sku="SVC-1", **kwargs) -> Item:
    payload = ItemCreate(sku=sku, name=kwargs.pop("name", "Service Item"), **kwargs)
    return items_service.create_item(conn, payload)


# --- create_item ---------------------------------------------------------------


def test_create_item_returns_item_model(conn):
    item = _make(conn, unit_price=3.5, reorder_point=7, description="desc")
    assert isinstance(item, Item)
    assert item.id == 1
    assert item.sku == "SVC-1"
    assert item.name == "Service Item"
    assert item.unit_price == 3.5
    assert item.reorder_point == 7
    assert item.description == "desc"
    assert item.active is True
    assert item.created_at  # set at insert time


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    _make(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _make(conn)


# --- get_item ------------------------------------------------------------------


def test_get_item_returns_persisted_item(conn):
    created = _make(conn)
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created


def test_get_item_missing_returns_none(conn):
    assert items_service.get_item(conn, 999) is None


def test_get_item_by_sku(conn):
    created = _make(conn, sku="BY-SKU")
    assert items_service.get_item_by_sku(conn, "BY-SKU") == created
    assert items_service.get_item_by_sku(conn, "NOPE") is None


# --- update_item ---------------------------------------------------------------


def test_update_item_partial_fields(conn):
    created = _make(conn, unit_price=1.0)
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="Renamed", unit_price=9.99)
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.unit_price == 9.99
    # untouched fields preserved
    assert updated.sku == created.sku
    assert updated.created_at == created.created_at


def test_update_item_deactivate(conn):
    created = _make(conn)
    updated = items_service.update_item(conn, created.id, ItemUpdate(active=False))
    assert updated is not None
    assert updated.active is False


def test_update_item_noop_returns_current_item(conn):
    created = _make(conn)
    updated = items_service.update_item(conn, created.id, ItemUpdate())
    assert updated == created


def test_update_item_missing_returns_none(conn):
    assert items_service.update_item(conn, 42, ItemUpdate(name="x")) is None


# --- delete_item ---------------------------------------------------------------


def test_delete_item_returns_true_and_removes_row(conn):
    created = _make(conn)
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None


def test_delete_item_missing_returns_false(conn):
    assert items_service.delete_item(conn, 999) is False


def test_delete_item_twice_second_is_false(conn):
    created = _make(conn)
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.delete_item(conn, created.id) is False


# --- api wiring ----------------------------------------------------------------


def test_api_module_has_no_inline_item_sql():
    """api.py must delegate item persistence to the service layer."""
    import inspect

    from inventory import api

    source = inspect.getsource(api)
    assert "INSERT INTO items" not in source
    assert "UPDATE items" not in source
    assert "DELETE FROM items" not in source
    assert "SELECT * FROM items WHERE" not in source


def test_api_routes_use_service(client):
    r = client.post("/items", json={"sku": "WIRE-1", "name": "Wire"})
    assert r.status_code == 201
    item_id = r.json()["id"]
    assert client.get(f"/items/{item_id}").status_code == 200
    assert client.put(f"/items/{item_id}", json={"name": "Rewired"}).json()["name"] == "Rewired"
    assert client.delete(f"/items/{item_id}").status_code == 204
    assert client.get(f"/items/{item_id}").status_code == 404
