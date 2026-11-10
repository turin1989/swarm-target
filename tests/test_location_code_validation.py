import pytest

VALID_CODES = ["WH-A", "A", "0", "WH-B-2", "A" * 32, "A" + "-" * 31]
INVALID_CODES = ["", "-A", "wh-a", "WH_A", "WH A", " WH-A", "A" * 33, "WHÄ"]


@pytest.mark.parametrize("code", VALID_CODES)
def test_valid_location_codes_accepted(client, code):
    r = client.post("/locations", json={"code": code, "name": "Loc"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == code


@pytest.mark.parametrize("code", INVALID_CODES)
def test_invalid_location_codes_rejected_with_422(client, code):
    r = client.post("/locations", json={"code": code, "name": "Loc"})
    assert r.status_code == 422, r.text


def test_existing_code_wh_a_remains_valid(client, loc_a):
    assert loc_a["code"] == "WH-A"
