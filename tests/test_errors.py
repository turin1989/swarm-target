"""Typed service-layer exceptions and their HTTP mapping."""

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
    "exc_class,status_code",
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (ValidationError, 400),
    ],
)
def test_status_codes(exc_class, status_code):
    exc = exc_class("boom")
    assert exc.status_code == status_code
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


def test_api_maps_not_found_error_to_404(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 999},
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_api_maps_validation_error_to_400(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1},
    )
    assert r.status_code == 400
    assert "required" in r.json()["detail"]
