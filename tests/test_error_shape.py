"""Uniform error response shape: {"error": {"code": ..., "message": ...}}."""


def _assert_error_shape(body, code):
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_404_not_found_shape(client):
    r = client.get("/items/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
    assert "not found" in r.json()["error"]["message"]


def test_404_location_not_found_shape(client):
    r = client.get("/locations/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_409_conflict_shape(client, item):
    r = client.post("/items", json={"sku": item["sku"], "name": "Dup"})
    assert r.status_code == 409
    _assert_error_shape(r.json(), "conflict")
    assert item["sku"] in r.json()["error"]["message"]


def test_422_request_validation_error_shape(client):
    r = client.post("/items", json={"name": "missing sku"})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")
    assert "sku" in r.json()["error"]["message"]


def test_422_query_validation_error_shape(client):
    r = client.get("/search")
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")
    assert "q" in r.json()["error"]["message"]


def test_400_bad_request_shape(client, item, loc_a):
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
    _assert_error_shape(r.json(), "bad_request")


def test_409_insufficient_stock_shape(client, item, loc_a):
    # T005 rejection (ship more than on hand) uses the uniform error shape
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 1, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 409
    _assert_error_shape(r.json(), "conflict")
    assert "insufficient" in r.json()["error"]["message"]


def test_stock_error_404_converted_via_http_exception(client, item):
    # StockError raised in the service layer surfaces through HTTPException
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 123},
    )
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_404_unknown_route_shape(client):
    r = client.get("/nope")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
