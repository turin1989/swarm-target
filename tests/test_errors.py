"""Tests for the typed service-layer exceptions (T051)."""

import inspect

import pytest

from inventory.services import errors, stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)


# --- exception hierarchy -------------------------------------------------------


def test_inventory_error_is_an_exception():
    assert issubclass(InventoryError, Exception)
    exc = InventoryError("boom")
    assert str(exc) == "boom"
    assert isinstance(exc.status_code, int)


@pytest.mark.parametrize(
    ("cls", "expected_status"),
    [(NotFoundError, 404), (ConflictError, 409), (ValidationError, 400)],
)
def test_subclasses_carry_status_code(cls, expected_status):
    assert issubclass(cls, InventoryError)
    exc = cls("nope")
    assert exc.status_code == expected_status
    assert str(exc) == "nope"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")
    assert not hasattr(errors, "StockError")


# --- services/stock.py raises the typed exceptions -----------------------------


def test_apply_movement_missing_item_raises_not_found(client):
    # Use the service directly against the app's database.
    from inventory.db import connect
    from inventory.models import MovementCreate

    conn = connect(client.app.state.db_path)
    try:
        with pytest.raises(NotFoundError) as exc_info:
            stock.apply_movement(
                conn,
                MovementCreate(item_id=999, kind="receive", qty=1, to_location_id=1),
            )
    finally:
        conn.close()
    assert exc_info.value.status_code == 404


def test_get_movement_missing_raises_not_found(client):
    from inventory.db import connect

    conn = connect(client.app.state.db_path)
    try:
        with pytest.raises(NotFoundError):
            stock.get_movement(conn, 12345)
    finally:
        conn.close()


def test_apply_movement_inactive_item_raises_conflict(client, item, loc_a):
    from inventory.db import connect
    from inventory.models import MovementCreate

    r = client.put(f"/items/{item['id']}", json={"active": False})
    assert r.status_code == 200, r.text

    conn = connect(client.app.state.db_path)
    try:
        with pytest.raises(ConflictError) as exc_info:
            stock.apply_movement(
                conn,
                MovementCreate(
                    item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"]
                ),
            )
    finally:
        conn.close()
    assert exc_info.value.status_code == 409
    assert "inactive" in str(exc_info.value)


def test_apply_movement_missing_location_field_raises_validation(client, item):
    from inventory.db import connect
    from inventory.models import MovementCreate

    conn = connect(client.app.state.db_path)
    try:
        with pytest.raises(ValidationError) as exc_info:
            stock.apply_movement(
                conn,
                MovementCreate(item_id=item["id"], kind="receive", qty=1),
            )
    finally:
        conn.close()
    assert exc_info.value.status_code == 400


# --- api maps InventoryError centrally ------------------------------------------


def test_api_has_no_per_route_stock_error_handling():
    import inventory.api as api

    source = inspect.getsource(api)
    assert "StockError" not in source

    # Routes must not wrap service calls in try/except for InventoryError;
    # the only remaining except clause is the sqlite IntegrityError on create_item.
    import ast

    handlers = [
        node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ExceptHandler)
    ]
    caught = {ast.unparse(h.type) for h in handlers if h.type is not None}
    assert "InventoryError" not in caught
    assert caught <= {"sqlite3.IntegrityError"}


def test_app_registers_single_inventory_error_handler(client):
    handlers = client.app.exception_handlers
    assert InventoryError in handlers


def test_handler_maps_each_subclass_status():
    from fastapi import Request

    from inventory.api import inventory_error_handler

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    request = Request(scope)
    for exc, status in [
        (NotFoundError("missing"), 404),
        (ConflictError("clash"), 409),
        (ValidationError("bad"), 400),
    ]:
        response = inventory_error_handler(request, exc)
        assert response.status_code == status
        assert bytes(str(exc), "utf-8") in response.body


# --- end-to-end: HTTP responses still carry the right codes ---------------------


def test_movement_for_missing_item_returns_404(client, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": 999, "kind": "receive", "qty": 1, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_movement_missing_required_location_returns_400(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1},
    )
    assert r.status_code == 400
    assert "to_location_id" in r.json()["detail"]


def test_get_missing_movement_returns_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


# --- merged m5-opt services use the typed exceptions too -------------------------


def test_get_location_levels_missing_location_raises_not_found(client):
    from inventory.db import connect

    conn = connect(client.app.state.db_path)
    try:
        with pytest.raises(NotFoundError) as exc_info:
            stock.get_location_levels(conn, 98765)
    finally:
        conn.close()
    assert exc_info.value.status_code == 404
    assert "not found" in str(exc_info.value)


def test_reverse_adjust_movement_raises_validation_error(client, item, loc_a):
    from inventory.db import connect

    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "adjust", "qty": 5, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    movement_id = r.json()["id"]

    conn = connect(client.app.state.db_path)
    try:
        with pytest.raises(ValidationError) as exc_info:
            stock.reverse_movement(conn, movement_id)
    finally:
        conn.close()
    assert exc_info.value.status_code == 400
    assert "cannot be reversed" in str(exc_info.value)


def test_location_stock_missing_location_returns_404_via_handler(client):
    r = client.get("/locations/98765/stock")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_reverse_adjust_movement_returns_400_via_handler(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "adjust", "qty": 5, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text

    r2 = client.post(f"/movements/{r.json()['id']}/reverse")
    assert r2.status_code == 400
    assert "cannot be reversed" in r2.json()["detail"]
