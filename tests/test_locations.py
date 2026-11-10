import pytest


class TestLocationCodeValidation:
    @pytest.mark.parametrize(
        "code",
        ["WH-A", "WH-B", "A", "0", "A1-B2-C3", "X" * 32, "9-", "WAREHOUSE-MAIN-01"],
    )
    def test_valid_codes_accepted(self, client, code):
        r = client.post("/locations", json={"code": code, "name": f"Loc {code}"})
        assert r.status_code == 201, r.text
        assert r.json()["code"] == code

    @pytest.mark.parametrize(
        "code",
        [
            "",            # empty
            "-WH",         # cannot start with hyphen
            "wh-a",        # lowercase not allowed
            "WH A",        # spaces not allowed
            "WH_A",        # underscore not allowed
            "WH.A",        # dot not allowed
            " WH-A",       # leading space
            "X" * 33,      # too long
            "É1",          # non-ASCII
        ],
    )
    def test_invalid_codes_rejected_with_422(self, client, code):
        r = client.post("/locations", json={"code": code, "name": "Bad Loc"})
        assert r.status_code == 422, r.text

    def test_existing_style_code_wh_a_remains_valid(self, loc_a):
        assert loc_a["code"] == "WH-A"
