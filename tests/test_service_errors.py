"""T051: typed service exceptions in inventory.services.errors."""

import pytest


# --- the exception hierarchy -----------------------------------------------------


def test_errors_module_defines_typed_hierarchy():
    from inventory.services.errors import (
        ConflictError,
        InventoryError,
        NotFoundError,
        ValidationError,
    )

    assert issubclass(InventoryError, Exception)
    for cls, status in ((NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)):
        assert issubclass(cls, InventoryError)
        exc = cls("boom")
        assert exc.status_code == status
        assert str(exc) == "boom"


def test_status_code_can_be_overridden_per_instance():
    from inventory.services.errors import InventoryError, ValidationError

    exc = ValidationError("qty must be a positive integer", status_code=422)
    assert exc.status_code == 422
    assert InventoryError("generic").status_code == 400


def test_stock_error_is_removed():
    from inventory.services import stock

    assert not hasattr(stock, "StockError")


# --- stock.py raises the typed exceptions ----------------------------------------


@pytest.fixture()
def conn():
    from inventory.db import SCHEMA, connect

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S2', 'Gadget', '', 1.0, 0, 0)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    yield conn
    conn.close()


def test_missing_item_raises_not_found(conn):
    from inventory.models import MovementCreate
    from inventory.services.errors import NotFoundError
    from inventory.services.stock import apply_movement

    m = MovementCreate(item_id=999, kind="receive", qty=1, to_location_id=1)
    with pytest.raises(NotFoundError) as exc:
        apply_movement(conn, m)
    assert exc.value.status_code == 404


def test_missing_location_raises_not_found(conn):
    from inventory.services.errors import NotFoundError
    from inventory.services.stock import get_location_levels

    with pytest.raises(NotFoundError) as exc:
        get_location_levels(conn, 999)
    assert exc.value.status_code == 404


def test_missing_movement_raises_not_found(conn):
    from inventory.services.errors import NotFoundError
    from inventory.services.stock import get_movement

    with pytest.raises(NotFoundError) as exc:
        get_movement(conn, 12345)
    assert exc.value.status_code == 404


def test_inactive_item_raises_conflict(conn):
    from inventory.models import MovementCreate
    from inventory.services.errors import ConflictError
    from inventory.services.stock import apply_movement

    m = MovementCreate(item_id=2, kind="receive", qty=1, to_location_id=1)
    with pytest.raises(ConflictError) as exc:
        apply_movement(conn, m)
    assert exc.value.status_code == 409


def test_insufficient_stock_raises_conflict(conn):
    from inventory.models import MovementCreate
    from inventory.services.errors import ConflictError
    from inventory.services.stock import apply_movement

    m = MovementCreate(item_id=1, kind="ship", qty=5, from_location_id=1)
    with pytest.raises(ConflictError) as exc:
        apply_movement(conn, m)
    assert exc.value.status_code == 409


def test_same_location_transfer_raises_validation_error(conn):
    from inventory.models import MovementCreate
    from inventory.services.errors import ValidationError
    from inventory.services.stock import apply_movement

    m = MovementCreate(
        item_id=1, kind="transfer", qty=1, from_location_id=1, to_location_id=1
    )
    with pytest.raises(ValidationError) as exc:
        apply_movement(conn, m)
    assert exc.value.status_code == 400


def test_missing_required_location_raises_validation_error(conn):
    from inventory.models import MovementCreate
    from inventory.services.errors import ValidationError
    from inventory.services.stock import apply_movement

    m = MovementCreate.model_construct(
        item_id=1, kind="receive", qty=1, from_location_id=None, to_location_id=None, note=""
    )
    with pytest.raises(ValidationError) as exc:
        apply_movement(conn, m)
    assert exc.value.status_code == 400


# --- api maps InventoryError centrally --------------------------------------------


def test_api_has_no_per_route_stock_error_handling():
    """The router maps InventoryError in one helper, not per-route try/except."""
    import inspect

    import inventory.api as api
    from inventory.services.errors import InventoryError

    source = inspect.getsource(api)
    assert "StockError" not in source
    assert source.count("except InventoryError") == 0
    assert source.count("except stock.") == 0
    # The single mapping helper exists and produces an HTTPException.
    from fastapi import HTTPException

    http_exc = api.inventory_error_to_http(InventoryError("nope", status_code=404))
    assert isinstance(http_exc, HTTPException)
    assert http_exc.status_code == 404
    assert http_exc.detail == "nope"


def test_inventory_error_handled_at_app_level(client):
    """Routes raise InventoryError; a single app-level handler maps it to HTTP."""
    # NotFoundError via GET /locations/{id}/stock
    r = client.get("/locations/999/stock")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

    # NotFoundError via GET /movements/{id}
    r = client.get("/movements/999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_movement_errors_map_to_expected_statuses(client, item, loc_a):
    # ConflictError -> 409
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 1, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"

    # ValidationError -> 400
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "qty": 1,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"

    # NotFoundError -> 404
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 999},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
