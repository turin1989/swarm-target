"""Typed service exceptions, their HTTP mapping, and the uniform error
response shape: {"error": {"code": ..., "message": ...}}."""

import pytest

from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)


def _assert_error_shape(body, code):
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


# --- typed exceptions ---------------------------------------------------------


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
    _assert_error_shape(r.json(), "bad_request")
    assert "to_location_id is required" in r.json()["error"]["message"]


def test_handler_maps_not_found_error_to_404(client, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": 999, "kind": "receive", "qty": 1, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
    assert r.json()["error"]["message"] == "item 999 not found"


# --- uniform error response shape ---------------------------------------------


def test_404_item_not_found_shape(client):
    r = client.get("/items/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_404_location_not_found_shape(client):
    r = client.get("/locations/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_404_unknown_route_shape(client):
    r = client.get("/nope")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_409_duplicate_sku_shape(client, item):
    r = client.post("/items", json={"sku": item["sku"], "name": "Dup"})
    assert r.status_code == 409
    _assert_error_shape(r.json(), "conflict")
    assert item["sku"] in r.json()["error"]["message"]


def test_422_request_validation_shape(client):
    r = client.post("/items", json={"name": "missing sku"})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")
    assert "sku" in r.json()["error"]["message"]


def test_422_query_validation_shape(client):
    r = client.get("/search")
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


def test_400_bad_request_shape(client, item):
    r = client.post("/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1})
    assert r.status_code == 400
    _assert_error_shape(r.json(), "bad_request")


def test_404_movement_unknown_item_shape(client, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": 123, "kind": "receive", "qty": 1, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
