import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.map_yahoo_static import (
    apply_yahoo_static_flags,
    map_yahoo_static,
    refresh_yahoo_static_cache,
    static_record,
)


class StaticRecordTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_static.yf.Ticker")
    def test_returns_profile_when_description_exists(self, mock_ticker):
        fund = mock_ticker.return_value.funds_data
        fund.description = "  A growth fund.  "
        fund.fund_overview = {"categoryName": "Large Growth", "family": "Acme"}
        fund.quote_type.return_value = "MUTUALFUND"

        record = static_record("AAA")

        self.assertEqual(record["symbol"], "AAA")
        self.assertEqual(record["description"], "A growth fund.")
        self.assertEqual(record["category_name"], "Large Growth")

    @patch("helpers.funds_functions.map_yahoo_static.yf.Ticker")
    def test_returns_none_without_description(self, mock_ticker):
        mock_ticker.return_value.funds_data.description = "   "
        self.assertIsNone(static_record("AAA"))


class RefreshYahooStaticCacheTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_static.time.sleep")
    @patch("helpers.funds_functions.map_yahoo_static._fetch_with_retries")
    def test_persists_records(self, mock_fetch, _mock_sleep):
        mock_fetch.side_effect = [
            ({"symbol": "AAA", "description": "Fund A"}, True),
            (None, True),
        ]

        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-yahoo.json"
            cache = refresh_yahoo_static_cache(["AAA", "BBB"], cache_path=cache_file)

            self.assertEqual(cache["AAA"]["description"], "Fund A")
            self.assertIsNone(cache["BBB"])
            self.assertTrue(cache["_nulls_are_final"])
            saved = json.loads(cache_file.read_text())
            self.assertEqual(saved["AAA"]["description"], "Fund A")


class MapYahooStaticTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_static.refresh_yahoo_static_cache")
    def test_sets_is_yahoo_static(self, mock_refresh):
        mock_refresh.return_value = {
            "AAA": {"description": "yes"},
            "BBB": None,
            "_nulls_are_final": True,
        }
        funds = pd.DataFrame({"market_identifier": ["AAA", "BBB"]})
        enriched = map_yahoo_static(funds, cache_path=Path("/unused"))
        self.assertEqual(enriched["is_yahoo_static"].tolist(), [True, False])
