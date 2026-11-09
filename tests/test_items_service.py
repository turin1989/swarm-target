"""Unit tests for inventory.services.items persistence helpers."""

import sqlite3

import pytest

from inventory.db import connect, init_db
from inventory.models import ItemCreate, ItemUpdate
from inventory.services import items as items_service


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    c = connect(path)
    try:
        yield c
    finally:
        c.close()


def _create(conn, **overrides):
    payload = {"sku": "SKU-1", "name": "Thing", "unit_price": 1.5, "reorder_point": 2}
    payload.update(overrides)
    return items_service.create_item(conn, ItemCreate(**payload))


def test_create_item_returns_item(conn):
    item = _create(conn)
    assert item.id == 1
    assert item.sku == "SKU-1"
    assert item.name == "Thing"
    assert item.unit_price == 1.5
    assert item.reorder_point == 2
    assert item.active is True


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    _create(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _create(conn, name="Dup")


def test_get_item_returns_none_for_missing(conn):
    assert items_service.get_item(conn, 999) is None


def test_get_item_round_trip(conn):
    created = _create(conn)
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created


def test_update_item_partial_fields(conn):
    created = _create(conn)
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="Renamed", unit_price=9.99)
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.unit_price == 9.99
    # untouched fields preserved
    assert updated.sku == created.sku
    assert updated.reorder_point == created.reorder_point


def test_update_item_deactivate(conn):
    created = _create(conn)
    updated = items_service.update_item(conn, created.id, ItemUpdate(active=False))
    assert updated is not None
    assert updated.active is False


def test_update_missing_item_returns_none(conn):
    assert items_service.update_item(conn, 42, ItemUpdate(name="x")) is None


def test_delete_item_returns_true_then_false(conn):
    created = _create(conn)
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None
    assert items_service.delete_item(conn, created.id) is False


def test_list_items_order_filter_and_limit(conn):
    for sku in ["C", "A", "B"]:
        _create(conn, sku=sku, name=sku)
    assert [i.sku for i in items_service.list_items(conn)] == ["C", "A", "B"]
    assert [i.sku for i in items_service.list_items(conn, limit=2)] == ["C", "A"]
    assert [i.sku for i in items_service.list_items(conn, limit=2, offset=2)] == ["B"]

    items_service.update_item(conn, 2, ItemUpdate(active=False))
    assert [i.sku for i in items_service.list_items(conn, active=True)] == ["C", "B"]
    assert [i.sku for i in items_service.list_items(conn, active=False)] == ["A"]


def test_list_items_sorting(conn):
    for sku, name in [("S1", "Charlie"), ("S2", "Alpha"), ("S3", "Bravo")]:
        _create(conn, sku=sku, name=name)
    assert [i.name for i in items_service.list_items(conn, sort="name")] == [
        "Alpha",
        "Bravo",
        "Charlie",
    ]
    assert [i.name for i in items_service.list_items(conn, sort="name", descending=True)] == [
        "Charlie",
        "Bravo",
        "Alpha",
    ]
    assert [i.sku for i in items_service.list_items(conn, sort="sku")] == ["S1", "S2", "S3"]
    assert [i.sku for i in items_service.list_items(conn, sort="id", descending=True)] == [
        "S3",
        "S2",
        "S1",
    ]


def test_list_items_invalid_sort_raises(conn):
    with pytest.raises(ValueError):
        items_service.list_items(conn, sort="unit_price")


def test_list_items_filter_sku_exact(conn):
    for sku in ["WIDGET-1", "WIDGET-2"]:
        _create(conn, sku=sku, name=sku)
    assert [i.sku for i in items_service.list_items(conn, sku="WIDGET-1")] == ["WIDGET-1"]
    # no partial matches
    assert items_service.list_items(conn, sku="WIDGET") == []
    assert items_service.list_items(conn, sku="NOPE") == []


def test_list_items_filter_sku_combined_with_active(conn):
    for sku in ["WIDGET-1", "GADGET-1"]:
        _create(conn, sku=sku, name=sku)
    items_service.update_item(conn, 2, ItemUpdate(active=False))
    assert [i.sku for i in items_service.list_items(conn, sku="WIDGET-1", active=True)] == [
        "WIDGET-1"
    ]
    assert items_service.list_items(conn, sku="WIDGET-1", active=False) == []
    assert [i.sku for i in items_service.list_items(conn, sku="GADGET-1", active=False)] == [
        "GADGET-1"
    ]


def test_count_items_with_sku_filter(conn):
    for sku in ["WIDGET-1", "WIDGET-2"]:
        _create(conn, sku=sku, name=sku)
    assert items_service.count_items(conn, sku="WIDGET-1") == 1
    assert items_service.count_items(conn, sku="WIDGET") == 0
    items_service.update_item(conn, 1, ItemUpdate(active=False))
    assert items_service.count_items(conn, sku="WIDGET-1", active=True) == 0
    assert items_service.count_items(conn, sku="WIDGET-1", active=False) == 1


def test_count_items_with_active_filter(conn):
    for sku in ["A", "B", "C"]:
        _create(conn, sku=sku, name=sku)
    assert items_service.count_items(conn) == 3
    items_service.update_item(conn, 1, ItemUpdate(active=False))
    assert items_service.count_items(conn, active=True) == 2
    assert items_service.count_items(conn, active=False) == 1


def test_get_item_by_sku(conn):
    created = _create(conn)
    assert items_service.get_item_by_sku(conn, created.sku) == created
    assert items_service.get_item_by_sku(conn, "NOPE-1") is None


def test_update_item_reorder_point(conn):
    created = _create(conn)
    updated = items_service.update_item(conn, created.id, ItemUpdate(reorder_point=12))
    assert updated is not None
    assert updated.reorder_point == 12
    fetched = items_service.get_item(conn, created.id)
    assert fetched is not None
    assert fetched.reorder_point == 12
