"""T050: uniform error response shape for all 4xx/5xx error responses.

Every error body must be {"error": {"code": "<snake_case>", "message": "<text>"}}
with codes: not_found (404), conflict (409), validation_error (422),
bad_request (400). Both HTTPException and request validation errors are
converted by exception handlers registered in main.py.
"""

import re

SNAKE_CASE = re.compile(r"^[a-z]+(_[a-z]+)*$")


def _assert_error_shape(r, status_code, code):
    assert r.status_code == status_code, r.text
    body = r.json()
    assert set(body.keys()) == {"error"}, body
    err = body["error"]
    assert set(err.keys()) == {"code", "message"}, err
    assert err["code"] == code
    assert SNAKE_CASE.match(err["code"])
    assert isinstance(err["message"], str) and err["message"]
    return err


# --- 404 not_found (HTTPException raised in route handlers) -------------------


def test_404_missing_item_uses_not_found_code(client):
    err = _assert_error_shape(client.get("/items/999"), 404, "not_found")
    assert "not found" in err["message"]


def test_404_missing_location_uses_not_found_code(client):
    _assert_error_shape(client.get("/locations/999"), 404, "not_found")


def test_404_missing_movement_uses_not_found_code(client):
    err = _assert_error_shape(client.get("/movements/999"), 404, "not_found")
    assert err["message"] == "movement 999 not found"


def test_404_missing_sku_uses_not_found_code(client):
    _assert_error_shape(client.get("/items/by-sku/NOPE"), 404, "not_found")


# --- 409 conflict --------------------------------------------------------------


def test_409_duplicate_sku_uses_conflict_code(client):
    assert client.post("/items", json={"sku": "DUP", "name": "a"}).status_code == 201
    r = client.post("/items", json={"sku": "DUP", "name": "b"})
    err = _assert_error_shape(r, 409, "conflict")
    assert "DUP" in err["message"]


def test_409_delete_item_with_stock_uses_conflict_code(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    _assert_error_shape(client.delete(f"/items/{item['id']}"), 409, "conflict")


def test_409_movement_on_inactive_item_uses_conflict_code(client, item, loc_a):
    assert client.put(f"/items/{item['id']}", json={"active": False}).status_code == 200
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": loc_a["id"]},
    )
    err = _assert_error_shape(r, 409, "conflict")
    assert "inactive" in err["message"]


# --- 422 validation_error (request validation errors) --------------------------


def test_422_missing_body_field_uses_validation_error_code(client):
    r = client.post("/items", json={"name": "missing sku"})
    err = _assert_error_shape(r, 422, "validation_error")
    assert "sku" in err["message"]


def test_422_missing_query_param_uses_validation_error_code(client):
    _assert_error_shape(client.get("/search"), 422, "validation_error")


def test_422_bad_path_param_uses_validation_error_code(client):
    _assert_error_shape(client.get("/items/not-a-number"), 422, "validation_error")


def test_422_from_http_exception_uses_validation_error_code(client):
    # invalid sort column raises HTTPException(422) in the route, not pydantic
    _assert_error_shape(client.get("/items", params={"sort": "nope"}), 422, "validation_error")


def test_422_non_positive_qty_uses_validation_error_code(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 0, "to_location_id": loc_a["id"]},
    )
    _assert_error_shape(r, 422, "validation_error")


# --- 400 bad_request ------------------------------------------------------------


def test_400_missing_movement_location_uses_bad_request_code(client, item):
    r = client.post("/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1})
    err = _assert_error_shape(r, 400, "bad_request")
    assert "required" in err["message"]


def test_400_adjust_with_from_location_uses_bad_request_code(client, item, loc_a, loc_b):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "adjust",
            "qty": 1,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
        },
    )
    _assert_error_shape(r, 400, "bad_request")
