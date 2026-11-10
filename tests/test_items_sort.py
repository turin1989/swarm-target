"""Sorting of GET /items via the `sort` query parameter."""

import pytest


@pytest.fixture()
def seeded(client):
    # Insertion order chosen so that id, name and sku orders all differ.
    specs = [
        {"sku": "C-3", "name": "Banana"},
        {"sku": "A-1", "name": "Cherry"},
        {"sku": "B-2", "name": "Apple"},
    ]
    for spec in specs:
        r = client.post("/items", json=spec)
        assert r.status_code == 201, r.text
    return specs


def _listed(client, **params):
    r = client.get("/items", params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_default_sort_is_id_ascending(client, seeded):
    items = _listed(client)
    assert [i["id"] for i in items] == [1, 2, 3]


def test_sort_by_id_ascending(client, seeded):
    items = _listed(client, sort="id")
    assert [i["id"] for i in items] == [1, 2, 3]


def test_sort_by_id_descending(client, seeded):
    items = _listed(client, sort="-id")
    assert [i["id"] for i in items] == [3, 2, 1]


def test_sort_by_name_ascending(client, seeded):
    items = _listed(client, sort="name")
    assert [i["name"] for i in items] == ["Apple", "Banana", "Cherry"]


def test_sort_by_name_descending(client, seeded):
    items = _listed(client, sort="-name")
    assert [i["name"] for i in items] == ["Cherry", "Banana", "Apple"]


def test_sort_by_sku_ascending(client, seeded):
    items = _listed(client, sort="sku")
    assert [i["sku"] for i in items] == ["A-1", "B-2", "C-3"]


def test_sort_by_sku_descending(client, seeded):
    items = _listed(client, sort="-sku")
    assert [i["sku"] for i in items] == ["C-3", "B-2", "A-1"]


@pytest.mark.parametrize(
    "bad",
    ["unit_price", "name,sku", "--name", "-", "", "ID", "name DESC", "id;DROP TABLE items"],
)
def test_invalid_sort_returns_422(client, seeded, bad):
    r = client.get("/items", params={"sort": bad})
    assert r.status_code == 422


def test_sort_combines_with_filters_and_pagination(client, seeded):
    r = client.get("/items", params={"sort": "-name", "limit": 2, "offset": 1})
    assert r.status_code == 200
    body = r.json()
    assert [i["name"] for i in body["items"]] == ["Banana", "Apple"]
    assert body["total"] == 3
