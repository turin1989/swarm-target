"""T041: movements for inactive items are rejected with 409 and leave stock unchanged."""

import pytest


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _deactivate(client, item_id):
    r = client.put(f"/items/{item_id}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False


def _levels(client, item_id):
    r = client.get(f"/items/{item_id}/stock")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("kind", ["receive", "ship", "transfer", "adjust"])
def test_movement_for_inactive_item_rejected_409(client, item, loc_a, loc_b, kind):
    # Seed some stock while the item is still active so outbound kinds would
    # otherwise succeed.
    r = _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    before = _levels(client, item["id"])

    _deactivate(client, item["id"])

    payload = {"item_id": item["id"], "kind": kind, "quantity": 3}
    if kind in ("receive", "adjust"):
        payload["to_location_id"] = loc_a["id"]
    elif kind == "ship":
        payload["from_location_id"] = loc_a["id"]
    else:  # transfer
        payload["from_location_id"] = loc_a["id"]
        payload["to_location_id"] = loc_b["id"]

    r = _move(client, **payload)
    assert r.status_code == 409, r.text
    detail = r.json()["error"]["message"]
    assert "inactive" in detail

    # Stock levels must be unchanged.
    assert _levels(client, item["id"]) == before


def test_no_movement_record_created_for_inactive_item(client, item, loc_a):
    _deactivate(client, item["id"])
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 409
    detail = r.json()["error"]["message"]
    assert "inactive" in detail
    assert client.get("/movements", params={"item_id": item["id"]}).json() == []


def test_reactivated_item_accepts_movements_again(client, item, loc_a):
    _deactivate(client, item["id"])
    assert _move(
        client, item_id=item["id"], kind="receive", quantity=2, to_location_id=loc_a["id"]
    ).status_code == 409

    r = client.put(f"/items/{item['id']}", json={"active": True})
    assert r.status_code == 200

    r = _move(client, item_id=item["id"], kind="receive", quantity=2, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    stock = _levels(client, item["id"])
    assert stock["total"] == 2
    assert stock["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 2}
    ]
