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
    "exc_type,code",
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_subclasses_carry_status_code(exc_type, code):
    exc = exc_type("boom")
    assert exc.status_code == code
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


def test_handler_maps_validation_error_to_400(client, item):
    r = client.post("/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1})
    assert r.status_code == 400
    assert "to_location_id is required" in r.json()["detail"]


def test_handler_maps_not_found_error_to_404(client, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": 999, "kind": "receive", "qty": 1, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "item 999 not found"
