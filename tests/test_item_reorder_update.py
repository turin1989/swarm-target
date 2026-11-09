"""Regression tests for T004: PUT /items/{id} must not silently ignore the
reorder threshold.

Note: the field was renamed from ``reorder_point`` to ``reorder_level`` by
T049 (commit a368a68); the legacy ``reorder_point`` key is intentionally
rejected with 422 (see tests/test_items.py). These tests pin down that the
canonical field is persisted, returned, composable with other fields, and
untouched when omitted.
"""


def test_put_reorder_value_persists_and_is_returned(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 12})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 12
    # persisted, not just echoed back
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 12


def test_put_reorder_value_together_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_level": 9, "name": "Combined", "unit_price": 4.5, "description": "d"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_level"] == 9
    assert body["name"] == "Combined"
    assert body["unit_price"] == 4.5
    assert body["description"] == "d"
    stored = client.get(f"/items/{item['id']}").json()
    assert stored["reorder_level"] == 9
    assert stored["name"] == "Combined"
    assert stored["unit_price"] == 4.5


def test_put_omitting_reorder_value_leaves_it_untouched(client, item):
    assert item["reorder_level"] == 5
    # a few updates that never mention the reorder threshold
    assert client.put(f"/items/{item['id']}", json={"name": "First"}).status_code == 200
    assert client.put(f"/items/{item['id']}", json={"unit_price": 1.0}).status_code == 200
    r = client.put(f"/items/{item['id']}", json={"active": True})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 5
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5


def test_put_reorder_value_can_be_set_to_zero(client, item):
    # 0 is falsy; the update path must not drop it as "unset"
    assert item["reorder_level"] == 5
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 0})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 0
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 0


def test_put_reorder_value_repeated_updates_each_persist(client, item):
    for value in (3, 11, 2):
        r = client.put(f"/items/{item['id']}", json={"reorder_level": value})
        assert r.status_code == 200
        assert r.json()["reorder_level"] == value
        assert client.get(f"/items/{item['id']}").json()["reorder_level"] == value


def test_put_legacy_reorder_point_key_is_rejected_not_ignored(client, item):
    # Pre-fix the API dropped unknown keys on the floor; now it must fail loudly
    # (the canonical spelling is reorder_level since T049).
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    assert r.status_code == 422
    # and the stored value is untouched by the rejected request
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5
