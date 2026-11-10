"""Tests for the typed service exceptions in inventory.services.errors (T051)."""

import inspect

import pytest

from inventory.db import connect, init_db
from inventory.models import MovementCreate
from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)

# --- the exception hierarchy ---------------------------------------------------


def test_inventory_error_is_exception_base():
    assert issubclass(InventoryError, Exception)
    for subclass in (NotFoundError, ConflictError, ValidationError):
        assert issubclass(subclass, InventoryError)


@pytest.mark.parametrize(
    ("exc_class", "expected_status"),
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (ValidationError, 400),
    ],
)
def test_exceptions_carry_status_code(exc_class, expected_status):
    exc = exc_class("boom")
    assert exc.status_code == expected_status
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


# --- stock.py raises the typed exceptions --------------------------------------


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "errors-test.db")
    init_db(path)
    conn = connect(path)
    conn.execute(
        "INSERT INTO items (sku, name, unit_price) VALUES ('ERR-1', 'Err Widget', 1.0)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-E', 'Warehouse E')")
    yield conn
    conn.close()


def _item_id(conn) -> int:
    return conn.execute("SELECT id FROM items").fetchone()["id"]


def _loc_id(conn) -> int:
    return conn.execute("SELECT id FROM locations").fetchone()["id"]


def test_apply_movement_unknown_item_raises_not_found(conn):
    with pytest.raises(NotFoundError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(item_id=999, kind="receive", quantity=1, to_location_id=_loc_id(conn)),
        )
    assert exc_info.value.status_code == 404


def test_apply_movement_unknown_location_raises_not_found(conn):
    with pytest.raises(NotFoundError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(item_id=_item_id(conn), kind="receive", quantity=1, to_location_id=999),
        )
    assert exc_info.value.status_code == 404


def test_apply_movement_missing_location_raises_validation_error(conn):
    with pytest.raises(ValidationError) as exc_info:
        stock.apply_movement(
            conn, MovementCreate(item_id=_item_id(conn), kind="receive", quantity=1)
        )
    assert exc_info.value.status_code == 400


def test_apply_movement_insufficient_stock_raises_conflict(conn):
    with pytest.raises(ConflictError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(
                item_id=_item_id(conn), kind="ship", quantity=5, from_location_id=_loc_id(conn)
            ),
        )
    assert exc_info.value.status_code == 409


def test_apply_movement_inactive_item_raises_conflict(conn):
    """T041 + T051: inactive items are rejected with the typed ConflictError."""
    item_id = _item_id(conn)
    conn.execute("UPDATE items SET active = 0 WHERE id = ?", (item_id,))
    with pytest.raises(ConflictError) as exc_info:
        stock.apply_movement(
            conn,
            MovementCreate(item_id=item_id, kind="receive", quantity=1, to_location_id=_loc_id(conn)),
        )
    assert exc_info.value.status_code == 409
    assert "inactive" in str(exc_info.value)
    # No movement record was created and no stock was adjusted.
    assert conn.execute("SELECT COUNT(*) AS n FROM movements").fetchone()["n"] == 0
    assert stock.total_stock(conn, item_id) == 0


def test_get_movement_unknown_id_raises_not_found(conn):
    with pytest.raises(NotFoundError):
        stock.get_movement(conn, 12345)


def test_service_errors_are_catchable_as_inventory_error(conn):
    with pytest.raises(InventoryError):
        stock.get_movement(conn, 12345)


# --- the API maps InventoryError centrally --------------------------------------


def test_api_has_single_mapping_helper():
    from fastapi import HTTPException

    from inventory import api

    mapped = api.inventory_error_to_http(NotFoundError("movement 7 not found"))
    assert isinstance(mapped, HTTPException)
    assert mapped.status_code == 404
    assert mapped.detail == "movement 7 not found"

    mapped = api.inventory_error_to_http(ConflictError("nope"))
    assert mapped.status_code == 409

    mapped = api.inventory_error_to_http(ValidationError("bad"))
    assert mapped.status_code == 400


def test_api_routes_do_not_catch_inventory_errors_per_route():
    """No route wraps service calls in try/except for domain errors."""
    from inventory import api

    source = inspect.getsource(api)
    assert "except stock." not in source
    assert "except InventoryError" not in source
    assert "StockError" not in source


# --- end-to-end: HTTP responses keep the documented statuses and shape -----------


def _assert_error_shape(body: dict, expected_code: str) -> None:
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == expected_code
    assert body["error"]["message"]


def test_movement_not_found_maps_to_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_movement_missing_location_maps_to_400(client, item):
    r = client.post(
        "/movements", json={"item_id": item["id"], "kind": "receive", "quantity": 1}
    )
    assert r.status_code == 400
    _assert_error_shape(r.json(), "bad_request")


def test_movement_insufficient_stock_maps_to_409(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "ship",
            "quantity": 3,
            "from_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 409
    _assert_error_shape(r.json(), "conflict")


def test_reverse_adjust_maps_to_400(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "adjust",
            "quantity": 4,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 201, r.text
    rev = client.post(f"/movements/{r.json()['id']}/reverse")
    assert rev.status_code == 400
    _assert_error_shape(rev.json(), "bad_request")
