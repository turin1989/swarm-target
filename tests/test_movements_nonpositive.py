"""T040: reject non-positive movement quantities at every layer."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from inventory.db import connect, init_db
from inventory.models import MovementCreate
from inventory.services import stock
from inventory.services.errors import ValidationError

# --- model layer ---------------------------------------------------------------


@pytest.mark.parametrize("qty", [0, -1, -100])
def test_movement_create_model_rejects_non_positive_quantity(qty):
    with pytest.raises(PydanticValidationError):
        MovementCreate(item_id=1, kind="receive", quantity=qty, to_location_id=1)


# --- service layer -------------------------------------------------------------


@pytest.fixture()
def conn(tmp_path):
    path = str(tmp_path / "svc.db")
    init_db(path)
    c = connect(path)
    try:
        c.execute(
            "INSERT INTO items (sku, name, description, unit_price, reorder_level,"
            " active, created_at) VALUES ('SKU-1', 'Thing', '', 1.0, 0, 1, '2026-01-01')"
        )
        c.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")
        yield c
    finally:
        c.close()


@pytest.mark.parametrize("qty", [0, -1, -100])
@pytest.mark.parametrize("kind", ["receive", "ship", "transfer", "adjust"])
def test_apply_movement_rejects_non_positive_quantity_without_writing(conn, kind, qty):
    # Bypass the pydantic constraint to exercise the service-level guard.
    movement = MovementCreate.model_construct(
        item_id=1,
        kind=kind,
        quantity=qty,
        from_location_id=1 if kind in ("ship", "transfer") else None,
        to_location_id=1 if kind in ("receive", "transfer", "adjust") else None,
        note="",
        reference=None,
    )
    with pytest.raises(ValidationError):
        stock.apply_movement(conn, movement)
    # no movement row was written and stock levels are untouched
    assert conn.execute("SELECT COUNT(*) AS n FROM movements").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM stock_levels").fetchone()["n"] == 0


# --- API layer -----------------------------------------------------------------


@pytest.mark.parametrize("qty", [0, -1, -100])
@pytest.mark.parametrize("kind", ["receive", "ship", "transfer", "adjust"])
def test_post_movements_non_positive_qty_422_no_row(client, item, loc_a, loc_b, kind, qty):
    payload = {"item_id": item["id"], "kind": kind, "quantity": qty}
    if kind in ("ship", "transfer"):
        payload["from_location_id"] = loc_a["id"]
    if kind in ("receive", "transfer", "adjust"):
        payload["to_location_id"] = loc_b["id"] if kind == "transfer" else loc_a["id"]

    r = client.post("/movements", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    # no movement row was written and stock is untouched
    assert client.get("/movements").json() == []
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 0
    assert s["levels"] == []
