"""Typed service-layer exceptions and their HTTP mapping."""

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
    for cls in (NotFoundError, ConflictError, ValidationError):
        assert issubclass(cls, InventoryError)
    assert issubclass(InventoryError, Exception)


@pytest.mark.parametrize(
    "cls,code",
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_status_codes(cls, code):
    exc = cls("boom")
    assert exc.status_code == code
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


# --- services raise typed errors ----------------------------------------------


def _conn(client):
    """Open a raw sqlite connection against the app's database."""
    from inventory.db import connect

    # TestClient keeps the app on .app; state holds the db path.
    return connect(client.app.state.db_path)


def test_apply_movement_missing_item_raises_not_found(client):
    from inventory.models import MovementCreate

    conn = _conn(client)
    try:
        with pytest.raises(NotFoundError):
            stock.apply_movement(
                conn, MovementCreate(item_id=999, kind="receive", qty=1, to_location_id=1)
            )
    finally:
        conn.close()


def test_apply_movement_missing_location_field_raises_validation(client, item):
    from inventory.models import MovementCreate

    conn = _conn(client)
    try:
        with pytest.raises(ValidationError):
            stock.apply_movement(
                conn, MovementCreate(item_id=item["id"], kind="receive", qty=1)
            )
    finally:
        conn.close()


def test_apply_movement_unknown_location_raises_not_found(client, item):
    from inventory.models import MovementCreate

    conn = _conn(client)
    try:
        with pytest.raises(NotFoundError):
            stock.apply_movement(
                conn,
                MovementCreate(item_id=item["id"], kind="receive", qty=1, to_location_id=42),
            )
    finally:
        conn.close()


def test_get_movement_missing_raises_not_found(client):
    conn = _conn(client)
    try:
        with pytest.raises(NotFoundError):
            stock.get_movement(conn, 12345)
    finally:
        conn.close()


# --- the API maps InventoryError centrally -------------------------------------


def test_api_has_no_per_route_stock_error_handling():
    import inspect

    from inventory import api

    source = inspect.getsource(api.create_movement)
    assert "try" not in source
    assert "StockError" not in source


def test_handler_registered_for_inventory_error(client):
    assert InventoryError in client.app.exception_handlers


@pytest.mark.parametrize(
    "payload,status,fragment",
    [
        ({"item_id": 999, "kind": "receive", "qty": 1, "to_location_id": 1}, 404, "item 999"),
        ({"kind": "receive", "qty": 1}, 400, "required"),
    ],
)
def test_inventory_error_maps_to_http_response(client, item, loc_a, payload, status, fragment):
    payload.setdefault("item_id", item["id"])
    r = client.post("/movements", json=payload)
    assert r.status_code == status
    assert fragment in r.json()["detail"]


def test_conflict_error_maps_to_409(client):
    """Any InventoryError subclass raised inside a route becomes an HTTP error."""
    from fastapi.testclient import TestClient

    app = client.app

    @app.get("/_boom_conflict")
    def _boom() -> dict:
        raise ConflictError("duplicate thing")

    with TestClient(app) as c:
        r = c.get("/_boom_conflict")
    assert r.status_code == 409
    assert r.json() == {"detail": "duplicate thing"}
