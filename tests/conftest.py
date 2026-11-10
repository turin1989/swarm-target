import pytest
from fastapi.testclient import TestClient

from inventory.main import create_app


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def item(client):
    r = client.post(
        "/items",
        json={"sku": "WIDGET-1", "name": "Widget", "unit_price": 2.5, "reorder_level": 5},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def loc_a(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def loc_b(client):
    r = client.post("/locations", json={"code": "WH-B", "name": "Warehouse B"})
    assert r.status_code == 201, r.text
    return r.json()
