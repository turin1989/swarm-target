"""Unit tests for inventory.services.items persistence helpers."""

import sqlite3

import pytest

from inventory.db import connect, init_db
from inventory.models import Item, ItemCreate, ItemUpdate
from inventory.services import items as items_service


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "service-test.db")
    init_db(path)
    conn = connect(path)
    yield conn
    conn.close()


def _make(conn, **overrides) -> Item:
    payload = {
        "sku": "SVC-1",
        "name": "Service Widget",
        "description": "a widget",
        "unit_price": 3.5,
        "reorder_level": 2,
    }
    payload.update(overrides)
    return items_service.create_item(conn, ItemCreate(**payload))


def test_create_item_returns_persisted_item(conn):
    item = _make(conn)
    assert isinstance(item, Item)
    assert item.id > 0
    assert item.sku == "SVC-1"
    assert item.name == "Service Widget"
    assert item.unit_price == 3.5
    assert item.reorder_level == 2
    assert item.active is True


def test_create_item_duplicate_sku_raises_integrity_error(conn):
    _make(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _make(conn)


def test_get_item_returns_item(conn):
    created = _make(conn)
    fetched = items_service.get_item(conn, created.id)
    assert fetched == created


def test_get_item_missing_returns_none(conn):
    assert items_service.get_item(conn, 9999) is None


def test_update_item_applies_changes(conn):
    created = _make(conn)
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="Renamed", unit_price=9.0, active=False)
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.unit_price == 9.0
    assert updated.active is False
    # unchanged fields are preserved
    assert updated.sku == created.sku
    assert updated.description == created.description


def test_update_item_applies_reorder_level(conn):
    created = _make(conn)
    updated = items_service.update_item(conn, created.id, ItemUpdate(reorder_level=9))
    assert updated is not None
    assert updated.reorder_level == 9
    # unchanged fields are preserved
    assert updated.name == created.name
    assert updated.unit_price == created.unit_price


def test_update_item_missing_returns_none(conn):
    assert items_service.update_item(conn, 9999, ItemUpdate(name="x")) is None


def test_update_item_with_no_fields_is_noop(conn):
    created = _make(conn)
    updated = items_service.update_item(conn, created.id, ItemUpdate())
    assert updated == created


def test_delete_item_returns_true_and_removes_row(conn):
    created = _make(conn)
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None


def test_delete_item_missing_returns_false(conn):
    assert items_service.delete_item(conn, 9999) is False


def test_api_module_uses_service_instead_of_inline_sql():
    """api.py must not contain inline SQL touching the items table."""
    import inspect

    from inventory import api

    source = inspect.getsource(api)
    assert "INSERT INTO items" not in source
    assert "UPDATE items" not in source
    assert "DELETE FROM items" not in source


# --- created_at (T020) ---------------------------------------------------------


def test_create_item_sets_created_at_in_service_layer(conn):
    """The service stamps created_at explicitly so legacy-migrated DBs
    (whose ALTER TABLE column has no default) still get a value on insert."""
    import re
    from datetime import datetime, timezone

    before = datetime.now(timezone.utc).replace(microsecond=0)
    item = _make(conn)
    after = datetime.now(timezone.utc)
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", item.created_at)
    parsed = datetime.strptime(item.created_at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    assert before <= parsed <= after
    row = conn.execute(
        "SELECT created_at FROM items WHERE id = ?", (item.id,)
    ).fetchone()
    assert row["created_at"] == item.created_at


def test_service_update_item_does_not_change_created_at(conn):
    item = _make(conn)
    updated = items_service.update_item(
        conn, item.id, ItemUpdate(name="Renamed", created_at="1999-01-01T00:00:00Z")
    )
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.created_at == item.created_at
