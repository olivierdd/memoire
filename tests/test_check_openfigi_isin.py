import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.check_openfigi_isin import (
    apply_isin_checks,
    check_openfigi_isins,
    names_match,
    record_from_job,
)


class NamesMatchTests(unittest.TestCase):
    def test_accepts_openfigi_abbreviations(self):
        self.assertTrue(names_match("Auxier Focus Fund;Investor", "AUXIER FOCUS FUND-INV"))
        self.assertTrue(
            names_match(
                "DFA US Large Company Portfolio;Inst",
                "DFA US LRG COMP PORT-INST",
            )
        )

    def test_accepts_a_shortened_sponsor_name(self):
        self.assertTrue(
            names_match(
                "JPMorgan U.S. Equity Mutual Fund Class L",
                "JPMORGAN US EQUITY-L",
            )
        )
        self.assertTrue(names_match("GoodHaven Fund", "GOODHAVEN FUND"))
        self.assertTrue(names_match("Thompson LargeCap Fund", "THOMPSON LARGECAP FUND"))
        self.assertTrue(
            names_match("iShares S&P 500 Index Fund;Service", "ISHARES S&P 500 INDEX-SRV")
        )
        self.assertTrue(
            names_match(
                "Fundamental Investors Mutual Fund Class F 1",
                "AMER FND FNDMNTL INVST-F1",
            )
        )

    def test_rejects_a_different_fund(self):
        self.assertFalse(
            names_match("Auxier Focus Fund;Investor", "VANGUARD INST INDEX-INST")
        )
        self.assertFalse(
            names_match(
                "Value Line Select Core Mutual Fund Investor Class",
                "VALUE LINE SELECT GROWTH-INV",
            )
        )


class RecordFromJobTests(unittest.TestCase):
    def test_keeps_us_listing_name(self):
        job = {
            "data": [
                {"ticker": "AUXFX", "name": "OTHER", "exchCode": "LN", "figi": "BBG1"},
                {
                    "ticker": "AUXFX",
                    "name": "AUXIER FOCUS FUND-INV",
                    "exchCode": "US",
                    "figi": "BBG000HJ2211",
                },
            ]
        }
        self.assertEqual(record_from_job(job)["name"], "AUXIER FOCUS FUND-INV")

    def test_unknown_isin_has_no_record(self):
        self.assertIsNone(record_from_job({"warning": "No identifier found."}))


class ApplyIsinChecksTests(unittest.TestCase):
    def test_compares_name_and_cusip_ticker(self):
        funds = pd.DataFrame(
            {
                "Name": ["Auxier Focus Fund;Investor", "Other Fund"],
                "CUSIP": ["349903179", "111111111"],
                "ISIN": ["US3499031793", "US1111111111"],
                "openfigi_market_id": ["AUXFX", "OTHER"],
                "openfigi_name": ["AUXIER FOCUS FUND-INV", "OTHER FUND"],
                "openfigi_cusip_ok": [True, True],
            }
        )
        cache = {
            "US3499031793": {
                "ticker": "AUXFX",
                "name": "AUXIER FOCUS FUND-INV",
                "figi": "BBG000HJ2211",
            },
            "US1111111111": {
                "ticker": "ZZZ",
                "name": "ZZZ FUND",
                "cusip": "999999999",
            },
        }

        cusip_cache = {
            "349903179": {
                "ticker": "AUXFX",
                "name": "AUXIER FOCUS FUND-INV",
                "figi": "BBG000HJ2211",
            },
            "111111111": {"ticker": "NOPE", "name": "NOPE FUND", "figi": "BBGNOPE"},
        }
        output = io.StringIO()
        with redirect_stdout(output):
            checked = apply_isin_checks(funds, cache, cusip_cache)

        self.assertEqual(
            list(checked.columns[-3:]),
            ["isin_found", "name_matches", "cusip_matches"],
        )
        self.assertEqual(checked["openfigi_market_id"].tolist(), ["AUXFX", "ZZZ"])
        self.assertEqual(
            checked["openfigi_name"].tolist(),
            ["AUXIER FOCUS FUND-INV", "ZZZ FUND"],
        )
        self.assertEqual(checked["isin_found"].tolist(), [True, True])
        self.assertEqual(checked["name_matches"].tolist(), [True, False])
        self.assertEqual(checked["cusip_matches"].tolist(), [True, False])
        alert = output.getvalue()
        self.assertIn("ISIN openfigi_market_id for Other Fund", alert)
        self.assertIn("OTHER -> ZZZ", alert)
        self.assertIn("ISIN openfigi_name for Other Fund", alert)
        self.assertNotIn("Auxier Focus Fund;Investor", alert)

    def test_missing_isin_is_not_a_match(self):
        funds = pd.DataFrame(
            {"Name": ["Missing"], "CUSIP": ["349903179"], "ISIN": ["US0000000000"]}
        )
        checked = apply_isin_checks(funds, {"US0000000000": None})
        self.assertEqual(checked["isin_found"].tolist(), [False])
        self.assertEqual(checked["name_matches"].tolist(), [False])
        self.assertEqual(checked["cusip_matches"].tolist(), [False])

    def test_cusip_matches_when_the_cusip_lookup_returns_the_same_listing(self):
        funds = pd.DataFrame(
            {
                "Name": ["Same", "Different", "Missing ISIN", "Missing CUSIP"],
                "CUSIP": ["349903179", "111111111", "349903179", None],
                "ISIN": ["US3499031793", "US1111111111", "US0000000000", "US3499031793"],
            }
        )
        cache = {
            "US3499031793": {"ticker": "AUXFX", "name": "AUXIER FOCUS FUND-INV", "figi": "BBG1"},
            "US1111111111": {"ticker": "ZZZ", "name": "ZZZ FUND", "figi": "BBG2"},
            "US0000000000": None,
        }
        cusip_cache = {
            "349903179": {"ticker": "AUXFX", "name": "AUXIER FOCUS FUND-INV", "figi": "BBG1"},
            "111111111": {"ticker": "OTHER", "name": "OTHER FUND", "figi": "BBG9"},
        }

        checked = apply_isin_checks(funds, cache, cusip_cache)

        self.assertEqual(checked["cusip_matches"].tolist(), [True, False, False, False])


class CheckOpenfigiIsinsTests(unittest.TestCase):
    def test_requests_id_isin_and_uses_cache(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "records.json"
            cusip_cache_file = Path(tmp) / "cusips.json"
            cusip_cache_file.write_text(
                json.dumps(
                    {
                        "349903179": {
                            "ticker": "AUXFX",
                            "name": "AUXIER FOCUS FUND-INV",
                            "figi": "BBG000HJ2211",
                        },
                        "_nulls_are_final": True,
                    }
                )
                + "\n"
            )
            cache_file.write_text(
                json.dumps(
                    {
                        "US3499031793": {
                            "ticker": "AUXFX",
                            "name": "AUXIER FOCUS FUND-INV",
                            "figi": "BBG000HJ2211",
                        },
                        "_nulls_are_final": True,
                    }
                )
                + "\n"
            )
            funds = pd.DataFrame(
                {
                    "Name": ["Auxier Focus Fund;Investor", "Unknown"],
                    "CUSIP": ["349903179", None],
                    "ISIN": ["US3499031793", "US0000000000"],
                    "openfigi_market_id": ["AUXFX", None],
                }
            )
            with patch(
                "helpers.funds_functions.check_openfigi_isin.post_mapping",
                return_value=[{"warning": "No identifier found."}],
            ) as post:
                checked = check_openfigi_isins(
                    funds,
                    cache_path=cache_file,
                    cusip_cache_path=cusip_cache_file,
                    pause_seconds=0,
                )

            post.assert_called_once_with(["US0000000000"], "ID_ISIN")
            self.assertEqual(checked["isin_found"].tolist(), [True, False])
            self.assertEqual(checked["cusip_matches"].tolist(), [True, False])


if __name__ == "__main__":
    unittest.main()
