"""T050: every 4xx/5xx response body is {"error": {"code": ..., "message": ...}}."""


def _assert_error_shape(r, status_code, code):
    assert r.status_code == status_code, r.text
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_404_http_exception_shape(client):
    r = client.get("/items/999")
    _assert_error_shape(r, 404, "not_found")
    assert "not found" in r.json()["error"]["message"]


def test_404_location_shape(client):
    r = client.get("/locations/999")
    _assert_error_shape(r, 404, "not_found")


def test_404_via_stock_service_error(client):
    # NotFoundError from the stock service is mapped to an HTTPException
    # by the app-level InventoryError handler
    r = client.get("/locations/999/stock")
    _assert_error_shape(r, 404, "not_found")


def test_409_conflict_shape(client, item):
    r = client.post(
        "/items",
        json={"sku": item["sku"], "name": "Dup", "unit_price": 1.0, "reorder_level": 0},
    )
    _assert_error_shape(r, 409, "conflict")
    assert item["sku"] in r.json()["error"]["message"]


def test_409_stock_error_shape(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "ship",
            "quantity": 1,
            "from_location_id": loc_a["id"],
        },
    )
    _assert_error_shape(r, 409, "conflict")
    assert "insufficient" in r.json()["error"]["message"]


def test_422_request_validation_error_shape(client):
    # Missing required fields triggers FastAPI's RequestValidationError.
    r = client.post("/items", json={})
    _assert_error_shape(r, 422, "validation_error")
    assert "sku" in r.json()["error"]["message"]


def test_422_path_param_validation_shape(client):
    r = client.get("/items/not-an-int")
    _assert_error_shape(r, 422, "validation_error")


def test_422_http_exception_shape(client):
    # Explicit HTTPException(422) raised by the bulk endpoint.
    r = client.post("/items/bulk", json=[])
    _assert_error_shape(r, 422, "validation_error")


def test_400_bad_request_shape(client, item, loc_a):
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
    _assert_error_shape(r, 400, "bad_request")
    assert "same location" in r.json()["error"]["message"]


def test_405_method_not_allowed_shape(client):
    # Other 4xx HTTPExceptions still use the uniform envelope.
    r = client.delete("/items")
    assert r.status_code == 405
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "bad_request"
    assert body["error"]["message"]
