"""Unit tests for the inventory.services.items persistence helpers (T030)."""

import pytest

from inventory.db import connect, init_db
from inventory.models import Item, ItemCreate, ItemUpdate
from inventory.services import items as items_service
from inventory.services.errors import ConflictError


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    c = connect(path)
    yield c
    c.close()


def _payload(**overrides) -> ItemCreate:
    base = {"sku": "SVC-1", "name": "Service Widget", "unit_price": 3.5, "reorder_level": 2}
    base.update(overrides)
    return ItemCreate(**base)


def test_create_item_returns_persisted_item(conn):
    item = items_service.create_item(conn, _payload())
    assert isinstance(item, Item)
    assert item.id == 1
    assert item.sku == "SVC-1"
    assert item.name == "Service Widget"
    assert item.unit_price == 3.5
    assert item.reorder_level == 2
    assert item.active is True


def test_create_item_duplicate_sku_raises_conflict(conn):
    items_service.create_item(conn, _payload())
    with pytest.raises(ConflictError):
        items_service.create_item(conn, _payload(name="Dup"))


def test_get_item_returns_item(conn):
    created = items_service.create_item(conn, _payload())
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created


def test_get_item_missing_returns_none(conn):
    assert items_service.get_item(conn, 999) is None


def test_get_item_by_sku(conn):
    created = items_service.create_item(conn, _payload())
    assert items_service.get_item_by_sku(conn, "SVC-1") == created
    assert items_service.get_item_by_sku(conn, "NOPE") is None


def test_update_item_applies_set_fields_only(conn):
    created = items_service.create_item(conn, _payload())
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="Renamed", unit_price=9.99)
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.unit_price == 9.99
    # untouched fields preserved
    assert updated.sku == created.sku
    assert updated.reorder_level == created.reorder_level


def test_update_item_active_flag_round_trips_as_bool(conn):
    created = items_service.create_item(conn, _payload())
    updated = items_service.update_item(conn, created.id, ItemUpdate(active=False))
    assert updated is not None
    assert updated.active is False
    assert items_service.get_item(conn, created.id).active is False


def test_update_item_missing_returns_none(conn):
    assert items_service.update_item(conn, 42, ItemUpdate(name="x")) is None


def test_update_item_empty_payload_is_noop(conn):
    created = items_service.create_item(conn, _payload())
    updated = items_service.update_item(conn, created.id, ItemUpdate())
    assert updated == created


def test_delete_item_returns_true_then_false(conn):
    created = items_service.create_item(conn, _payload())
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None
    assert items_service.delete_item(conn, created.id) is False


def test_delete_missing_item_returns_false(conn):
    assert items_service.delete_item(conn, 999) is False
