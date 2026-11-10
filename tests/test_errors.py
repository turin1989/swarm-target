"""Tests for the typed service-layer exceptions and their HTTP mapping."""

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
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_exceptions_carry_status_code(exc_cls, expected_status):
    exc = exc_cls("boom")
    assert exc.status_code == expected_status
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


# --- service layer raises typed exceptions ------------------------------------


def _movement(**overrides):
    from inventory.models import MovementCreate

    payload = {"item_id": 1, "kind": "receive", "qty": 1, "to_location_id": 1}
    payload.update(overrides)
    return MovementCreate(**payload)


def _conn(tmp_path):
    from inventory.db import connect, init_db

    path = str(tmp_path / "svc.db")
    init_db(path)
    return connect(path)


def test_apply_movement_unknown_item_raises_not_found(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(NotFoundError):
        stock.apply_movement(conn, _movement(item_id=999))


def test_apply_movement_unknown_location_raises_not_found(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO items (sku, name) VALUES ('S1', 'n')")
    with pytest.raises(NotFoundError):
        stock.apply_movement(conn, _movement(to_location_id=999))


def test_apply_movement_missing_location_raises_validation_error(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO items (sku, name) VALUES ('S1', 'n')")
    with pytest.raises(ValidationError):
        stock.apply_movement(conn, _movement(to_location_id=None))


def test_adjust_with_from_location_raises_validation_error(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO items (sku, name) VALUES ('S1', 'n')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('L1', 'loc')")
    with pytest.raises(ValidationError):
        stock.apply_movement(
            conn, _movement(kind="adjust", to_location_id=1, from_location_id=1)
        )


def test_get_movement_unknown_id_raises_not_found(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(NotFoundError):
        stock.get_movement(conn, 12345)


# --- HTTP mapping is handled centrally -----------------------------------------


def test_inventory_error_maps_to_http_status(client, item, loc_a):
    # NotFoundError -> 404 with a detail body, via the app-level handler
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 9999},
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_validation_error_maps_to_400(client, item, loc_a):
    # from_location_id must be null for adjust -> ValidationError -> 400
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "adjust",
            "qty": 1,
            "to_location_id": loc_a["id"],
            "from_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 400
    assert "from_location_id" in r.json()["detail"]


def test_missing_required_location_maps_to_400(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1},
    )
    assert r.status_code == 400
    assert "to_location_id" in r.json()["detail"]


def test_no_per_route_stock_error_handling_in_api():
    """api.py must not map errors per-route; one central handler does it."""
    import inspect

    import inventory.api as api

    source = inspect.getsource(api)
    assert "StockError" not in source
    # the movements route itself contains no try/except
    create_movement_src = inspect.getsource(api.create_movement)
    assert "try:" not in create_movement_src
    assert "except" not in create_movement_src


def test_handler_registered_on_app(client):
    from inventory.services.errors import InventoryError

    app = client.app
    assert InventoryError in app.exception_handlers
