"""Uniform error response shape: {"error": {"code": ..., "message": ...}}."""


def _assert_error_shape(body: dict, code: str) -> None:
    assert set(body) == {"error"}, body
    assert set(body["error"]) == {"code", "message"}, body
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_404_http_exception_shape(client):
    """HTTPException raised in a route -> not_found."""
    r = client.get("/items/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_404_service_error_shape(client, item):
    """Service-layer NotFoundError -> not_found."""
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": 999},
    )
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_409_conflict_shape(client, item):
    """Duplicate SKU -> HTTPException(409) -> conflict."""
    r = client.post("/items", json={"sku": item["sku"], "name": "dupe"})
    assert r.status_code == 409
    _assert_error_shape(r.json(), "conflict")


def test_422_request_validation_error_shape(client):
    """Pydantic request validation errors -> validation_error."""
    r = client.post("/items", json={"name": "missing sku"})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")
    assert "sku" in r.json()["error"]["message"]


def test_422_query_validation_error_shape(client):
    """Query-parameter validation errors -> validation_error."""
    r = client.get("/items", params={"limit": 0})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


def test_400_bad_request_shape(client, item):
    """Service-layer ValidationError -> bad_request."""
    r = client.post("/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1})
    assert r.status_code == 400
    _assert_error_shape(r.json(), "bad_request")


def test_error_body_has_no_detail_key(client):
    """The legacy FastAPI `detail` key must be gone from error bodies."""
    for r in (
        client.get("/items/999"),
        client.post("/items", json={}),
    ):
        assert r.status_code >= 400
        assert "detail" not in r.json()
