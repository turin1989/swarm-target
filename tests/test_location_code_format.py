"""Tests for T034: location code format validation."""

import pytest


@pytest.mark.parametrize(
    "code",
    [
        "WH-A",
        "WH-B",
        "A",
        "0",
        "A1-B2-C3",
        "WAREHOUSE-1",
        "X" * 32,
        "A" + "-" * 31,
    ],
)
def test_valid_location_codes_accepted(client, code):
    r = client.post("/locations", json={"code": code, "name": f"Loc {code}"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == code


@pytest.mark.parametrize(
    "code",
    [
        "",  # empty
        "-A",  # cannot start with hyphen
        "wh-a",  # lowercase not allowed
        "WH A",  # spaces not allowed
        "WH_A",  # underscores not allowed
        "WH.A",  # dots not allowed
        " WH-A",  # leading space
        "WH-A ",  # trailing space
        "Wh-A",  # mixed case
        "X" * 33,  # too long (33 chars)
        "WH-Ä",  # non-ASCII letter
    ],
)
def test_invalid_location_codes_rejected_with_422(client, code):
    r = client.post("/locations", json={"code": code, "name": "Bad"})
    assert r.status_code == 422, r.text


def test_existing_code_wh_a_remains_valid(client, loc_a):
    assert loc_a["code"] == "WH-A"
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["code"] == "WH-A"
