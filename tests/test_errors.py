"""Typed service exceptions and their HTTP mapping."""

import pytest

from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)


def test_exception_hierarchy():
    assert issubclass(NotFoundError, InventoryError)
    assert issubclass(ConflictError, InventoryError)
    assert issubclass(ValidationError, InventoryError)
    assert issubclass(InventoryError, Exception)


@pytest.mark.parametrize(
    "exc_class,expected_status",
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (ValidationError, 400),
    ],
)
def test_status_codes(exc_class, expected_status):
    exc = exc_class("boom")
    assert exc.status_code == expected_status
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


def test_stock_raises_typed_not_found(client):
    """Service layer raises NotFoundError and the app maps it to a 404."""
    r = client.post(
        "/movements",
        json={"item_id": 999, "kind": "receive", "qty": 1, "to_location_id": 1},
    )
    assert r.status_code == 404
    assert "item 999 not found" in r.json()["detail"]


def test_stock_raises_typed_validation_error(client, item):
    """Missing location maps to a 400 via the InventoryError handler."""
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1},
    )
    assert r.status_code == 400
    assert "required" in r.json()["detail"]


def test_handler_registered_once_on_app(client):
    """InventoryError is mapped by a single app-level exception handler."""
    from inventory.api import inventory_error_handler

    app = client.app
    assert app.exception_handlers.get(InventoryError) is inventory_error_handler
