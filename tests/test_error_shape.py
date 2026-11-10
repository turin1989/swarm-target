"""Uniform error response shape: {"error": {"code": ..., "message": ...}}."""


def _assert_error_shape(body: dict, code: str) -> None:
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_404_not_found_shape(client):
    r = client.get("/items/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")
    assert r.json()["error"]["message"] == "item 999 not found"


def test_404_location_not_found_shape(client):
    r = client.get("/locations/999")
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_404_unknown_route_shape(client):
    r = client.get("/nope")
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


def test_422_query_validation_error_shape(client):
    r = client.get("/items", params={"limit": 0})
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


def test_422_from_http_exception_shape(client, item, loc_a):
    # quantity validation happens before the service layer and surfaces as HTTPException(422)
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 0, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 422
    _assert_error_shape(r.json(), "validation_error")


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
    assert r.status_code == 400
    _assert_error_shape(r.json(), "bad_request")


def test_404_from_service_layer_shape(client, item):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 1, "to_location_id": 123},
    )
    assert r.status_code == 404
    _assert_error_shape(r.json(), "not_found")


def test_405_method_not_allowed_still_wrapped(client):
    r = client.delete("/items")
    assert r.status_code == 405
    body = r.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message"}


def test_no_detail_key_in_error_responses(client):
    for r in (client.get("/items/999"), client.post("/items", json={})):
        assert "detail" not in r.json()
