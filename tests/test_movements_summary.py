"""Movements summary report."""


def _move(client, item, kind, quantity, *, frm=None, to=None):
    payload = {"item_id": item["id"], "kind": kind, "quantity": quantity}
    if frm is not None:
        payload["from_location_id"] = frm["id"]
    if to is not None:
        payload["to_location_id"] = to["id"]
    r = client.post("/movements", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_summary_empty_db_has_all_kinds_with_zeros(client):
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 0, "qty": 0},
        "ship": {"count": 0, "qty": 0},
        "transfer": {"count": 0, "qty": 0},
    }


def test_summary_counts_and_sums_by_kind(client, item, loc_a, loc_b):
    _move(client, item, "receive", 10, to=loc_a)
    _move(client, item, "receive", 5, to=loc_a)
    _move(client, item, "ship", 3, frm=loc_a)
    _move(client, item, "transfer", 2, frm=loc_a, to=loc_b)
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 2, "qty": 15},
        "ship": {"count": 1, "qty": 3},
        "transfer": {"count": 1, "qty": 2},
    }


def test_summary_kinds_with_no_movements_present_with_zeros(client, item, loc_a):
    _move(client, item, "receive", 7, to=loc_a)
    body = client.get("/reports/movements-summary").json()
    assert body["receive"] == {"count": 1, "qty": 7}
    assert body["ship"] == {"count": 0, "qty": 0}
    assert body["transfer"] == {"count": 0, "qty": 0}
