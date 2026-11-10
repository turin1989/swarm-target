"""T051: typed service exceptions in inventory.services.errors."""

import pytest

from inventory.services import stock
from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)

# --- exception hierarchy -------------------------------------------------------


def test_hierarchy():
    assert issubclass(NotFoundError, InventoryError)
    assert issubclass(ConflictError, InventoryError)
    assert issubclass(ValidationError, InventoryError)
    assert issubclass(InventoryError, Exception)


def test_status_codes():
    assert NotFoundError("x").status_code == 404
    assert ConflictError("x").status_code == 409
    assert ValidationError("x").status_code == 400


def test_message_is_preserved():
    exc = NotFoundError("item 1 not found")
    assert str(exc) == "item 1 not found"


def test_stock_error_is_removed():
    assert not hasattr(stock, "StockError")


# --- services.stock raises the typed exceptions --------------------------------


def _conn(client):
    # build a raw connection against the same schema the app uses
    from inventory.db import connect

    return connect(client.app.state.db_path)


def test_get_movement_raises_not_found(client):
    conn = _conn(client)
    try:
        with pytest.raises(NotFoundError) as exc_info:
            stock.get_movement(conn, 999)
        assert exc_info.value.status_code == 404
    finally:
        conn.close()


def test_apply_movement_unknown_item_raises_not_found(client):
    from inventory.models import MovementCreate

    conn = _conn(client)
    try:
        m = MovementCreate(item_id=999, kind="receive", quantity=1, to_location_id=1)
        with pytest.raises(NotFoundError):
            stock.apply_movement(conn, m)
    finally:
        conn.close()


def test_insufficient_stock_raises_conflict(client, item, loc_a):
    from inventory.models import MovementCreate

    conn = _conn(client)
    try:
        m = MovementCreate(
            item_id=item["id"], kind="ship", quantity=5, from_location_id=loc_a["id"]
        )
        with pytest.raises(ConflictError) as exc_info:
            stock.apply_movement(conn, m)
        assert exc_info.value.status_code == 409
    finally:
        conn.close()


def test_same_location_transfer_raises_validation(client, item, loc_a):
    from inventory.models import MovementCreate

    conn = _conn(client)
    try:
        m = MovementCreate(
            item_id=item["id"],
            kind="transfer",
            quantity=1,
            from_location_id=loc_a["id"],
            to_location_id=loc_a["id"],
        )
        with pytest.raises(ValidationError) as exc_info:
            stock.apply_movement(conn, m)
        assert exc_info.value.status_code == 400
    finally:
        conn.close()


# --- API maps InventoryError centrally ------------------------------------------


def test_api_has_no_per_route_stock_error_handling():
    import inspect

    from inventory import api

    source = inspect.getsource(api)
    assert "StockError" not in source
    # the only InventoryError handling lives in the shared route class
    assert source.count("except InventoryError") == 1


def test_not_found_maps_to_404(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 1, "to_location_id": 123},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_conflict_maps_to_409(client, item, loc_a):
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
    assert r.json()["error"]["code"] == "conflict"


def test_validation_maps_to_400(client, item, loc_a):
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
    assert r.json()["error"]["code"] == "bad_request"


def test_reverse_unknown_movement_maps_to_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
