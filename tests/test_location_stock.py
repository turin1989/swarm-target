def _make_item(client, sku):
    r = client.post("/items", json={"sku": sku, "name": f"Item {sku}"})
    assert r.status_code == 201, r.text
    return r.json()


def _receive(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "qty": qty, "to_location_id": location_id},
    )
    assert r.status_code == 201, r.text


def _ship(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "ship", "qty": qty, "from_location_id": location_id},
    )
    assert r.status_code == 201, r.text


class TestLocationStock:
    def test_empty_location_returns_no_levels(self, client, loc_a):
        r = client.get(f"/locations/{loc_a['id']}/stock")
        assert r.status_code == 200, r.text
        assert r.json() == {"location_id": loc_a["id"], "levels": []}

    def test_levels_ordered_by_item_id(self, client, loc_a):
        item_1 = _make_item(client, "SKU-1")
        item_2 = _make_item(client, "SKU-2")
        item_3 = _make_item(client, "SKU-3")
        # receive out of item_id order
        _receive(client, item_3["id"], loc_a["id"], 7)
        _receive(client, item_1["id"], loc_a["id"], 4)
        _receive(client, item_2["id"], loc_a["id"], 9)

        r = client.get(f"/locations/{loc_a['id']}/stock")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["location_id"] == loc_a["id"]
        assert body["levels"] == [
            {"item_id": item_1["id"], "location_id": loc_a["id"], "qty": 4},
            {"item_id": item_2["id"], "location_id": loc_a["id"], "qty": 9},
            {"item_id": item_3["id"], "location_id": loc_a["id"], "qty": 7},
        ]

    def test_zero_qty_levels_are_omitted(self, client, loc_a):
        item_1 = _make_item(client, "SKU-1")
        item_2 = _make_item(client, "SKU-2")
        _receive(client, item_1["id"], loc_a["id"], 5)
        _receive(client, item_2["id"], loc_a["id"], 3)
        _ship(client, item_1["id"], loc_a["id"], 5)  # back to zero

        r = client.get(f"/locations/{loc_a['id']}/stock")
        assert r.status_code == 200, r.text
        assert r.json()["levels"] == [
            {"item_id": item_2["id"], "location_id": loc_a["id"], "qty": 3}
        ]

    def test_negative_qty_levels_are_included(self, client, loc_a):
        # only qty == 0 levels are omitted; negative levels must still be listed.
        # Shipping below zero is rejected (409), so drive the level negative
        # with an absolute adjust instead.
        item = _make_item(client, "SKU-1")
        _receive(client, item["id"], loc_a["id"], 2)
        r = client.post(
            "/movements",
            json={
                "item_id": item["id"],
                "kind": "adjust",
                "qty": -3,
                "to_location_id": loc_a["id"],
            },
        )
        assert r.status_code == 201, r.text

        r = client.get(f"/locations/{loc_a['id']}/stock")
        assert r.status_code == 200, r.text
        assert r.json()["levels"] == [
            {"item_id": item["id"], "location_id": loc_a["id"], "qty": -3}
        ]

    def test_only_levels_for_this_location(self, client, loc_a, loc_b):
        item = _make_item(client, "SKU-1")
        _receive(client, item["id"], loc_a["id"], 5)
        _receive(client, item["id"], loc_b["id"], 2)

        r = client.get(f"/locations/{loc_b['id']}/stock")
        assert r.status_code == 200, r.text
        assert r.json() == {
            "location_id": loc_b["id"],
            "levels": [{"item_id": item["id"], "location_id": loc_b["id"], "qty": 2}],
        }

    def test_unknown_location_returns_404(self, client):
        r = client.get("/locations/9999/stock")
        assert r.status_code == 404
