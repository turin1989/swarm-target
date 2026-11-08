"""Hidden scoring test for T050."""
from tests.scoring.conftest import mk_item


def test_uniform_error_shape(sclient):
    r = sclient.get("/items/999")
    assert r.status_code == 404
    body = r.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "not_found"
    assert "999" in body["error"]["message"]

    mk_item(sclient, sku="DUP")
    r = sclient.post("/items", json={"sku": "DUP", "name": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"

    r = sclient.post("/items", json={"name": "no sku"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert set(r.json()) == {"error"}

    item = mk_item(sclient, sku="M")
    # receive without a destination -> 400 from the stock service
    r = sclient.post("/movements", json={"item_id": item["id"], "kind": "receive", "qty": 1, "quantity": 1})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"
