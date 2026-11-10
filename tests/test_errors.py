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
    assert issubclass(InventoryError, Exception)
    for subclass in (NotFoundError, ConflictError, ValidationError):
        assert issubclass(subclass, InventoryError)


@pytest.mark.parametrize(
    "exc_class,expected_status",
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (ValidationError, 400),
    ],
)
def test_subclasses_carry_status_code(exc_class, expected_status):
    exc = exc_class("boom")
    assert exc.status_code == expected_status
    assert str(exc) == "boom"
    assert isinstance(exc, InventoryError)


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


def test_service_raises_validation_error(client, item):
    """Missing location -> ValidationError -> 400 via the app-level handler."""
    r = client.post(
        "/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1}
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]


def test_service_raises_not_found_error(client, item):
    """Unknown location -> NotFoundError -> 404 via the app-level handler."""
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 999},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "not found" in body["error"]["message"]


def test_not_found_error_response_includes_request_id(client, item):
    """Errors mapped by the handler still pass through the middleware stack."""
    r = client.post(
        "/movements",
        json={"item_id": 999, "kind": "receive", "qty": 1, "to_location_id": 1},
        headers={"x-request-id": "err-req-1"},
    )
    assert r.status_code == 404
    assert r.headers["x-request-id"] == "err-req-1"


def test_no_per_route_stock_error_handling():
    """api.py must not try/except service errors per route."""
    import inspect

    import inventory.api as api

    source = inspect.getsource(api.create_movement)
    assert "try" not in source
    assert "except" not in source
    assert "StockError" not in inspect.getsource(api)
