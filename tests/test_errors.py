"""Typed service-layer exceptions (inventory.services.errors) and their HTTP mapping."""

import inspect

import pytest

from inventory import api
from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)


# --- the errors module itself --------------------------------------------------


def test_inventory_error_is_exception_base():
    assert issubclass(InventoryError, Exception)
    for subclass in (NotFoundError, ConflictError, ValidationError):
        assert issubclass(subclass, InventoryError)


@pytest.mark.parametrize(
    "exc_class,expected_status",
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_subclasses_carry_status_code(exc_class, expected_status):
    exc = exc_class("boom")
    assert exc.status_code == expected_status
    assert str(exc) == "boom"


def test_errors_can_be_caught_as_inventory_error():
    with pytest.raises(InventoryError) as excinfo:
        raise NotFoundError("gone")
    assert excinfo.value.status_code == 404


# --- StockError is gone ---------------------------------------------------------


def test_stock_error_removed():
    assert not hasattr(stock, "StockError")


# --- the service layer raises typed exceptions ----------------------------------


@pytest.fixture()
def conn():
    import sqlite3

    from inventory.db import SCHEMA

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    yield connection
    connection.close()


def test_apply_movement_raises_typed_exceptions(conn):
    from inventory.models import MovementCreate

    conn.execute("INSERT INTO items (sku, name) VALUES ('SKU-1', 'Thing')")
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'A')")

    with pytest.raises(NotFoundError):
        stock.apply_movement(
            conn, MovementCreate(item_id=999, kind="receive", qty=1, to_location_id=1)
        )
    with pytest.raises(ValidationError):
        stock.apply_movement(conn, MovementCreate(item_id=1, kind="receive", qty=1))
    with pytest.raises(NotFoundError):
        stock.apply_movement(
            conn, MovementCreate(item_id=1, kind="receive", qty=1, to_location_id=42)
        )
    with pytest.raises(ConflictError):
        stock.apply_movement(
            conn, MovementCreate(item_id=1, kind="ship", qty=5, from_location_id=1)
        )
    with pytest.raises(NotFoundError):
        stock.get_movement(conn, 12345)


def test_api_maps_not_found(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 999},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert "location 999 not found" in r.json()["error"]["message"]


def test_api_maps_conflict(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 1, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    assert "insufficient" in r.json()["error"]["message"]


def test_api_maps_validation(client, item, loc_a):
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
    assert "same location" in r.json()["error"]["message"]


# --- mapping happens in one place, not per-route --------------------------------


def test_no_per_route_inventory_error_handling_in_api():
    source = inspect.getsource(api)
    # no route catches service-layer errors itself
    assert "StockError" not in source
    assert "except InventoryError" not in source
    assert "except errors." not in source
    assert "except stock." not in source


def test_create_movement_has_no_exception_handling():
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(api.create_movement)))
    assert not any(isinstance(node, ast.Try) for node in ast.walk(tree))


def test_inventory_error_handler_registered_once():
    from inventory.main import create_app

    app = create_app(db_path=":memory:")
    handlers = [exc for exc in app.exception_handlers if exc is InventoryError]
    assert handlers == [InventoryError]
