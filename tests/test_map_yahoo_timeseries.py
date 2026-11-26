import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.map_yahoo_timeseries import (
    append_yahoo_price_and_tr_columns,
    apply_yahoo_timeseries_flags,
    fetch_yahoo_price_levels,
    fetch_yahoo_total_return_levels,
    holiday_mask_from_daily_sheet,
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


class FetchYahooTotalReturnLevelsTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_timeseries.yf.Ticker")
    def test_uses_auto_adjust_true(self, mock_ticker):
        history = pd.DataFrame(
            {"Close": [100.0, 101.0, 102.5]},
            index=pd.to_datetime(
                ["2020-01-02", "2020-01-03", "2020-01-06"], utc=True
            ),
        )
        mock_ticker.return_value.history.return_value = history

        levels = fetch_yahoo_total_return_levels("FRDPX")

        mock_ticker.return_value.history.assert_called_once_with(
            period="max", auto_adjust=True, repair=False
        )
        self.assertIsNotNone(levels)
        assert levels is not None
        self.assertEqual(levels.name, "FRDPX")
        self.assertEqual(list(levels.values), [100.0, 101.0, 102.5])
        self.assertIsNone(levels.index.tz)
        self.assertEqual(levels.index[0], pd.Timestamp("2020-01-02"))

    @patch("helpers.funds_functions.map_yahoo_timeseries.yf.Ticker")
    def test_returns_none_when_empty(self, mock_ticker):
        mock_ticker.return_value.history.return_value = pd.DataFrame()
        self.assertIsNone(fetch_yahoo_total_return_levels("ZZZZ"))


class FetchYahooPriceLevelsTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_timeseries.yf.Ticker")
    def test_uses_auto_adjust_false(self, mock_ticker):
        history = pd.DataFrame(
            {"Close": [50.0, 51.0]},
            index=pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True),
        )
        mock_ticker.return_value.history.return_value = history
        levels = fetch_yahoo_price_levels("FRDPX")
        mock_ticker.return_value.history.assert_called_once_with(
            period="max", auto_adjust=False, repair=False
        )
        self.assertEqual(list(levels.values), [50.0, 51.0])


class AppendYahooPriceAndTrColumnTests(unittest.TestCase):
    def _sample_daily(self) -> pd.DataFrame:
        # Rows 0–5 labels; row 6+ observations (Datastream layout).
        rows = [
            ["ISIN", "US0000000001", "INDEX"],
            ["Name", "Existing Fund - TOT RETURN IND", "S&P 500 COMPOSITE - TOT RETURN IND"],
            ["Category", "Active MF", "Index"],
            ["Fee", 0.5, None],
            ["Type", "Total return index, daily", "Total return index, daily"],
            ["Code", "EXISTING", "S&P 500 TR"],
            [pd.Timestamp("2020-01-02"), 10.0, 100.0],
            [pd.Timestamp("2020-01-03"), 10.5, 100.0],  # S&P-flat holiday
            [pd.Timestamp("2020-01-06"), 11.0, 101.0],
            [pd.Timestamp("2020-01-07"), 11.2, 102.0],
        ]
        return pd.DataFrame(rows)

    def test_appends_price_and_tr_pairs_with_primary_headers(self):
        daily = self._sample_daily()
        tr_levels = pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
            name="FRDPX",
        )
        price_levels = pd.Series(
            [50.0, 55.0, 60.5],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
            name="FRDPX",
        )
        holiday_mask = holiday_mask_from_daily_sheet(daily)

        out, observations = append_yahoo_price_and_tr_columns(
            daily,
            isin="US3546131018",
            ticker="FRDPX",
            fund_name="Franklin Rising Dividends;A",
            tr_levels=tr_levels,
            price_levels=price_levels,
            category="Active MF",
            fee=0.82,
            holiday_mask=holiday_mask,
        )

        self.assertEqual(observations, 3)
        self.assertEqual(out.shape[1], 7)  # date + existing + SPX + 4 Yahoo
        price_col = out.iloc[:, 3]
        price_ret = out.iloc[:, 4]
        tr_col = out.iloc[:, 5]
        tr_ret = out.iloc[:, 6]
        self.assertEqual(price_col.iloc[0], "US3546131018")
        self.assertEqual(price_col.iloc[3], 0.82)
        self.assertEqual(tr_col.iloc[3], 0.82)
        self.assertEqual(price_col.iloc[5], "US3546131018 Price")
        self.assertEqual(price_ret.iloc[5], "US3546131018 Price %")
        self.assertEqual(tr_col.iloc[5], "US3546131018 TR")
        self.assertEqual(tr_ret.iloc[5], "US3546131018 TR %")
        self.assertEqual(
            tr_col.iloc[1], "Franklin Rising Dividends;A - TOT RETURN IND"
        )
        self.assertAlmostEqual(float(tr_col.iloc[6]), 100.0)
        self.assertTrue(pd.isna(tr_col.iloc[7]))
        self.assertAlmostEqual(float(tr_col.iloc[8]), 121.0)
        self.assertTrue(pd.isna(tr_col.iloc[9]))
        self.assertAlmostEqual(float(price_col.iloc[6]), 50.0)
        self.assertTrue(pd.isna(price_ret.iloc[7]))
        self.assertAlmostEqual(float(price_ret.iloc[8]), 0.21)
        self.assertTrue(pd.isna(tr_ret.iloc[7]))
        self.assertAlmostEqual(float(tr_ret.iloc[8]), 0.21)

    def test_holiday_na_leaves_blank_session_and_recomputes_next_return(self):
        daily = self._sample_daily()
        # Yahoo missing on the S&P-flat holiday (2020-01-03).
        tr_levels = pd.Series(
            [100.0, 110.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-06"]),
            name="FRDPX",
        )
        price_levels = pd.Series(
            [50.0, 55.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-06"]),
            name="FRDPX",
        )
        holiday_mask = holiday_mask_from_daily_sheet(daily)
        self.assertTrue(bool(holiday_mask.iloc[1]))

        out, observations = append_yahoo_price_and_tr_columns(
            daily,
            isin="US3546131018",
            ticker="FRDPX",
            fund_name="Franklin Rising Dividends;A",
            tr_levels=tr_levels,
            price_levels=price_levels,
            holiday_mask=holiday_mask,
        )

        self.assertEqual(observations, 2)
        tr_col = out.iloc[:, 5]
        tr_ret = out.iloc[:, 6]
        self.assertAlmostEqual(float(tr_col.iloc[6]), 100.0)
        self.assertTrue(pd.isna(tr_col.iloc[7]))
        self.assertAlmostEqual(float(tr_col.iloc[8]), 110.0)
        self.assertTrue(pd.isna(tr_ret.iloc[7]))
        self.assertAlmostEqual(float(tr_ret.iloc[8]), 0.1)

    def test_returns_zero_observations_when_no_date_overlap(self):
        daily = self._sample_daily()
        levels = pd.Series(
            [100.0],
            index=pd.to_datetime(["2019-01-02"]),
            name="FRDPX",
        )
        out, observations = append_yahoo_price_and_tr_columns(
            daily,
            isin="US3546131018",
            ticker="FRDPX",
            fund_name="Franklin Rising Dividends;A",
            tr_levels=levels,
            price_levels=levels,
        )
        self.assertEqual(observations, 0)
        self.assertEqual(out.shape[1], daily.shape[1])
