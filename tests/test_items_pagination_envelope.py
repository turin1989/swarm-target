"""GET /items returns a paginated envelope (T048)."""


def _make_items(client, n, prefix="SKU"):
    for i in range(n):
        r = client.post("/items", json={"sku": f"{prefix}-{i}", "name": f"Item {i}"})
        assert r.status_code == 201, r.text


def test_envelope_keys_and_defaults_when_empty(client):
    r = client.get("/items")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 100  # default limit
    assert body["offset"] == 0  # default offset


def test_envelope_contains_item_objects(client, item):
    body = client.get("/items").json()
    assert body["items"] == [item]
    assert body["total"] == 1


def test_envelope_echoes_limit_and_offset(client):
    _make_items(client, 5)
    r = client.get("/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [i["sku"] for i in body["items"]] == ["SKU-1", "SKU-2"]


def test_envelope_total_ignores_pagination(client):
    _make_items(client, 5)
    body = client.get("/items", params={"limit": 2, "offset": 3}).json()
    assert len(body["items"]) == 2
    assert body["total"] == 5

    body = client.get("/items", params={"offset": 99}).json()
    assert body["items"] == []
    assert body["total"] == 5


def test_envelope_total_respects_filters(client):
    _make_items(client, 3, prefix="ON")
    client.post("/items", json={"sku": "OFF-0", "name": "Off"})
    client.put("/items/4", json={"active": False})

    body = client.get("/items", params={"active": "true", "limit": 1}).json()
    assert len(body["items"]) == 1
    assert body["total"] == 3

    body = client.get("/items", params={"active": "false"}).json()
    assert body["total"] == 1

    body = client.get("/items", params={"sku": "ON-1"}).json()
    assert body["total"] == 1
    assert [i["sku"] for i in body["items"]] == ["ON-1"]


def test_envelope_total_matches_header(client):
    _make_items(client, 4)
    r = client.get("/items", params={"limit": 2})
    assert r.json()["total"] == int(r.headers["X-Total-Count"]) == 4
