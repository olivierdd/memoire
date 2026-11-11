import unittest

import numpy as np
import pandas as pd

from helpers.timeseries_functions.total_return_gap import (
    return_gap_attribution,
    return_gap_cause_summary,
    total_return_level_identity,
)


class TotalReturnLevelIdentityTests(unittest.TestCase):
    def _daily(self, fund_returns: list[float | None]) -> pd.DataFrame:
        dates = pd.to_datetime(["2016-09-30", "2023-09-29", "2026-09-30"])
        index_level = [100.0, 150.0, 200.0]
        fund_level = [10.0, 15.0, 20.0]
        index_return = [np.nan, 0.5, 200.0 / 150.0 - 1.0]
        return pd.DataFrame(
            {
                "S&P 500 TR": index_level,
                "S&P 500 TR %": index_return,
                "US0000000001 TR": fund_level,
                "US0000000001 TR %": fund_returns,
            },
            index=dates,
        )

    def test_compounded_return_matches_the_level_change(self):
        daily = self._daily([np.nan, 0.5, 20.0 / 15.0 - 1.0])
        report = total_return_level_identity(daily, ["US0000000001"])
        ten_year = report.loc[report["horizon"].eq("10y")].iloc[0]
        three_year = report.loc[report["horizon"].eq("3y")].iloc[0]
        self.assertAlmostEqual(ten_year["level_pct"], 100.0)
        self.assertAlmostEqual(ten_year["compound_pct"], 100.0)
        self.assertEqual(ten_year["n_breaks"], 0)
        self.assertEqual(ten_year["n_missing"], 0)
        self.assertAlmostEqual(three_year["level_pct"], (20.0 / 15.0 - 1.0) * 100.0)
        self.assertAlmostEqual(three_year["compound_pct"], three_year["level_pct"])

    def test_a_stored_return_that_disagrees_with_the_level_is_a_break(self):
        daily = self._daily([np.nan, 0.4, 20.0 / 15.0 - 1.0])
        report = total_return_level_identity(daily, ["US0000000001"])
        ten_year = report.loc[report["horizon"].eq("10y")].iloc[0]
        three_year = report.loc[report["horizon"].eq("3y")].iloc[0]
        self.assertEqual(ten_year["n_breaks"], 1)
        self.assertEqual(three_year["n_breaks"], 0)
        self.assertGreater(ten_year["abs_diff_pp"], 1.0)


class DecemberAttributionTests(unittest.TestCase):
    def test_december_lag_is_separated_from_the_other_months(self):
        periods = pd.period_range("2023-10", periods=36, freq="M")
        index = pd.Series(0.01, index=periods, name="S&P 500 TR %")
        fund = index.copy()
        fund.loc[fund.index.month == 12] = -0.05
        monthly = pd.DataFrame({"S&P 500 TR %": index, "US0000000001 TR %": fund})
        comparable = pd.DataFrame(
            [
                {
                    "isin": "US0000000001",
                    "name": "December fund",
                    "horizon": "3y",
                    "window_start": "2023-10",
                    "window_end": "2026-09",
                    "delta_total_return_pct": -4.0,
                }
            ]
        )
        funds = pd.DataFrame(
            [{"ISIN": "US0000000001", "Total Expense Ratio": "0,50"}]
        )
        attribution = return_gap_attribution(monthly, comparable, funds)
        row = attribution.iloc[0]
        self.assertAlmostEqual(row["expense"], 0.5)
        self.assertLess(row["december_log_excess"], -0.02)
        self.assertAlmostEqual(row["other_log_excess"], 0.0)
        self.assertTrue(row["worst_is_december"])
        summary = return_gap_cause_summary(attribution)
        three_year = summary.loc[summary["horizon"].eq("3y")].iloc[0]
        self.assertEqual(three_year["n_large_december"], 1)
        self.assertEqual(three_year["n_quiet_december"], 0)
        self.assertAlmostEqual(three_year["median_gap_large_december"], -4.0)


if __name__ == "__main__":
    unittest.main()
