import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.map_yahoo_timeseries import (
    apply_yahoo_timeseries_flags,
    map_yahoo_timeseries,
    refresh_yahoo_timeseries_cache,
    series_bounds,
    store_timeseries,
    timeseries_was_checked,
)


class TimeseriesHelpersTests(unittest.TestCase):
    def test_timeseries_was_checked(self):
        self.assertTrue(timeseries_was_checked({"timeseries": None}))
        self.assertFalse(timeseries_was_checked({"description": "x"}))

    def test_store_timeseries_keeps_static_profile(self):
        cache = {"AAA": {"description": "Fund"}}
        store_timeseries(cache, "AAA", {"start": "2020-01-01", "end": "2024-01-01"})
        self.assertEqual(cache["AAA"]["description"], "Fund")
        self.assertEqual(cache["AAA"]["timeseries"]["start"], "2020-01-01")


class SeriesBoundsTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_timeseries.yf.Ticker")
    def test_returns_start_and_end(self, mock_ticker):
        history = pd.DataFrame(
            {"Close": [1.0, 2.0]},
            index=pd.to_datetime(["2020-01-02", "2024-06-01"]),
        )
        mock_ticker.return_value.history.return_value = history

        bounds = series_bounds("AAA")

        self.assertEqual(bounds["start"], "2020-01-02")
        self.assertEqual(bounds["end"], "2024-06-01")
        self.assertEqual(bounds["source"], "Yahoo")


class RefreshYahooTimeseriesCacheTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_timeseries.time.sleep")
    @patch("helpers.funds_functions.map_yahoo_timeseries._fetch_timeseries_with_retries")
    def test_persists_bounds(self, mock_fetch, _mock_sleep):
        mock_fetch.side_effect = [
            ({"start": "2020-01-01", "end": "2024-01-01", "source": "Yahoo"}, True),
            (None, True),
        ]

        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-yahoo.json"
            cache = refresh_yahoo_timeseries_cache(["AAA", "BBB"], cache_path=cache_file)

            self.assertEqual(cache["AAA"]["timeseries"]["start"], "2020-01-01")
            self.assertIsNone(cache["BBB"]["timeseries"])
            self.assertTrue(cache["_timeseries_are_final"])
            saved = json.loads(cache_file.read_text())
            self.assertIn("timeseries", saved["AAA"])


class MapYahooTimeseriesTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_timeseries.refresh_yahoo_timeseries_cache")
    def test_sets_is_yahoo_timeseries(self, mock_refresh):
        mock_refresh.return_value = {
            "AAA": {"timeseries": {"start": "2020-01-01"}},
            "BBB": {"timeseries": None},
            "_timeseries_are_final": True,
        }
        funds = pd.DataFrame({"market_identifier": ["AAA", "BBB"]})
        enriched = map_yahoo_timeseries(funds, cache_path=Path("/unused"))
        self.assertEqual(enriched["is_yahoo_timeseries"].tolist(), [True, False])
