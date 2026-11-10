"""Tests for the typed domain exceptions (T051)."""

import inspect

import pytest

from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)


# --- the exception hierarchy ----------------------------------------------------


def test_exception_hierarchy_and_status_codes():
    assert issubclass(InventoryError, Exception)
    assert issubclass(NotFoundError, InventoryError)
    assert issubclass(ConflictError, InventoryError)
    assert issubclass(ValidationError, InventoryError)

    assert NotFoundError("x").status_code == 404
    assert ConflictError("x").status_code == 409
    assert ValidationError("x").status_code == 400


def test_exceptions_carry_message():
    exc = NotFoundError("item 7 not found")
    assert str(exc) == "item 7 not found"
    assert isinstance(exc, InventoryError)


# --- StockError is gone, services raise the typed errors ------------------------


def _service_db():
    from inventory.db import SCHEMA, connect

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    return conn


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


def test_service_raises_not_found_error():
    conn = _service_db()
    with pytest.raises(NotFoundError) as exc:
        stock.get_location_levels(conn, 999)
    assert exc.value.status_code == 404

    from inventory.models import MovementCreate

    m = MovementCreate(item_id=42, kind="receive", qty=1, to_location_id=1)
    with pytest.raises(NotFoundError):
        stock.apply_movement(conn, m)


def test_service_raises_conflict_error_for_insufficient_stock():
    conn = _service_db()
    from inventory.models import MovementCreate

    m = MovementCreate(item_id=1, kind="ship", qty=1, from_location_id=1)
    with pytest.raises(ConflictError) as exc:
        stock.apply_movement(conn, m)
    assert exc.value.status_code == 409


def test_service_raises_validation_error_for_missing_location():
    conn = _service_db()
    from inventory.models import MovementCreate

    m = MovementCreate.model_construct(
        item_id=1, kind="receive", qty=1, from_location_id=None, to_location_id=None, note=""
    )
    with pytest.raises(ValidationError) as exc:
        stock.apply_movement(conn, m)
    assert exc.value.status_code == 400
    assert "required" in str(exc.value)


# --- the API maps InventoryError centrally ---------------------------------------


def test_app_registers_single_inventory_error_handler(client):
    app = client.app
    assert InventoryError in app.exception_handlers
    # Subclasses are matched through the base class; no per-subclass handlers.
    assert NotFoundError not in app.exception_handlers
    assert ConflictError not in app.exception_handlers
    assert ValidationError not in app.exception_handlers


def test_api_has_no_per_route_stock_error_handling():
    from inventory import api

    source = inspect.getsource(api)
    assert "StockError" not in source
    assert "except InventoryError" not in source


def test_handler_maps_status_and_detail_shape(client, item, loc_a):
    # 404 via the handler
    r = client.get("/locations/999/stock")
    assert r.status_code == 404
    assert r.json() == {"detail": "location 999 not found"}

    # 409 via the handler
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 1, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 409
    assert "insufficient" in r.json()["detail"]

    # 400 via the handler
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
    assert "same location" in r.json()["detail"]


def test_handled_error_rolls_back_transaction(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    before = client.get(f"/items/{item['id']}/stock").json()

    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 99, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 409
    assert client.get(f"/items/{item['id']}/stock").json() == before
    assert len(client.get("/movements").json()) == 1
