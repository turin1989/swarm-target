"""Typed service exceptions and their HTTP mapping."""

import pytest

from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)

# --- exception hierarchy -------------------------------------------------------


def test_subclasses_derive_from_inventory_error():
    assert issubclass(NotFoundError, InventoryError)
    assert issubclass(ConflictError, InventoryError)
    assert issubclass(ValidationError, InventoryError)
    assert issubclass(InventoryError, Exception)


@pytest.mark.parametrize(
    "exc_cls,expected_status",
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (ValidationError, 400),
    ],
)
def test_exceptions_carry_status_code(exc_cls, expected_status):
    exc = exc_cls("boom")
    assert exc.status_code == expected_status
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


# --- service layer raises typed errors -----------------------------------------


def _db(client):
    import sqlite3

    conn = sqlite3.connect(client.app.state.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_apply_movement_missing_item_raises_not_found(client):
    from inventory.models import MovementCreate

    conn = _db(client)
    try:
        with pytest.raises(NotFoundError):
            stock.apply_movement(
                conn, MovementCreate(item_id=999, kind="receive", qty=1, to_location_id=1)
            )
    finally:
        conn.close()


def test_apply_movement_missing_location_field_raises_validation(client, item):
    from inventory.models import MovementCreate

    conn = _db(client)
    try:
        with pytest.raises(ValidationError):
            stock.apply_movement(conn, MovementCreate(item_id=item["id"], kind="receive", qty=1))
    finally:
        conn.close()


def test_apply_movement_unknown_location_raises_not_found(client, item):
    from inventory.models import MovementCreate

    conn = _db(client)
    try:
        with pytest.raises(NotFoundError):
            stock.apply_movement(
                conn,
                MovementCreate(item_id=item["id"], kind="receive", qty=1, to_location_id=123),
            )
    finally:
        conn.close()


def test_get_movement_missing_raises_not_found(client):
    conn = _db(client)
    try:
        with pytest.raises(NotFoundError):
            stock.get_movement(conn, 999)
    finally:
        conn.close()


# --- API maps InventoryError via a single handler -------------------------------


def test_validation_error_maps_to_400(client, item):
    r = client.post("/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1})
    assert r.status_code == 400
    assert "required" in r.json()["detail"]


def test_not_found_error_maps_to_404(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 42},
    )
    assert r.status_code == 404
    assert "location 42 not found" in r.json()["detail"]


def test_inventory_error_handler_registered_once(client):
    from inventory.api import inventory_error_handler

    assert client.app.exception_handlers[InventoryError] is inventory_error_handler


def test_no_per_route_try_except_for_inventory_errors():
    import inspect

    from inventory import api

    source = inspect.getsource(api.create_movement)
    assert "except" not in source
