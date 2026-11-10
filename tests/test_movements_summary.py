"""Movement summary report."""

EMPTY = {
    "receive": {"count": 0, "qty": 0},
    "ship": {"count": 0, "qty": 0},
    "transfer": {"count": 0, "qty": 0},
}


def _move(client, item, kind, qty, from_loc=None, to_loc=None):
    payload = {"item_id": item["id"], "kind": kind, "qty": qty}
    if from_loc is not None:
        payload["from_location_id"] = from_loc["id"]
    if to_loc is not None:
        payload["to_location_id"] = to_loc["id"]
    r = client.post("/movements", json=payload)
    assert r.status_code == 201, r.text


def test_summary_empty_db_has_all_kinds_with_zeros(client):
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == EMPTY


def test_summary_counts_and_sums_by_kind(client, item, loc_a, loc_b):
    _move(client, item, "receive", 10, to_loc=loc_a)
    _move(client, item, "receive", 5, to_loc=loc_a)
    _move(client, item, "transfer", 4, from_loc=loc_a, to_loc=loc_b)
    _move(client, item, "ship", 3, from_loc=loc_b)
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 2, "qty": 15},
        "ship": {"count": 1, "qty": 3},
        "transfer": {"count": 1, "qty": 4},
    }


def test_summary_kinds_with_no_movements_present_with_zeros(client, item, loc_a):
    _move(client, item, "receive", 7, to_loc=loc_a)
    body = client.get("/reports/movements-summary").json()
    assert set(body) == {"receive", "ship", "transfer"}
    assert body["receive"] == {"count": 1, "qty": 7}
    assert body["ship"] == {"count": 0, "qty": 0}
    assert body["transfer"] == {"count": 0, "qty": 0}
