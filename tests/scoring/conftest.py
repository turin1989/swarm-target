"""Fixtures for hidden scoring tests. Deliberately independent of tests/conftest.py so
interface-change tasks (field renames etc.) do not break unrelated scoring tests."""

import pytest
from fastapi.testclient import TestClient

from inventory.main import create_app


@pytest.fixture()
def sclient(tmp_path):
    app = create_app(str(tmp_path / "scoring.db"))
    with TestClient(app) as c:
        yield c


def mk_item(client, sku="SKU-1", name="Thing", **extra):
    r = client.post("/items", json={"sku": sku, "name": name, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def mk_loc(client, code="L1", name="Loc 1"):
    r = client.post("/locations", json={"code": code, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def move(client, **payload):
    return client.post("/movements", json=payload)


def qty_key(body):
    """Movement/StockLevel quantity key: 'quantity' after T047, 'qty' before."""
    return "quantity" if "quantity" in body else "qty"


def receive(client, item_id, loc_id, n):
    # send both spellings so this helper works before and after T047 (extra keys are ignored)
    r = move(client, item_id=item_id, kind="receive", qty=n, quantity=n, to_location_id=loc_id)
    assert r.status_code == 201, r.text
    return r.json()


def total(client, item_id):
    return client.get(f"/items/{item_id}/stock").json()["total"]
