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
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "item 999 not found" in body["error"]["message"]


def test_stock_raises_typed_validation_error(client, item):
    """Missing location maps to a 400 via the InventoryError handler."""
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]


def test_handler_registered_once_on_app(client):
    """InventoryError is mapped by a single app-level exception handler."""
    from inventory.api import inventory_error_handler

    app = client.app
    assert app.exception_handlers.get(InventoryError) is inventory_error_handler


# --- uniform error response shape ---------------------------------------------


def _assert_error_shape(body: dict, code: str) -> None:
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_404_uniform_shape_from_http_exception(client):
    """HTTPException(404) raised in a route is converted by the app handler."""
    r = client.get("/items/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
    assert "not found" in r.json()["error"]["message"]


def test_404_uniform_shape_for_location(client):
    r = client.get("/locations/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_409_uniform_shape_on_duplicate_sku(client, item):
    r = client.post(
        "/items",
        json={"sku": item["sku"], "name": "Duplicate", "unit_price": 1.0},
    )
    assert r.status_code == 409
    _assert_error_shape(r.json(), "conflict")
    assert item["sku"] in r.json()["error"]["message"]


def test_422_uniform_shape_on_request_validation_error(client):
    """FastAPI request validation errors are converted to the uniform shape."""
    r = client.post("/items", json={"name": "No SKU"})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")
    assert "sku" in r.json()["error"]["message"]


def test_422_uniform_shape_on_query_validation_error(client):
    r = client.get("/items", params={"limit": 0})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


def test_400_uniform_shape_from_service_validation_error(client, item, loc_a):
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
    _assert_error_shape(r.json(), "bad_request")


def test_404_uniform_shape_for_unknown_route(client):
    """Even framework-level 404s use the uniform shape."""
    r = client.get("/nope")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
