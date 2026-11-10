"""Direct tests for inventory.services.items persistence helpers."""

import sqlite3

import pytest

from inventory.db import SCHEMA
from inventory.models import Item, ItemCreate, ItemUpdate
from inventory.services import items as items_service


@pytest.fixture()
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


def test_create_item_returns_item_model(conn):
    item = items_service.create_item(
        conn, ItemCreate(sku="SVC-1", name="Service", unit_price=1.5, reorder_point=3)
    )
    assert isinstance(item, Item)
    assert item.id == 1
    assert item.sku == "SVC-1"
    assert item.name == "Service"
    assert item.unit_price == 1.5
    assert item.reorder_point == 3
    assert item.active is True


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    items_service.create_item(conn, ItemCreate(sku="DUP", name="First"))
    with pytest.raises(sqlite3.IntegrityError):
        items_service.create_item(conn, ItemCreate(sku="DUP", name="Second"))


def test_get_item_returns_none_for_missing(conn):
    assert items_service.get_item(conn, 999) is None


def test_get_item_round_trips_created_item(conn):
    created = items_service.create_item(conn, ItemCreate(sku="GET-1", name="Gettable"))
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created


def test_update_item_returns_none_for_missing(conn):
    assert items_service.update_item(conn, 42, ItemUpdate(name="x")) is None


def test_update_item_applies_partial_updates(conn):
    created = items_service.create_item(
        conn, ItemCreate(sku="UPD-1", name="Before", unit_price=2.0, reorder_point=4)
    )
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="After", unit_price=9.99)
    )
    assert updated is not None
    assert updated.name == "After"
    assert updated.unit_price == 9.99
    # untouched fields preserved
    assert updated.sku == "UPD-1"
    assert updated.reorder_point == 4


def test_update_item_can_deactivate(conn):
    created = items_service.create_item(conn, ItemCreate(sku="ACT-1", name="Active"))
    updated = items_service.update_item(conn, created.id, ItemUpdate(active=False))
    assert updated is not None
    assert updated.active is False
    fetched = items_service.get_item(conn, created.id)
    assert fetched is not None
    assert fetched.active is False


def test_delete_item_returns_true_when_deleted(conn):
    created = items_service.create_item(conn, ItemCreate(sku="DEL-1", name="Doomed"))
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None


def test_delete_item_returns_false_when_missing(conn):
    assert items_service.delete_item(conn, 123) is False
