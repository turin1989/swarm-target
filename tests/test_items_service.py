"""Unit tests for inventory.services.items (T030)."""

import sqlite3

import pytest

from inventory.db import connect, init_db
from inventory.models import Item, ItemCreate, ItemUpdate
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


def _create(conn, **overrides) -> Item:
    data = {"sku": "SVC-1", "name": "Service Widget", "unit_price": 2.5}
    data.update(overrides)
    return items_service.create_item(conn, ItemCreate(**data))


def test_create_item_returns_persisted_item(conn):
    item = _create(conn, description="desc", reorder_point=4, barcode="BC-1")
    assert isinstance(item, Item)
    assert item.id > 0
    assert item.sku == "SVC-1"
    assert item.name == "Service Widget"
    assert item.description == "desc"
    assert item.unit_price == 2.5
    assert item.reorder_point == 4
    assert item.barcode == "BC-1"
    assert item.active is True
    assert item.created_at


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    _create(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _create(conn, name="Another")


def test_get_item_returns_item(conn):
    created = _create(conn)
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created


def test_get_item_returns_none_for_missing(conn):
    assert items_service.get_item(conn, 9999) is None


def test_update_item_applies_fields(conn):
    created = _create(conn)
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="Renamed", unit_price=9.75, active=False)
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.unit_price == 9.75
    assert updated.active is False
    # untouched fields are preserved
    assert updated.sku == created.sku
    # change is persisted
    assert items_service.get_item(conn, created.id) == updated


def test_update_item_with_no_fields_returns_unchanged_item(conn):
    created = _create(conn)
    updated = items_service.update_item(conn, created.id, ItemUpdate())
    assert updated == created


def test_update_item_returns_none_for_missing(conn):
    assert items_service.update_item(conn, 9999, ItemUpdate(name="x")) is None


def test_delete_item_returns_true_and_removes_row(conn):
    created = _create(conn)
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None


def test_delete_item_returns_false_for_missing(conn):
    assert items_service.delete_item(conn, 9999) is False


def test_api_module_uses_items_service():
    """api.py delegates item persistence to the service instead of inline SQL."""
    import inspect

    from inventory import api

    source = inspect.getsource(api)
    assert "items_service" in source
    assert "INSERT INTO items" not in source
    assert "UPDATE items" not in source
    assert "DELETE FROM items" not in source
