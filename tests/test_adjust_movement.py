"""The 'adjust' movement kind (T039): set stock at a location to an absolute qty."""

import pytest


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_adjust_sets_stock_absolute_on_empty_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=7, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 7
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 7}]


def test_adjust_overwrites_existing_stock_not_a_delta(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=3, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 3}]


def test_adjust_can_raise_stock_above_current(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=2, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=50, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 50


def test_adjust_only_affects_target_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=4, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=9, to_location_id=loc_b["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=1, to_location_id=loc_b["id"])
    assert r.status_code == 201, r.text
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "qty": 4},
        {"item_id": item["id"], "location_id": loc_b["id"], "qty": 1},
    ]
    assert s["total"] == 5


def test_adjust_is_recorded_with_kind_adjust(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=6,
        to_location_id=loc_a["id"],
        note="cycle count",
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "adjust"
    assert body["qty"] == 6
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None
    assert body["note"] == "cycle count"

    # persisted and retrievable
    assert client.get(f"/movements/{body['id']}").json()["kind"] == "adjust"
    listed = client.get("/movements", params={"kind": "adjust"}).json()
    assert [m["id"] for m in listed] == [body["id"]]
    assert all(m["kind"] == "adjust" for m in listed)


def test_adjust_requires_to_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=5)
    assert r.status_code == 400
    assert "to_location_id" in r.json()["error"]["message"]
    assert "required" in r.json()["error"]["message"]
    # nothing was written
    assert client.get("/movements").json() == []


def test_adjust_rejects_from_location(client, item, loc_a, loc_b):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=5,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 400
    assert "from_location_id" in r.json()["error"]["message"]
    # nothing was written and stock untouched
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_adjust_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=123)
    assert r.status_code == 404


def test_adjust_unknown_item_404(client, loc_a):
    r = _move(client, item_id=999, kind="adjust", qty=5, to_location_id=loc_a["id"])
    assert r.status_code == 404


@pytest.mark.parametrize("qty", [0, -1, -10])
def test_adjust_non_positive_qty_422(client, item, loc_a, qty):
    r = _move(client, item_id=item["id"], kind="adjust", qty=qty, to_location_id=loc_a["id"])
    assert r.status_code == 422


def test_adjust_cannot_be_reversed(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=loc_a["id"])
    movement_id = r.json()["id"]
    rev = client.post(f"/movements/{movement_id}/reverse")
    assert rev.status_code == 400
    assert "cannot be reversed" in rev.json()["error"]["message"]
    # stock untouched
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5
