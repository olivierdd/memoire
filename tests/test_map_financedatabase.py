import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.map_financedatabase import (
    apply_financedatabase_static_flags,
    fetch_fmp_static,
    fmp_was_fetched,
    probe_fmp_price_range,
    refresh_fmp_cache,
)


class FmpWasFetchedTests(unittest.TestCase):
    def test_true_when_prices_block_present(self):
        row = {"name": "Fund", "fmp": {"prices": {"available": False}}}
        self.assertTrue(fmp_was_fetched(row))

    def test_false_when_fmp_missing(self):
        self.assertFalse(fmp_was_fetched({"name": "Fund"}))
        self.assertFalse(fmp_was_fetched(None))


class ProbeFmpPriceRangeTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_financedatabase.fmp_get")
    def test_finds_start_and_end_from_year_probes(self, mock_get):
        def fake_get(path, params, api_key):
            from_date = params.get("from", "")
            to_date = params.get("to", "")
            if to_date == date.today().isoformat():
                return [{"date": "2026-10-20"}, {"date": "2026-10-21"}]
            if from_date.endswith("-01-01") and to_date.endswith("-12-31"):
                year = int(from_date[:4])
                if year < 2002:
                    return []
                if year == 2002:
                    return [{"date": "2002-03-15"}, {"date": "2002-06-01"}]
                return [{"date": f"{year}-06-01"}]
            return []

        mock_get.side_effect = fake_get
        bounds = probe_fmp_price_range("CICAX", "key")
        self.assertEqual(
            bounds,
            {"available": True, "start": "2002-03-15", "end": "2026-10-21"},
        )
        self.assertTrue(mock_get.called)

    @patch("helpers.funds_functions.map_financedatabase.fmp_get", return_value=[])
    def test_unavailable_when_recent_window_empty(self, _mock_get):
        self.assertEqual(
            probe_fmp_price_range("MISSING", "key"),
            {"available": False, "start": None, "end": None},
        )


class FetchFmpStaticTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_financedatabase.probe_fmp_price_range")
    @patch("helpers.funds_functions.map_financedatabase.fmp_get")
    def test_collects_static_blocks_and_skips_price_probe_when_unlisted(
        self, mock_get, mock_probe
    ):
        def fake_get(path, params, api_key):
            if path == "/etf/info":
                return [{"symbol": "SPY", "expenseRatio": 0.09}]
            if path in {"/profile", "/quote"}:
                return []
            return []

        mock_get.side_effect = fake_get
        mock_probe.return_value = {
            "available": True,
            "start": "2000-01-03",
            "end": "2026-10-21",
        }

        payload = fetch_fmp_static("SPY", "key")

        self.assertTrue(payload["listed"])
        self.assertEqual(payload["info"]["symbol"], "SPY")
        self.assertEqual(payload["prices"]["start"], "2000-01-03")
        mock_probe.assert_called_once()

    @patch("helpers.funds_functions.map_financedatabase.probe_fmp_price_range")
    @patch("helpers.funds_functions.map_financedatabase.fmp_get", return_value=[])
    def test_unlisted_funds_do_not_probe_prices(self, _mock_get, mock_probe):
        payload = fetch_fmp_static("CICEX", "key")
        self.assertFalse(payload["listed"])
        self.assertFalse(payload["prices"]["available"])
        mock_probe.assert_not_called()


class RefreshFmpCacheTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_financedatabase.fetch_fmp_static")
    @patch("helpers.funds_functions.map_financedatabase._load_fmp_api_key", return_value="key")
    def test_persists_fmp_payload_on_existing_financedatabase_row(
        self, _mock_key, mock_fetch
    ):
        mock_fetch.return_value = {
            "listed": True,
            "info": {"symbol": "SPY"},
            "profile": None,
            "quote": None,
            "dividends": [],
            "splits": [],
            "prices": {"available": True, "start": "2000-01-03", "end": "2026-10-21"},
        }

        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-financedatabase.json"
            cache = {
                "SPY": {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust"},
                "_nulls_are_final": True,
            }
            cache_file.write_text(json.dumps(cache, indent=2) + "\n")

            refresh_fmp_cache(["SPY"], cache, cache_path=cache_file)

            saved = json.loads(cache_file.read_text())
            self.assertTrue(fmp_was_fetched(saved["SPY"]))
            self.assertEqual(saved["SPY"]["fmp"]["info"]["symbol"], "SPY")
            self.assertTrue(saved["_fmp_are_final"])

    @patch("helpers.funds_functions.map_financedatabase.fetch_fmp_static")
    @patch("helpers.funds_functions.map_financedatabase._load_fmp_api_key", return_value="key")
    def test_upgrades_null_cache_entry_when_financedatabase_miss(
        self, _mock_key, mock_fetch
    ):
        mock_fetch.return_value = {
            "listed": False,
            "info": None,
            "profile": None,
            "quote": None,
            "dividends": [],
            "splits": [],
            "prices": {"available": False, "start": None, "end": None},
        }

        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-financedatabase.json"
            cache = {"CICEX": None, "_nulls_are_final": True}
            refresh_fmp_cache(["CICEX"], cache, cache_path=cache_file)
            self.assertEqual(cache["CICEX"]["symbol"], "CICEX")
            self.assertFalse(cache["CICEX"]["fmp"]["listed"])


class ApplyFinancedatabaseStaticFlagsTests(unittest.TestCase):
    def test_sets_has_fmp_prices_from_cache(self):
        funds = pd.DataFrame({"market_identifier": ["AAA", "BBB"]})
        cache = {
            "AAA": {"name": "A", "fmp": {"prices": {"available": True}}},
            "BBB": {"name": "B", "fmp": {"prices": {"available": False}}},
        }
        enriched = apply_financedatabase_static_flags(funds, cache)
        self.assertEqual(enriched["has_fmp_prices"].tolist(), [True, False])

    def test_has_financedb_timeries_uses_fmp_or_legacy_timeseries(self):
        funds = pd.DataFrame({"market_identifier": ["AAA", "BBB", "CCC"]})
        cache = {
            "AAA": {"fmp": {"prices": {"available": True}}},
            "BBB": {"timeseries": {"start": "2000-01-01", "end": "2020-01-01"}},
            "CCC": {"fmp": {"prices": {"available": False}}},
        }
        enriched = apply_financedatabase_static_flags(funds, cache)
        self.assertEqual(enriched["has_financedb_timeries"].tolist(), [True, True, False])
