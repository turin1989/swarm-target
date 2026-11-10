"""Item persistence helpers in inventory.services.items (T030)."""

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
    try:
        yield c
    finally:
        c.close()


# --- get_item ------------------------------------------------------------------


def test_get_item_returns_none_for_missing(conn):
    assert items_service.get_item(conn, 999) is None


def test_get_item_returns_item_model(conn):
    created = items_service.create_item(
        conn, ItemCreate(sku="SVC-1", name="Service", unit_price=2.5)
    )
    fetched = items_service.get_item(conn, created.id)
    assert isinstance(fetched, Item)
    assert fetched == created
    assert fetched.active is True


# --- create_item ----------------------------------------------------------------


def test_create_item_persists_all_fields(conn):
    item = items_service.create_item(
        conn,
        ItemCreate(
            sku="SVC-2",
            name="Full",
            description="desc",
            unit_price=1.25,
            reorder_level=4,
            barcode="BC-42",
        ),
    )
    assert item.id > 0
    assert item.sku == "SVC-2"
    assert item.name == "Full"
    assert item.description == "desc"
    assert item.unit_price == 1.25
    assert item.reorder_level == 4
    assert item.barcode == "BC-42"
    assert item.created_at


def test_create_item_duplicate_sku_raises_conflict(conn):
    items_service.create_item(conn, ItemCreate(sku="DUP", name="One"))
    with pytest.raises(ConflictError) as exc:
        items_service.create_item(conn, ItemCreate(sku="DUP", name="Two"))
    assert "DUP" in str(exc.value)


def test_create_item_duplicate_barcode_raises_conflict(conn):
    items_service.create_item(conn, ItemCreate(sku="B-1", name="One", barcode="X-1"))
    with pytest.raises(ConflictError) as exc:
        items_service.create_item(conn, ItemCreate(sku="B-2", name="Two", barcode="X-1"))
    assert "X-1" in str(exc.value)


# --- update_item ----------------------------------------------------------------


def test_update_item_missing_returns_none(conn):
    assert items_service.update_item(conn, 999, ItemUpdate(name="x")) is None


def test_update_item_applies_set_fields_only(conn):
    created = items_service.create_item(
        conn, ItemCreate(sku="UPD-1", name="Before", unit_price=1.0, reorder_level=5)
    )
    updated = items_service.update_item(
        conn, created.id, ItemUpdate(name="After", active=False)
    )
    assert updated is not None
    assert updated.name == "After"
    assert updated.active is False
    # untouched fields preserved
    assert updated.unit_price == 1.0
    assert updated.reorder_level == 5
    assert updated.created_at == created.created_at
    # persisted
    assert items_service.get_item(conn, created.id) == updated


def test_update_item_with_no_fields_is_a_noop(conn):
    created = items_service.create_item(conn, ItemCreate(sku="UPD-2", name="Same"))
    assert items_service.update_item(conn, created.id, ItemUpdate()) == created


# --- delete_item ----------------------------------------------------------------


def test_delete_item_returns_true_and_removes_row(conn):
    created = items_service.create_item(conn, ItemCreate(sku="DEL-1", name="Doomed"))
    assert items_service.delete_item(conn, created.id) is True
    assert items_service.get_item(conn, created.id) is None


def test_delete_item_missing_returns_false(conn):
    assert items_service.delete_item(conn, 999) is False


# --- api wiring -----------------------------------------------------------------


def test_api_routes_still_work_via_service(client):
    r = client.post("/items", json={"sku": "WIRE-1", "name": "Wired"})
    assert r.status_code == 201
    item_id = r.json()["id"]
    assert client.get(f"/items/{item_id}").status_code == 200
    assert client.put(f"/items/{item_id}", json={"name": "Rewired"}).json()["name"] == "Rewired"
    assert client.delete(f"/items/{item_id}").status_code == 204
    assert client.get(f"/items/{item_id}").status_code == 404


def test_api_has_no_inline_item_sql(client):
    """api.py must delegate item persistence to the service module."""
    import inspect

    from inventory import api

    source = inspect.getsource(api)
    assert "INSERT INTO items" not in source
    assert "UPDATE items" not in source
    assert "DELETE FROM items" not in source
    assert "SELECT * FROM items WHERE id" not in source
