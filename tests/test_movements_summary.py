"""Movements summary report."""


def test_summary_empty_db_has_all_kinds_with_zeros(client):
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 0, "qty": 0},
        "ship": {"count": 0, "qty": 0},
        "transfer": {"count": 0, "qty": 0},
    }


def test_summary_counts_and_qty_per_kind(client, item, loc_a, loc_b):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 10, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "qty": 4,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
        },
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 3, "from_location_id": loc_a["id"]},
    )
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 2, "qty": 15},
        "ship": {"count": 1, "qty": 3},
        "transfer": {"count": 1, "qty": 4},
    }


def test_summary_kinds_with_no_movements_present_with_zeros(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 7, "to_location_id": loc_a["id"]},
    )
    r = client.get("/reports/movements-summary")
    assert r.status_code == 200
    assert r.json() == {
        "receive": {"count": 1, "qty": 7},
        "ship": {"count": 0, "qty": 0},
        "transfer": {"count": 0, "qty": 0},
    }
