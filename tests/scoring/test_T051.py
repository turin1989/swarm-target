"""Hidden scoring test for T051."""
import importlib

import pytest


def test_typed_service_exceptions(sclient):
    errors = importlib.import_module("inventory.services.errors")
    stock = importlib.import_module("inventory.services.stock")
    assert not hasattr(stock, "StockError")
    for name, code in (("NotFoundError", 404), ("ConflictError", 409), ("ValidationError", 400)):
        cls = getattr(errors, name)
        assert issubclass(cls, errors.InventoryError)
        assert cls("x").status_code == code

    from inventory.db import connect
    from inventory.models import MovementCreate

    conn = connect(str(sclient.app.state.db_path))
    payload = MovementCreate.model_validate(
        {"item_id": 999, "kind": "receive", "qty": 1, "quantity": 1, "to_location_id": 1}
    )
    with pytest.raises(errors.NotFoundError):
        stock.apply_movement(conn, payload)
    with pytest.raises(errors.NotFoundError):
        stock.get_movement(conn, 999)
    # HTTP mapping still works
    assert sclient.get("/items/999").status_code == 404
