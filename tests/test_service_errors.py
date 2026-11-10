"""T051: typed service-layer exceptions in inventory.services.errors."""

import inspect
import sqlite3

import pytest

from inventory.db import init_db, connect
from inventory.models import MovementCreate
from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)


# --- exception hierarchy -------------------------------------------------------


def test_inventory_error_is_exception():
    assert issubclass(InventoryError, Exception)


@pytest.mark.parametrize(
    ("cls", "status"),
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_subclasses_carry_status_code(cls, status):
    assert issubclass(cls, InventoryError)
    exc = cls("boom")
    assert exc.status_code == status
    assert str(exc) == "boom"


def test_stock_error_removed():
    assert not hasattr(stock, "StockError")


# --- service layer raises typed exceptions ------------------------------------


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def seeded(conn):
    cur = conn.execute("INSERT INTO items (sku, name) VALUES ('S-1', 'Thing')")
    item_id = cur.lastrowid
    cur = conn.execute("INSERT INTO locations (code, name) VALUES ('L-A', 'A')")
    loc_id = cur.lastrowid
    return {"item_id": item_id, "loc_id": loc_id}


def test_missing_item_raises_not_found(conn, seeded):
    m = MovementCreate(item_id=9999, kind="receive", qty=1, to_location_id=seeded["loc_id"])
    with pytest.raises(NotFoundError) as exc_info:
        stock.apply_movement(conn, m)
    assert exc_info.value.status_code == 404


def test_missing_location_raises_not_found(conn, seeded):
    m = MovementCreate(item_id=seeded["item_id"], kind="receive", qty=1, to_location_id=9999)
    with pytest.raises(NotFoundError):
        stock.apply_movement(conn, m)


def test_missing_movement_raises_not_found(conn):
    with pytest.raises(NotFoundError):
        stock.get_movement(conn, 12345)


def test_insufficient_stock_raises_conflict(conn, seeded):
    m = MovementCreate(
        item_id=seeded["item_id"], kind="ship", qty=5, from_location_id=seeded["loc_id"]
    )
    with pytest.raises(ConflictError) as exc_info:
        stock.apply_movement(conn, m)
    assert exc_info.value.status_code == 409


def test_inactive_item_raises_conflict(conn, seeded):
    conn.execute("UPDATE items SET active = 0 WHERE id = ?", (seeded["item_id"],))
    m = MovementCreate(
        item_id=seeded["item_id"], kind="receive", qty=1, to_location_id=seeded["loc_id"]
    )
    with pytest.raises(ConflictError):
        stock.apply_movement(conn, m)


def test_missing_required_location_raises_validation(conn, seeded):
    m = MovementCreate(item_id=seeded["item_id"], kind="receive", qty=1)
    with pytest.raises(ValidationError) as exc_info:
        stock.apply_movement(conn, m)
    assert exc_info.value.status_code == 400


def test_same_location_transfer_raises_validation(conn, seeded):
    m = MovementCreate(
        item_id=seeded["item_id"],
        kind="transfer",
        qty=1,
        from_location_id=seeded["loc_id"],
        to_location_id=seeded["loc_id"],
    )
    with pytest.raises(ValidationError):
        stock.apply_movement(conn, m)


def test_typed_errors_caught_by_inventory_error(conn):
    with pytest.raises(InventoryError):
        stock.get_movement(conn, 99999)


# --- api maps InventoryError centrally ----------------------------------------


def test_api_has_no_per_route_stock_error_handling():
    """api.py must not catch service errors per-route; one handler does the mapping."""
    from inventory import api

    source = inspect.getsource(api)
    assert "StockError" not in source
    assert "except InventoryError" not in source
    assert hasattr(api, "inventory_error_handler")


def test_api_maps_not_found_error(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 4242},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "4242" in body["error"]["message"]


def test_api_maps_conflict_error(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "ship",
            "qty": 3,
            "from_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_api_maps_validation_error(client, item, loc_a):
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


def test_api_maps_movement_not_found_on_get(client):
    r = client.get("/movements/987654")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_api_maps_reverse_errors(client, item, loc_a):
    # reversing a missing movement -> 404 via NotFoundError
    r = client.post("/movements/5555/reverse")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

    # reversing an adjust movement -> 400 via ValidationError
    created = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "adjust", "qty": 7, "to_location_id": loc_a["id"]},
    )
    assert created.status_code == 201
    rev = client.post(f"/movements/{created.json()['id']}/reverse")
    assert rev.status_code == 400
    assert rev.json()["error"]["code"] == "bad_request"


def test_failed_movement_rolls_back(client, item, loc_a):
    """A ConflictError mid-request must not leave partial stock changes behind."""
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "ship",
            "qty": 1,
            "from_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 409
    levels = client.get(f"/items/{item['id']}/stock").json()
    assert levels["total"] == 0
