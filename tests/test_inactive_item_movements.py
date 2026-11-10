"""T041: movements for inactive items are rejected with 409 and stock is unchanged."""

import pytest


def _deactivate(client, item_id):
    r = client.put(f"/items/{item_id}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False


def _error_detail(response) -> str:
    """Return the error detail/message regardless of error envelope shape."""
    body = response.json()
    if "detail" in body:
        return body["detail"]
    return body["error"]["message"]


def _stock(client, item_id):
    r = client.get(f"/items/{item_id}/stock")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("kind", ["receive", "ship", "transfer", "adjust"])
def test_movement_for_inactive_item_409(client, item, loc_a, loc_b, kind):
    # seed some stock while the item is still active
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 10, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text

    _deactivate(client, item["id"])
    before = _stock(client, item["id"])

    payload = {"item_id": item["id"], "kind": kind, "quantity": 3}
    if kind in ("ship", "transfer"):
        payload["from_location_id"] = loc_a["id"]
    if kind in ("receive", "transfer", "adjust"):
        payload["to_location_id"] = loc_b["id"]

    r = client.post("/movements", json=payload)
    assert r.status_code == 409, r.text
    assert "inactive" in _error_detail(r)

    # stock levels unchanged
    assert _stock(client, item["id"]) == before


def test_reverse_movement_for_inactive_item_409(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 7, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    movement_id = r.json()["id"]

    _deactivate(client, item["id"])
    before = _stock(client, item["id"])

    r = client.post(f"/movements/{movement_id}/reverse")
    assert r.status_code == 409, r.text
    assert "inactive" in _error_detail(r)
    assert _stock(client, item["id"]) == before
