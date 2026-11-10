"""T003: a transfer must debit the source location and credit the destination."""


def _move(client, **payload):
    r = client.post("/movements", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _levels_by_location(client, item_id):
    r = client.get(f"/items/{item_id}/stock")
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {lvl["location_id"]: lvl["qty"] for lvl in body["levels"]}


def test_transfer_debits_source_and_credits_destination(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])

    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )

    _, levels = _levels_by_location(client, item["id"])
    # stock at from_location_id decreased by 2
    assert levels[loc_a["id"]] == 8
    # stock at to_location_id increased by 2
    assert levels[loc_b["id"]] == 2


def test_transfer_leaves_total_stock_unchanged(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=7, to_location_id=loc_a["id"])
    before, _ = _levels_by_location(client, item["id"])
    assert before["total"] == 7

    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )

    after, _ = _levels_by_location(client, item["id"])
    assert after["total"] == 7


def test_item_stock_endpoint_reflects_both_locations_after_transfer(
    client, item, loc_a, loc_b
):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])

    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )

    body, levels = _levels_by_location(client, item["id"])
    # both locations appear in GET /items/{id}/stock with the expected quantities
    assert set(levels) == {loc_a["id"], loc_b["id"]}
    assert levels == {loc_a["id"]: 3, loc_b["id"]: 2}
    assert body["total"] == 5


def test_repeated_transfers_accumulate_correctly(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])

    for _ in range(3):
        _move(
            client,
            item_id=item["id"],
            kind="transfer",
            qty=2,
            from_location_id=loc_a["id"],
            to_location_id=loc_b["id"],
        )

    body, levels = _levels_by_location(client, item["id"])
    assert levels[loc_a["id"]] == 4
    assert levels[loc_b["id"]] == 6
    assert body["total"] == 10


def test_transfer_back_restores_original_distribution(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=6, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_b["id"],
        to_location_id=loc_a["id"],
    )

    body, levels = _levels_by_location(client, item["id"])
    assert levels[loc_a["id"]] == 6
    assert levels.get(loc_b["id"], 0) == 0
    assert body["total"] == 6
