"""T041: movements against inactive items are rejected with 409."""

import pytest


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _detail(response):
    """The HTTPException detail surfaces as error.message in the uniform shape."""
    body = response.json()
    return body["error"]["message"]


def _deactivate(client, item_id):
    r = client.put(f"/items/{item_id}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False


@pytest.mark.parametrize(
    "kind,loc_fields",
    [
        ("receive", {"to_location_id": "a"}),
        ("ship", {"from_location_id": "a"}),
        ("transfer", {"from_location_id": "a", "to_location_id": "b"}),
        ("adjust", {"to_location_id": "a"}),
    ],
)
def test_any_movement_kind_rejected_for_inactive_item(
    client, item, loc_a, loc_b, kind, loc_fields
):
    # Seed some stock while the item is still active so ship/transfer would
    # otherwise succeed.
    r = _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    assert r.status_code == 201

    _deactivate(client, item["id"])

    locs = {"a": loc_a["id"], "b": loc_b["id"]}
    kwargs = {k: locs[v] for k, v in loc_fields.items()}
    r = _move(client, item_id=item["id"], kind=kind, quantity=3, **kwargs)
    assert r.status_code == 409, r.text
    assert "inactive" in _detail(r)


def test_stock_levels_unchanged_after_rejected_movement(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    before = client.get(f"/items/{item['id']}/stock").json()

    _deactivate(client, item["id"])

    for kind, kwargs in [
        ("receive", {"to_location_id": loc_a["id"]}),
        ("ship", {"from_location_id": loc_a["id"]}),
        ("transfer", {"from_location_id": loc_a["id"], "to_location_id": loc_b["id"]}),
        ("adjust", {"to_location_id": loc_a["id"]}),
    ]:
        r = _move(client, item_id=item["id"], kind=kind, quantity=2, **kwargs)
        assert r.status_code == 409

    after = client.get(f"/items/{item['id']}/stock").json()
    assert after == before
    assert after["total"] == 10


def test_no_movement_record_created_for_inactive_item(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _deactivate(client, item["id"])

    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 409

    movements = client.get("/movements", params={"item_id": item["id"]}).json()
    assert len(movements) == 1


def test_reactivated_item_accepts_movements_again(client, item, loc_a):
    _deactivate(client, item["id"])
    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    assert r.status_code == 409

    r = client.put(f"/items/{item['id']}", json={"active": True})
    assert r.status_code == 200

    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5
