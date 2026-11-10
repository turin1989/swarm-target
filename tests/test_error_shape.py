"""Tests for the uniform error response shape.

Every 4xx/5xx response body must be:
    {"error": {"code": "<snake_case>", "message": "<text>"}}
"""


def _assert_error_shape(body: dict, expected_code: str) -> None:
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == expected_code
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
    r = client.post(
        "/items",
        json={"sku": item["sku"], "name": "Duplicate", "unit_price": 1.0},
    )
    assert r.status_code == 409
    _assert_error_shape(r.json(), "conflict")
    assert item["sku"] in r.json()["error"]["message"]


def test_422_request_validation_error_shape(client):
    # missing required fields triggers FastAPI's RequestValidationError
    r = client.post("/items", json={})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


def test_422_query_validation_error_shape(client):
    r = client.get("/items", params={"limit": 0})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


def test_422_http_exception_shape(client):
    # a blank (whitespace-only) q raises HTTPException(422) in the route
    r = client.get("/search", params={"q": " "})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


def test_400_bad_request_shape(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1},
    )
    assert r.status_code == 400
    _assert_error_shape(r.json(), "bad_request")
    assert "required" in r.json()["error"]["message"]


def test_404_movement_unknown_location_shape(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 123},
    )
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
