import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions import map_edgar_tickers as mod
from helpers.funds_functions.map_edgar_tickers import map_edgar_tickers


class EdgarTickersCacheTests(unittest.TestCase):
    def test_load_all_mutual_fund_tickers_uses_cache(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-edgar-tickers.json"
            rows = [
                {"cik": 123, "seriesId": "S1", "classId": "C1", "ticker": "AAA"},
                {"cik": 456, "seriesId": "S2", "classId": "C2", "ticker": "BBB"},
            ]
            cache_file.write_text(json.dumps({"records": rows}) + "\n")

            with patch.object(mod, "get_mutual_fund_tickers") as fetch:
                df = mod.load_all_mutual_fund_tickers(cache_file)
                fetch.assert_not_called()

            self.assertEqual(len(df), 2)
            self.assertEqual(set(df["ticker"]), {"AAA", "BBB"})

    def test_save_and_reload_roundtrip(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-edgar-tickers.json"
            source = pd.DataFrame(
                [
                    {
                        "cik": 102909,
                        "seriesId": "S000002277",
                        "classId": "C000006293",
                        "ticker": "VFIAX",
                    },
                ]
            )
            mod.save_edgar_tickers_cache(source, cache_file)
            loaded = mod.load_edgar_tickers_cache(cache_file)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.iloc[0]["ticker"], "VFIAX")

    def test_load_all_fund_reference_data_uses_cache(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-edgar-fund-data.json"
            rows = [
                {
                    "cik": "0000102909",
                    "company_name": "Vanguard",
                    "series_id": "S000002277",
                    "series_name": "500 Index Fund",
                    "class_id": "C000006293",
                    "class_name": "Admiral Shares",
                    "ticker": "VFIAX",
                },
            ]
            mod.save_edgar_fund_data_cache(pd.DataFrame(rows), cache_file)

            with patch.object(mod, "get_fund_reference_data") as fetch:
                df = mod.load_all_fund_reference_data(cache_file)
                fetch.assert_not_called()

            self.assertEqual(len(df), 1)

    def test_map_edgar_tickers_matches_market_identifier(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-edgar-fund-data.json"
            mod.save_edgar_fund_data_cache(
                pd.DataFrame(
                    [
                        {
                            "cik": "0000102909",
                            "company_name": "Vanguard",
                            "entity_org_type": "Trust",
                            "file_number": "811-05141",
                            "series_id": "S000002277",
                            "series_name": "500 Index Fund",
                            "class_id": "C000006293",
                            "class_name": "Admiral Shares",
                            "ticker": "VFIAX",
                        },
                    ]
                ),
                cache_file,
            )
            funds = pd.DataFrame({"market_identifier": ["VFIAX", "UNKNOWN"]})
            out = map_edgar_tickers(funds, cache_file)
            self.assertTrue(out.loc[0, "is_edgartools"])
            self.assertEqual(out.loc[0, "edgartools_cik"], "0000102909")
            self.assertEqual(out.loc[0, "edgartools_series_id"], "S000002277")
            self.assertEqual(out.loc[0, "edgar_series_name"], "500 Index Fund")
            self.assertFalse(out.loc[1, "is_edgartools"])

    def test_name_match_when_sec_ticker_is_blank(self):
        reference = pd.DataFrame(
            [
                {
                    "cik": "0000893818",
                    "company_name": "BlackRock Funds III",
                    "series_id": "S000004272",
                    "series_name": "iShares S&amp;P 500 Index Fund",
                    "class_id": "C000011979",
                    "class_name": "Class K Shares",
                    "ticker": "WFSPX",
                },
                {
                    "cik": "0000893818",
                    "company_name": "BlackRock Funds III",
                    "series_id": "S000004272",
                    "series_name": "iShares S&amp;P 500 Index Fund",
                    "class_id": "C000117728",
                    "class_name": "Service Shares",
                    "ticker": None,
                },
                {
                    "cik": "0000893818",
                    "company_name": "BlackRock Funds III",
                    "series_id": "S000004272",
                    "series_name": "iShares S&amp;P 500 Index Fund",
                    "class_id": "C000212062",
                    "class_name": "Class G Shares",
                    "ticker": None,
                },
                {
                    "cik": "0000893818",
                    "company_name": "BlackRock Funds III",
                    "series_id": "S000004272",
                    "series_name": "iShares S&amp;P 500 Index Fund",
                    "class_id": "C000201951",
                    "class_name": "Investor P Shares",
                    "ticker": None,
                },
            ]
        )
        funds = pd.DataFrame(
            {
                "Name": [
                    "iShares S&P 500 Index Fund;Service",
                    "iShares S&P 500 Index Fund;G",
                    "iShares S&P 500 Index Fund;InvP",
                    "iShares S&P 500 Index Fund;K",
                ],
                "market_identifier": ["BSPSX", "BSPGX", "BSPPX", "WFSPX"],
            }
        )
        out = map_edgar_tickers(funds, fund_reference=reference)
        self.assertEqual(out.loc[0, "edgartools_series_id"], "S000004272")
        self.assertEqual(out.loc[0, "edgartools_class_id"], "C000117728")
        self.assertEqual(out.loc[0, "edgartools_cik"], "0000893818")
        self.assertEqual(out.loc[1, "edgartools_class_id"], "C000212062")
        self.assertEqual(out.loc[2, "edgartools_class_id"], "C000201951")
        self.assertEqual(out.loc[3, "edgartools_class_id"], "C000011979")
        self.assertTrue(out["is_edgartools"].all())

    def test_name_match_when_no_ticker_hits_in_frame(self):
        reference = pd.DataFrame(
            [
                {
                    "cik": "0000893818",
                    "company_name": "BlackRock Funds III",
                    "series_id": "S000004272",
                    "series_name": "iShares S&amp;P 500 Index Fund",
                    "class_id": "C000117728",
                    "class_name": "Service Shares",
                    "ticker": None,
                },
            ]
        )
        funds = pd.DataFrame(
            {
                "Name": ["iShares S&P 500 Index Fund;Service"],
                "market_identifier": ["BSPSX"],
            }
        )
        out = map_edgar_tickers(funds, fund_reference=reference)
        self.assertEqual(out.loc[0, "edgartools_series_id"], "S000004272")
        self.assertEqual(out.loc[0, "edgar_company_name"], "BlackRock Funds III")

    def test_name_match_skipped_when_ambiguous(self):
        reference = pd.DataFrame(
            [
                {
                    "cik": "0000000001",
                    "company_name": "Trust A",
                    "series_id": "S1",
                    "series_name": "Growth Fund",
                    "class_id": "C1",
                    "class_name": "Service Shares",
                    "ticker": None,
                },
                {
                    "cik": "0000000002",
                    "company_name": "Trust B",
                    "series_id": "S2",
                    "series_name": "Growth Fund",
                    "class_id": "C2",
                    "class_name": "Service Shares",
                    "ticker": None,
                },
            ]
        )
        funds = pd.DataFrame(
            {"Name": ["Growth Fund;Service"], "market_identifier": ["XXXX"]}
        )
        out = map_edgar_tickers(funds, fund_reference=reference)
        self.assertFalse(out.loc[0, "is_edgartools"])


if __name__ == "__main__":
    unittest.main()
