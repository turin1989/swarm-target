"""Tests for T051: typed service-layer exceptions in inventory.services.errors."""

import inspect
import sqlite3

import pytest

from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)
from inventory.models import MovementCreate


# --- the errors module itself --------------------------------------------------


def test_exception_hierarchy():
    assert issubclass(InventoryError, Exception)
    for subclass in (NotFoundError, ConflictError, ValidationError):
        assert issubclass(subclass, InventoryError)


@pytest.mark.parametrize(
    ("exc_class", "status_code"),
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_subclasses_carry_status_code(exc_class, status_code):
    assert exc_class.status_code == status_code
    assert exc_class("boom").status_code == status_code


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


# --- services/stock.py raises the typed exceptions -----------------------------


@pytest.fixture()
def conn(client):
    c = sqlite3.connect(client.app.state.db_path)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


def test_apply_movement_missing_item_raises_not_found(conn):
    with pytest.raises(NotFoundError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(item_id=999, kind="receive", qty=1, to_location_id=1),
        )
    assert exc_info.value.status_code == 404


def test_apply_movement_missing_location_raises_not_found(conn, item):
    with pytest.raises(NotFoundError):
        stock.apply_movement(
            conn,
            MovementCreate(item_id=item["id"], kind="receive", qty=1, to_location_id=999),
        )


def test_insufficient_stock_raises_conflict(conn, item, loc_a):
    with pytest.raises(ConflictError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(
                item_id=item["id"], kind="ship", qty=5, from_location_id=loc_a["id"]
            ),
        )
    assert exc_info.value.status_code == 409


def test_same_location_transfer_raises_validation_error(conn, item, loc_a):
    with pytest.raises(ValidationError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(
                item_id=item["id"],
                kind="transfer",
                qty=1,
                from_location_id=loc_a["id"],
                to_location_id=loc_a["id"],
            ),
        )
    assert exc_info.value.status_code == 400


def test_get_movement_missing_raises_not_found(conn):
    with pytest.raises(NotFoundError):
        stock.get_movement(conn, 12345)


# --- api maps InventoryError centrally, not per-route --------------------------


def test_api_has_no_per_route_stock_error_handling():
    from inventory import api

    source = inspect.getsource(api)
    assert "StockError" not in source
    # the only mapping lives in the helper, not in route bodies
    assert "inventory_error_to_http" in source


def test_inventory_error_to_http_maps_status_and_message():
    from fastapi import HTTPException

    from inventory.api import inventory_error_to_http

    exc = inventory_error_to_http(ConflictError("nope"))
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 409
    assert exc.detail == "nope"


@pytest.mark.parametrize(
    ("exc", "status_code", "code"),
    [
        (NotFoundError("thing not found"), 404, "not_found"),
        (ConflictError("thing conflicts"), 409, "conflict"),
        (ValidationError("thing invalid"), 400, "bad_request"),
    ],
)
def test_inventory_error_handled_centrally(client, monkeypatch, exc, status_code, code):
    """Any InventoryError escaping a route is mapped in one place by the app."""

    def boom(conn, movement_id):
        raise exc

    monkeypatch.setattr("inventory.api.stock.get_movement", boom)
    r = client.get("/movements/1")
    assert r.status_code == status_code
    assert r.json() == {"error": {"code": code, "message": str(exc)}}


# --- end-to-end status codes through the HTTP layer -----------------------------


def test_movement_not_found_maps_to_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_insufficient_stock_maps_to_409(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 3, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_same_location_transfer_maps_to_400(client, item, loc_a):
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
    assert r.json()["error"]["code"] == "bad_request"
