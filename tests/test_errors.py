"""Tests for the typed service exceptions (T051)."""

import inspect

import pytest

from inventory.services.errors import (
    ConflictError,
    InventoryError,
    NotFoundError,
    ValidationError,
)

# --- exception hierarchy -------------------------------------------------------


def test_hierarchy_and_default_status_codes():
    assert issubclass(NotFoundError, InventoryError)
    assert issubclass(ConflictError, InventoryError)
    assert issubclass(ValidationError, InventoryError)
    assert issubclass(InventoryError, Exception)

    assert NotFoundError("x").status_code == 404
    assert ConflictError("x").status_code == 409
    assert ValidationError("x").status_code == 400


def test_exceptions_carry_message():
    exc = NotFoundError("item 7 not found")
    assert str(exc) == "item 7 not found"


def test_status_code_can_be_overridden():
    assert ValidationError("bad qty", status_code=422).status_code == 422


def test_stock_error_is_removed():
    from inventory.services import stock

    assert not hasattr(stock, "StockError")


# --- service layer raises typed exceptions -------------------------------------


@pytest.fixture()
def conn():
    from inventory.db import SCHEMA, connect

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S2', 'Retired', '', 1.0, 0, 0)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
    return conn


def _mc(**kw):
    from inventory.models import MovementCreate

    defaults = dict(
        item_id=1, kind="receive", qty=1, from_location_id=None, to_location_id=1, note=""
    )
    defaults.update(kw)
    return MovementCreate.model_construct(**defaults)


def test_unknown_item_raises_not_found(conn):
    from inventory.services.stock import apply_movement

    with pytest.raises(NotFoundError) as exc:
        apply_movement(conn, _mc(item_id=99))
    assert exc.value.status_code == 404


def test_unknown_location_raises_not_found(conn):
    from inventory.services.stock import apply_movement

    with pytest.raises(NotFoundError) as exc:
        apply_movement(conn, _mc(to_location_id=99))
    assert exc.value.status_code == 404


def test_inactive_item_raises_conflict(conn):
    from inventory.services.stock import apply_movement

    with pytest.raises(ConflictError) as exc:
        apply_movement(conn, _mc(item_id=2))
    assert exc.value.status_code == 409


def test_missing_location_raises_validation(conn):
    from inventory.services.stock import apply_movement

    with pytest.raises(ValidationError) as exc:
        apply_movement(conn, _mc(to_location_id=None))
    assert exc.value.status_code == 400


def test_transfer_same_location_raises_validation(conn):
    from inventory.services.stock import apply_movement

    with pytest.raises(ValidationError) as exc:
        apply_movement(
            conn, _mc(kind="transfer", from_location_id=1, to_location_id=1)
        )
    assert exc.value.status_code == 400


def test_missing_movement_raises_not_found(conn):
    from inventory.services.stock import get_movement

    with pytest.raises(NotFoundError):
        get_movement(conn, 999)


# --- api maps InventoryError centrally ------------------------------------------


def test_api_has_no_per_route_stock_error_handling():
    """api.py maps InventoryError in one place, not via per-route try/except."""
    import inventory.api as api

    source = inspect.getsource(api)
    assert "StockError" not in source
    # the only reference to InventoryError in route code is the single handler
    assert source.count("InventoryError") >= 1
    assert "except stock." not in source
    assert hasattr(api, "inventory_error_handler")


def test_handler_registered_on_app(client):
    app = client.app
    assert InventoryError in app.exception_handlers


def test_inventory_error_mapped_to_http_response(client, item, loc_a):
    # NotFoundError -> 404
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 999},
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]

    # ValidationError -> 400
    r = client.post(
        "/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1}
    )
    assert r.status_code == 400
    assert "required" in r.json()["detail"]

    # ConflictError -> 409
    client.put(f"/items/{item['id']}", json={"active": False})
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "qty": 1,
            "to_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 409
    assert "inactive" in r.json()["detail"]


def test_inventory_error_rolls_back_transaction(client, item, loc_a):
    """A movement rejected by the service leaves no movement row behind."""
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
    assert client.get("/movements").json() == []
