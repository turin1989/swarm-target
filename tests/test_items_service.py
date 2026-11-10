"""Tests for inventory.services.items persistence helpers (T030)."""

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


def test_create_item_returns_item(conn):
    item = items_service.create_item(
        conn,
        ItemCreate(sku="svc-1", name="Service Widget", unit_price=1.25, reorder_level=3),
    )
    assert isinstance(item, Item)
    assert item.id > 0
    assert item.sku == "SVC-1"  # sku is normalised to upper case
    assert item.name == "Service Widget"
    assert item.unit_price == 1.25
    assert item.reorder_level == 3
    assert item.active is True
    assert item.created_at  # timestamp populated by the service


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    items_service.create_item(conn, ItemCreate(sku="SVC-DUP", name="One"))
    with pytest.raises(sqlite3.IntegrityError):
        items_service.create_item(conn, ItemCreate(sku="SVC-DUP", name="Two"))


def test_get_item_found_and_missing(conn):
    created = items_service.create_item(conn, ItemCreate(sku="SVC-GET", name="Gettable"))
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created
    assert items_service.get_item(conn, created.id + 999) is None


def test_update_item_applies_fields(conn):
    created = items_service.create_item(conn, ItemCreate(sku="SVC-UPD", name="Before"))
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="After", unit_price=9.5, active=False)
    )
    assert updated is not None
    assert updated.name == "After"
    assert updated.unit_price == 9.5
    assert updated.active is False
    # untouched fields stay the same
    assert updated.sku == created.sku
    assert updated.created_at == created.created_at


def test_update_item_missing_returns_none(conn):
    assert items_service.update_item(conn, 12345, ItemUpdate(name="Nope")) is None


def test_update_item_noop_returns_item(conn):
    created = items_service.create_item(conn, ItemCreate(sku="SVC-NOOP", name="Same"))
    updated = items_service.update_item(conn, created.id, ItemUpdate())
    assert updated == created


def test_delete_item_returns_bool(conn):
    created = items_service.create_item(conn, ItemCreate(sku="SVC-DEL", name="Doomed"))
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None
    assert items_service.delete_item(conn, created.id) is False
