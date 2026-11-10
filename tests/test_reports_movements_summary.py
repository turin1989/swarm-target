"""GET /reports/movements-summary."""


def _move(client, **kw):
    r = client.post("/movements", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def test_empty_summary_has_all_kinds_zeroed(client):
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 0, "qty": 0},
        "ship": {"count": 0, "qty": 0},
        "transfer": {"count": 0, "qty": 0},
    }


def test_summary_counts_and_quantities(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    _move(client, item_id=item["id"], kind="ship", qty=3, from_location_id=loc_b["id"])

    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 2, "qty": 15},
        "ship": {"count": 1, "qty": 3},
        "transfer": {"count": 1, "qty": 4},
    }


def test_kinds_without_movements_are_zeroed(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=7, to_location_id=loc_a["id"])

    body = client.get("/reports/movements-summary").json()
    assert body["receive"] == {"count": 1, "qty": 7}
    assert body["ship"] == {"count": 0, "qty": 0}
    assert body["transfer"] == {"count": 0, "qty": 0}
