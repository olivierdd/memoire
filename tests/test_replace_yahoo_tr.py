import unittest
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.map_yahoo_timeseries import (
    fetch_yahoo_price_levels,
    fetch_yahoo_total_return_levels,
    levels_and_returns_with_holiday_na,
    spx_flat_holiday_mask,
)
from helpers.timeseries_functions.replace_yahoo_tr import (
    YAHOO_TR_REPLACEMENTS,
    YAHOO_TR_REPLACE_ISINS,
    align_yahoo_levels_to_index,
    lipper_fund_sample_end,
    replace_datastream_tr_with_yahoo,
    truncate_panel_to_sample_end,
)
from helpers.timeseries_functions.yahoo_tr_freeze import (
    fetch_yahoo_total_return_levels_prefer_freeze,
    freeze_yahoo_tr_replacements,
    load_frozen_yahoo_price_levels,
    load_frozen_yahoo_total_return_levels,
    yahoo_tr_freeze_download_date,
)
from helpers.timeseries_functions.series_v2_pipeline import (
    rescale_level_breaks,
    summarize_tr_consistency,
)


class YahooTrReplacementMapTests(unittest.TestCase):
    def test_seven_funds_only_excludes_cfimx(self):
        self.assertEqual(len(YAHOO_TR_REPLACEMENTS), 7)
        self.assertNotIn("US1888501012", YAHOO_TR_REPLACE_ISINS)
        self.assertEqual(YAHOO_TR_REPLACEMENTS["US8085098551"], "SWPPX")
        self.assertEqual(YAHOO_TR_REPLACEMENTS["US2562191062"], "DODGX")


class AlignYahooLevelsTests(unittest.TestCase):
    def test_aligns_and_leaves_missing_blank(self):
        levels = pd.Series(
            [100.0, 110.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
        )
        dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
        aligned = align_yahoo_levels_to_index(levels, dates)
        self.assertAlmostEqual(float(aligned.iloc[0]), 100.0)
        self.assertAlmostEqual(float(aligned.iloc[1]), 110.0)
        self.assertTrue(pd.isna(aligned.iloc[2]))


class FetchYahooPriceLevelsTests(unittest.TestCase):
    @patch("helpers.funds_functions.map_yahoo_timeseries.yf.Ticker")
    def test_price_uses_auto_adjust_false(self, mock_ticker):
        history = pd.DataFrame(
            {"Close": [50.0, 51.0]},
            index=pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True),
        )
        mock_ticker.return_value.history.return_value = history
        levels = fetch_yahoo_price_levels("SWPPX")
        mock_ticker.return_value.history.assert_called_once_with(
            period="max", auto_adjust=False, repair=False
        )
        self.assertEqual(list(levels.values), [50.0, 51.0])

    @patch("helpers.funds_functions.map_yahoo_timeseries.yf.Ticker")
    def test_tr_uses_auto_adjust_true(self, mock_ticker):
        history = pd.DataFrame(
            {"Close": [100.0, 110.0]},
            index=pd.to_datetime(["2020-01-02", "2020-01-03"], utc=True),
        )
        mock_ticker.return_value.history.return_value = history
        levels = fetch_yahoo_total_return_levels("SWPPX")
        mock_ticker.return_value.history.assert_called_once_with(
            period="max", auto_adjust=True, repair=False
        )
        self.assertEqual(list(levels.values), [100.0, 110.0])


class YahooTrFreezeTests(unittest.TestCase):
    def test_freeze_roundtrip_and_prefer_freeze_over_live(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        tr_levels = pd.Series(
            [100.0, 110.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
            name="SWPPX",
        )
        price_levels = pd.Series(
            [50.0, 55.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
            name="SWPPX",
        )
        with tempfile.TemporaryDirectory() as tmp:
            freeze_dir = Path(tmp)
            manifest = freeze_yahoo_tr_replacements(
                freeze_dir=freeze_dir,
                replacements={"US8085098551": "SWPPX"},
                download_date="2026-11-24",
                fetch_tr_levels=lambda _t: tr_levels,
                fetch_price_levels=lambda _t: price_levels,
            )
            self.assertEqual(manifest["download_date"], "2026-11-24")
            self.assertEqual(
                yahoo_tr_freeze_download_date(freeze_dir), "2026-11-24"
            )
            loaded_tr = load_frozen_yahoo_total_return_levels(
                "SWPPX", freeze_dir=freeze_dir
            )
            loaded_price = load_frozen_yahoo_price_levels(
                "SWPPX", freeze_dir=freeze_dir
            )
            self.assertEqual(list(loaded_tr.values), [100.0, 110.0])
            self.assertEqual(list(loaded_price.values), [50.0, 55.0])

            with patch(
                "helpers.timeseries_functions.yahoo_tr_freeze.fetch_yahoo_total_return_levels"
            ) as live_tr:
                live_tr.side_effect = AssertionError("live fetch should not run")
                preferred = fetch_yahoo_total_return_levels_prefer_freeze(
                    "SWPPX", freeze_dir=freeze_dir
                )
            self.assertEqual(list(preferred.values), [100.0, 110.0])
            live_tr.assert_not_called()


class TruncatePanelToSampleEndTests(unittest.TestCase):
    def test_uses_modal_lipper_fund_tr_last_date_and_drops_later_rows(self):
        dates = pd.to_datetime(
            ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
        )
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4],
                "id": ["US111", "US222", "S&P", "US00774Q8740"],
                "name": ["A", "B", "S&P", "Yahoo fund"],
                "category": ["Active MF", "Passive MF", "Index", "Active MF"],
                "header": [
                    "US111 TR",
                    "US222 TR",
                    "S&P 500 TR",
                    "US00774Q8740 TR",
                ],
                "source": ["Lipper", "Lipper", "Lipper", "Yahoo"],
                "observations": [2, 2, 4, 4],
                "first_date": [dates[0], dates[0], dates[0], dates[0]],
                "last_date": [dates[1], dates[1], dates[3], dates[3]],
            }
        )
        observations = pd.DataFrame(
            {
                1: [1.0, 1.1, 1.2, 1.3],
                2: [2.0, 2.1, 2.2, 2.3],
                3: [100.0, 101.0, 102.0, 103.0],
                4: [10.0, 11.0, 12.0, 13.0],
            },
            index=pd.Index(dates, name="date"),
        )

        self.assertEqual(
            lipper_fund_sample_end(catalog), pd.Timestamp("2026-10-30")
        )
        out_catalog, out_obs, end = truncate_panel_to_sample_end(
            catalog, observations
        )
        self.assertEqual(end, pd.Timestamp("2026-10-30"))
        self.assertEqual(list(out_obs.index), list(dates[:2]))
        self.assertEqual(int(out_catalog.loc[out_catalog["column"].eq(3), "observations"].iloc[0]), 2)
        self.assertEqual(
            pd.Timestamp(
                out_catalog.loc[out_catalog["column"].eq(3), "last_date"].iloc[0]
            ),
            pd.Timestamp("2026-10-30"),
        )
        # Yahoo-replaced last_date must not set the endpoint.
        self.assertEqual(
            pd.Timestamp(
                out_catalog.loc[out_catalog["column"].eq(4), "last_date"].iloc[0]
            ),
            pd.Timestamp("2026-10-30"),
        )

    def test_noop_when_panel_already_ends_on_sample_end(self):
        dates = pd.to_datetime(["2026-10-29", "2026-10-30"])
        catalog = pd.DataFrame(
            {
                "column": [1],
                "id": ["US111"],
                "name": ["A"],
                "category": ["Active MF"],
                "header": ["US111 TR"],
                "observations": [2],
                "first_date": [dates[0]],
                "last_date": [dates[1]],
            }
        )
        observations = pd.DataFrame(
            {1: [1.0, 1.1]}, index=pd.Index(dates, name="date")
        )
        out_catalog, out_obs, end = truncate_panel_to_sample_end(
            catalog, observations
        )
        self.assertEqual(end, pd.Timestamp("2026-10-30"))
        self.assertEqual(len(out_obs), 2)
        self.assertEqual(int(out_catalog.loc[0, "observations"]), 2)


class ReplaceDatastreamWithYahooTests(unittest.TestCase):
    def _panel(self, *, include_cfimx: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
        dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"])
        observations = pd.DataFrame(
            {
                1: [10.0, 10.5, 20.0, 21.0],
                2: [pd.NA, 0.05, 0.90, 0.05],
                3: [50.0, 51.0, 52.0, 53.0],
                4: [pd.NA, 0.02, 0.02, 0.02],
            },
            index=pd.Index(dates, name="date"),
        )
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4],
                "id": ["US8085098551"] * 4,
                "name": ["Schwab TR", "Schwab TR %", "Schwab Price", "Schwab Price %"],
                "category": ["Index"] * 4,
                "fee": [0.0] * 4,
                "note": [
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Price, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                ],
                "header": [
                    "US8085098551 TR",
                    "US8085098551 TR %",
                    "US8085098551 Price",
                    "US8085098551 Price %",
                ],
                "observations": [4, 3, 4, 3],
                "first_date": [dates[0]] * 4,
                "last_date": [dates[-1]] * 4,
            }
        )
        if include_cfimx:
            observations[5] = [9.0, 9.1, 9.2, 9.3]
            observations[6] = [pd.NA, 0.01, 0.01, 0.01]
            observations[7] = [40.0, 41.0, 42.0, 43.0]
            observations[8] = [pd.NA, 0.025, 0.024, 0.024]
            extra = pd.DataFrame(
                {
                    "column": [5, 6, 7, 8],
                    "id": ["US1888501012"] * 4,
                    "name": ["Clipper TR", "Clipper TR %", "Clipper Price", "Clipper Price %"],
                    "category": ["Index"] * 4,
                    "fee": [0.0] * 4,
                    "note": [
                        "Total return index, daily",
                        "Daily simple return = P(t)/P(t-1) - 1",
                        "Price, daily",
                        "Daily simple return = P(t)/P(t-1) - 1",
                    ],
                    "header": [
                        "US1888501012 TR",
                        "US1888501012 TR %",
                        "US1888501012 Price",
                        "US1888501012 Price %",
                    ],
                    "observations": [4, 3, 4, 3],
                    "first_date": [dates[0]] * 4,
                    "last_date": [dates[-1]] * 4,
                }
            )
            catalog = pd.concat([catalog, extra], ignore_index=True)
        return catalog, observations

    def test_replaces_price_and_tr_from_distinct_yahoo_closes(self):
        catalog, observations = self._panel()
        tr_levels = pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
            name="SWPPX",
        )
        price_levels = pd.Series(
            [50.0, 55.0, 60.5],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
            name="SWPPX",
        )

        out_catalog, out_obs, log = replace_datastream_tr_with_yahoo(
            catalog,
            observations,
            replacements={"US8085098551": "SWPPX"},
            fetch_tr_levels=lambda _t: tr_levels,
            fetch_price_levels=lambda _t: price_levels,
        )

        self.assertEqual(list(log["status"]), ["replaced"])
        self.assertEqual(int(log.loc[0, "tr_days_filled"]), 3)
        self.assertEqual(int(log.loc[0, "price_days_filled"]), 3)
        # TR from adjusted Close
        self.assertAlmostEqual(float(out_obs.loc[observations.index[0], 1]), 100.0)
        self.assertAlmostEqual(float(out_obs.loc[observations.index[1], 1]), 110.0)
        self.assertAlmostEqual(float(out_obs.loc[observations.index[1], 2]), 0.1)
        # Price from split-adjusted Close (different levels)
        self.assertAlmostEqual(float(out_obs.loc[observations.index[0], 3]), 50.0)
        self.assertAlmostEqual(float(out_obs.loc[observations.index[1], 3]), 55.0)
        self.assertAlmostEqual(float(out_obs.loc[observations.index[1], 4]), 0.1)
        self.assertTrue(pd.isna(out_obs.loc[observations.index[3], 1]))
        self.assertTrue(pd.isna(out_obs.loc[observations.index[3], 3]))
        # Fund-type category is preserved; origin moves to source.
        self.assertTrue(
            out_catalog.loc[out_catalog["header"].eq("US8085098551 TR"), "category"]
            .eq("Index")
            .all()
        )
        self.assertTrue(
            out_catalog.loc[out_catalog["header"].eq("US8085098551 Price"), "category"]
            .eq("Index")
            .all()
        )
        self.assertTrue(
            out_catalog.loc[out_catalog["header"].eq("US8085098551 TR"), "source"]
            .eq("Yahoo")
            .all()
        )
        self.assertTrue(
            out_catalog.loc[out_catalog["header"].eq("US8085098551 Price"), "source"]
            .eq("Yahoo")
            .all()
        )
        self.assertEqual(list(out_obs.columns), [1, 2, 3, 4])

    def test_cfimx_untouched_when_not_in_map(self):
        catalog, observations = self._panel(include_cfimx=True)
        before_tr = observations[5].copy()
        before_price = observations[7].copy()
        tr_levels = pd.Series(
            [100.0, 110.0, 121.0],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
        )
        price_levels = pd.Series(
            [50.0, 55.0, 60.5],
            index=pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
        )
        _, out_obs, log = replace_datastream_tr_with_yahoo(
            catalog,
            observations,
            replacements={"US8085098551": "SWPPX"},
            fetch_tr_levels=lambda _t: tr_levels,
            fetch_price_levels=lambda _t: price_levels,
        )
        self.assertEqual(set(log["isin"]), {"US8085098551"})
        self.assertTrue(out_obs[5].equals(before_tr))
        self.assertTrue(out_obs[7].equals(before_price))

    def test_blanks_spx_flat_holiday_and_recomputes_next_session_return(self):
        """S&P-flat holidays are NA; the next session return uses the prior close."""
        dates = pd.to_datetime(
            ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
        )
        # S&P flat on 2020-01-03 (holiday); Yahoo has no print that day.
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4, 5, 6],
                "id": ["S&P", "S&P"] + ["US8085098551"] * 4,
                "name": ["S&P"] * 2 + ["Fund"] * 4,
                "category": ["Index"] * 6,
                "fee": [pd.NA] * 6,
                "note": [
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Price, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                ],
                "header": [
                    "S&P 500 TR",
                    "S&P 500 TR %",
                    "US8085098551 TR",
                    "US8085098551 TR %",
                    "US8085098551 Price",
                    "US8085098551 Price %",
                ],
                "observations": [4] * 6,
                "first_date": [dates[0]] * 6,
                "last_date": [dates[-1]] * 6,
            }
        )
        observations = pd.DataFrame(
            {
                1: [100.0, 100.0, 101.0, 102.0],
                2: [pd.NA, 0.0, 0.01, 0.0099],
                3: [10.0, 10.0, 10.0, 10.0],
                4: [pd.NA, 0.0, 0.0, 0.0],
                5: [50.0, 50.0, 50.0, 50.0],
                6: [pd.NA, 0.0, 0.0, 0.0],
            },
            index=pd.Index(dates, name="date"),
        )
        tr_levels = pd.Series(
            [100.0, 110.0, 111.1],
            index=pd.to_datetime(["2020-01-02", "2020-01-06", "2020-01-07"]),
        )
        price_levels = pd.Series(
            [50.0, 55.0, 55.55],
            index=pd.to_datetime(["2020-01-02", "2020-01-06", "2020-01-07"]),
        )
        out_catalog, out_obs, log = replace_datastream_tr_with_yahoo(
            catalog,
            observations,
            replacements={"US8085098551": "SWPPX"},
            fetch_tr_levels=lambda _t: tr_levels,
            fetch_price_levels=lambda _t: price_levels,
        )
        holiday = dates[1]
        next_session = dates[2]
        self.assertTrue(pd.isna(out_obs.loc[holiday, 3]))
        self.assertTrue(pd.isna(out_obs.loc[holiday, 4]))
        self.assertAlmostEqual(float(out_obs.loc[next_session, 4]), 0.1)
        self.assertTrue(pd.isna(out_obs.loc[holiday, 5]))
        self.assertTrue(pd.isna(out_obs.loc[holiday, 6]))
        self.assertAlmostEqual(float(out_obs.loc[next_session, 6]), 0.1)
        self.assertEqual(int(log.loc[0, "tr_days_filled"]), 3)
        self.assertEqual(int(log.loc[0, "tr_days_blank"]), 1)

        _, issue_summary, _ = summarize_tr_consistency(
            out_catalog, out_obs, flags=("gaps",)
        )
        yahoo_gaps = issue_summary.loc[
            issue_summary["header"].eq("US8085098551 TR %"), "gaps"
        ]
        self.assertEqual(int(yahoo_gaps.iloc[0]), 0)


class HolidayNaHelpersTests(unittest.TestCase):
    def test_spx_flat_mask_and_session_returns(self):
        dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
        market = pd.Series([100.0, 100.0, 101.0], index=dates)
        mask = spx_flat_holiday_mask(market)
        self.assertFalse(bool(mask.iloc[0]))
        self.assertTrue(bool(mask.iloc[1]))
        self.assertFalse(bool(mask.iloc[2]))
        levels = pd.Series([100.0, float("nan"), 110.0], index=dates)
        filled, returns = levels_and_returns_with_holiday_na(levels, mask)
        self.assertTrue(pd.isna(filled.iloc[1]))
        self.assertAlmostEqual(float(returns.iloc[2]), 0.1)


class RescaleYahooReplacedIsinsHaveNoLevelActionTests(unittest.TestCase):
    """Yahoo-replaced ISINs are absent from level_actions (Step 1 owns them)."""

    def test_yahoo_replaced_isin_with_break_is_not_rescaled(self):
        dates = pd.date_range("2020-04-15", periods=8, freq="B")
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4, 5, 6],
                "id": [
                    "S&P",
                    "S&P",
                    "US78472P1093",
                    "US78472P1093",
                    "US78472P1093",
                    "US78472P1093",
                ],
                "name": ["S&P"] * 2 + ["State Street"] * 4,
                "category": ["Index"] * 6,
                "fee": [pd.NA] * 6,
                "note": [
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Price, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                ],
                "header": [
                    "S&P 500 TR",
                    "S&P 500 TR %",
                    "US78472P1093 TR",
                    "US78472P1093 TR %",
                    "US78472P1093 Price",
                    "US78472P1093 Price %",
                ],
            }
        )
        market = pd.Series(
            [100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0], index=dates
        )
        fund_tr = market.copy()
        fund_price = market.copy()
        break_day = pd.Timestamp("2020-04-20")
        if break_day in dates:
            fund_tr.loc[break_day:] = fund_tr.loc[break_day:] * 6
            fund_price.loc[break_day:] = fund_price.loc[break_day:] * 6
        observations = pd.DataFrame(
            {
                1: market.to_numpy(),
                2: market.pct_change().to_numpy(),
                3: fund_tr.to_numpy(),
                4: fund_tr.pct_change().to_numpy(),
                5: fund_price.to_numpy(),
                6: fund_price.pct_change().to_numpy(),
            },
            index=dates,
        )
        before_tr = observations[3].copy()
        before_price = observations[5].copy()
        adjusted, log = rescale_level_breaks(catalog, observations)
        # No Datastream CA rule for Yahoo ISINs → not adjusted, not rescaled.
        not_adjusted = log.loc[
            log["isin"].eq("US78472P1093") & log["decision"].eq("not adjusted")
        ]
        self.assertFalse(not_adjusted.empty)
        self.assertEqual(set(not_adjusted["series"]), {"Price", "TR"})
        self.assertFalse(
            (
                log["decision"].eq("rescaled") & log["isin"].eq("US78472P1093")
            ).any()
        )
        self.assertFalse(
            log["decision"].eq("skipped — Yahoo Price+TR at load").any()
        )
        self.assertTrue(adjusted[3].equals(before_tr))
        self.assertTrue(adjusted[5].equals(before_price))

    def test_yahoo_replaced_isin_silent_when_no_break(self):
        dates = pd.date_range("2020-04-15", periods=8, freq="B")
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4, 5, 6],
                "id": [
                    "S&P",
                    "S&P",
                    "US78472P1093",
                    "US78472P1093",
                    "US78472P1093",
                    "US78472P1093",
                ],
                "name": ["S&P"] * 2 + ["State Street"] * 4,
                "category": ["Index"] * 6,
                "fee": [pd.NA] * 6,
                "note": [
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Price, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                ],
                "header": [
                    "S&P 500 TR",
                    "S&P 500 TR %",
                    "US78472P1093 TR",
                    "US78472P1093 TR %",
                    "US78472P1093 Price",
                    "US78472P1093 Price %",
                ],
            }
        )
        market = pd.Series(
            [100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0], index=dates
        )
        observations = pd.DataFrame(
            {
                1: market.to_numpy(),
                2: market.pct_change().to_numpy(),
                3: market.to_numpy(),
                4: market.pct_change().to_numpy(),
                5: market.to_numpy(),
                6: market.pct_change().to_numpy(),
            },
            index=dates,
        )
        _, log = rescale_level_breaks(catalog, observations)
        self.assertFalse((log["isin"].eq("US78472P1093")).any())
        self.assertFalse(
            (log["isin"].eq("US78472P1093") & log["decision"].eq("rescaled")).any()
        )


if __name__ == "__main__":
    unittest.main()
