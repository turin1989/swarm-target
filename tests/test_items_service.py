"""Unit tests for inventory.services.items persistence helpers."""

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


def test_create_item_returns_item_model(conn):
    item = items_service.create_item(
        conn, ItemCreate(sku="SVC-1", name="Svc", unit_price=3.5, reorder_point=2)
    )
    assert isinstance(item, Item)
    assert item.id == 1
    assert item.sku == "SVC-1"
    assert item.name == "Svc"
    assert item.unit_price == 3.5
    assert item.reorder_point == 2
    assert item.active is True


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    items_service.create_item(conn, ItemCreate(sku="DUP", name="One"))
    with pytest.raises(sqlite3.IntegrityError):
        items_service.create_item(conn, ItemCreate(sku="DUP", name="Two"))


def test_get_item_returns_item_or_none(conn):
    created = items_service.create_item(conn, ItemCreate(sku="G-1", name="Get"))
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created
    assert items_service.get_item(conn, 999) is None


def test_update_item_partial_update(conn):
    created = items_service.create_item(
        conn, ItemCreate(sku="U-1", name="Before", unit_price=1.0)
    )
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="After", unit_price=9.99)
    )
    assert updated is not None
    assert updated.name == "After"
    assert updated.unit_price == 9.99
    # untouched fields preserved
    assert updated.sku == created.sku
    assert updated.active is True


def test_update_item_deactivate(conn):
    created = items_service.create_item(conn, ItemCreate(sku="U-2", name="Act"))
    updated = items_service.update_item(conn, created.id, ItemUpdate(active=False))
    assert updated is not None
    assert updated.active is False


def test_update_missing_item_returns_none(conn):
    assert items_service.update_item(conn, 42, ItemUpdate(name="x")) is None


def test_delete_item_returns_true_then_false(conn):
    created = items_service.create_item(conn, ItemCreate(sku="D-1", name="Del"))
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None
    assert items_service.delete_item(conn, created.id) is False


def test_delete_missing_item_returns_false(conn):
    assert items_service.delete_item(conn, 999) is False
