"""T051: StockError split into typed exceptions in inventory.services.errors."""

import sqlite3

import pytest

from inventory import api
from inventory.db import init_db
from inventory.models import MovementCreate
from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)

# --- the exception hierarchy ---------------------------------------------------


def test_inventory_error_is_exception():
    assert issubclass(InventoryError, Exception)


@pytest.mark.parametrize(
    "exc_type,status_code",
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_subclasses_carry_status_code(exc_type, status_code):
    assert issubclass(exc_type, InventoryError)
    exc = exc_type("boom")
    assert exc.status_code == status_code
    assert str(exc) == "boom"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


# --- the service layer raises the typed exceptions -----------------------------


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO items (id, sku, name) VALUES (1, 'SKU-1', 'Widget')"
    )
    conn.execute("INSERT INTO locations (id, code, name) VALUES (1, 'A', 'A')")
    conn.execute("INSERT INTO locations (id, code, name) VALUES (2, 'B', 'B')")
    yield conn
    conn.close()


def test_missing_item_raises_not_found(conn):
    m = MovementCreate(item_id=999, kind="receive", quantity=1, to_location_id=1)
    with pytest.raises(NotFoundError):
        stock.apply_movement(conn, m)


def test_missing_location_raises_not_found(conn):
    m = MovementCreate(item_id=1, kind="receive", quantity=1, to_location_id=999)
    with pytest.raises(NotFoundError):
        stock.apply_movement(conn, m)


def test_missing_movement_raises_not_found(conn):
    with pytest.raises(NotFoundError):
        stock.get_movement(conn, 12345)


def test_insufficient_stock_raises_conflict(conn):
    m = MovementCreate(item_id=1, kind="ship", quantity=5, from_location_id=1)
    with pytest.raises(ConflictError):
        stock.apply_movement(conn, m)


def test_inactive_item_raises_conflict(conn):
    conn.execute("UPDATE items SET active = 0 WHERE id = 1")
    m = MovementCreate(item_id=1, kind="receive", quantity=1, to_location_id=1)
    with pytest.raises(ConflictError):
        stock.apply_movement(conn, m)


def test_same_location_transfer_raises_validation_error(conn):
    stock.apply_movement(
        conn, MovementCreate(item_id=1, kind="receive", quantity=5, to_location_id=1)
    )
    m = MovementCreate(
        item_id=1, kind="transfer", quantity=1, from_location_id=1, to_location_id=1
    )
    with pytest.raises(ValidationError):
        stock.apply_movement(conn, m)


def test_all_service_errors_are_inventory_errors(conn):
    with pytest.raises(InventoryError):
        stock.get_movement(conn, 999)


# --- the HTTP layer maps InventoryError in one place ---------------------------


def test_api_has_single_mapping_helper():
    exc = api.inventory_error_to_http(NotFoundError("item 7 not found"))
    assert exc.status_code == 404
    assert exc.detail == "item 7 not found"

    exc = api.inventory_error_to_http(ConflictError("nope"))
    assert exc.status_code == 409

    exc = api.inventory_error_to_http(ValidationError("bad"))
    assert exc.status_code == 400


def test_api_routes_have_no_per_route_stock_error_handling():
    import inspect

    source = inspect.getsource(api)
    assert "StockError" not in source
    # routes delegate to the single mapping; no per-route except blocks
    assert "except InventoryError" not in source


def test_not_found_error_maps_to_404_response(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 1, "to_location_id": 999},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "not found" in body["error"]["message"]


def test_conflict_error_maps_to_409_response(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 3, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]


def test_validation_error_maps_to_400_response(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "quantity": 1,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "same location" in body["error"]["message"]


def test_inventory_error_rolls_back_transaction(client, item, loc_a):
    # a failing movement must not leave a partially-applied transaction behind
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 5, "to_location_id": loc_a["id"]},
    )
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "quantity": 1,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 400
    movements = client.get("/movements").json()
    assert len(movements) == 1
    stock_resp = client.get(f"/items/{item['id']}/stock").json()
    assert stock_resp["total"] == 5
