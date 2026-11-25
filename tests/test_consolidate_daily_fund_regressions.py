import unittest

import numpy as np
import pandas as pd

from helpers.timeseries_functions.consolidate_daily_fund_regressions import (
    build_consolidated_group_stats,
    category_flags,
    fit_daily_fund_benchmark_regression,
    format_table_figures,
    _filter_group,
)


class FitDailyRegressionTests(unittest.TestCase):
    def test_excel_identities_on_synthetic_daily(self):
        rng = np.random.default_rng(42)
        n = 252
        bench = rng.normal(0.0004, 0.01, n)
        fund = 0.0001 + 0.95 * bench + rng.normal(0, 0.002, n)
        fees = 0.42
        stats = fit_daily_fund_benchmark_regression(
            fund, bench, trading_days_per_year=252, fees_pct=fees
        )
        self.assertEqual(stats["Trading days"], 252.0)
        self.assertAlmostEqual(
            stats["Gross alpha (%/yr)"],
            stats["Net alpha (%/yr)"] + fees,
            places=6,
        )
        if stats["Tracking error (%)"] > 0:
            expected_ir = stats["Excess return (%/yr)"] / stats["Tracking error (%)"]
            self.assertAlmostEqual(stats["Information ratio"], expected_ir, places=6)

    def test_too_few_days_returns_nan_metrics(self):
        stats = fit_daily_fund_benchmark_regression(
            np.array([0.01, 0.02]),
            np.array([0.01, 0.015]),
        )
        self.assertTrue(np.isnan(stats["Beta"]))


class FormatTableFiguresTests(unittest.TestCase):
    def test_rounds_to_four_decimals(self):
        frame = pd.DataFrame(
            {
                "Fund": ["US1"],
                "Fees (%)": [0.123456],
                "Beta": [1.23456789],
            }
        )
        shown = format_table_figures(frame)
        self.assertEqual(shown.at[0, "Fees (%)"], 0.1235)
        self.assertEqual(shown.at[0, "Beta"], 1.2346)

    def test_keeps_dash_in_consolidated_cells(self):
        frame = pd.DataFrame(
            {
                "Indicator": ["Overview", "Beta"],
                "Statistic": ["Number of funds", "Mean"],
                "Active": [264.0, 0.999876],
                "Passive ETF": ["–", 1.234567],
            }
        )
        shown = format_table_figures(frame)
        self.assertEqual(shown.at[0, "Active"], 264)
        self.assertEqual(shown.at[0, "Passive ETF"], "–")
        self.assertEqual(shown.at[1, "Active"], 0.9999)
        self.assertEqual(shown.at[1, "Passive ETF"], 1.2346)


class ConsolidatedGroupStatsTests(unittest.TestCase):
    def test_group_filters_and_counts(self):
        table = pd.DataFrame(
            [
                {
                    "Fund": "A",
                    "Category": "Active MF",
                    "ETF": 0,
                    "Active": 1,
                    "ETF×Active": 0,
                    "Fees (%)": 0.5,
                    "AUM": 1e9,
                    "Trading days": 100,
                    "Beta": 1.0,
                    "Tracking error (%)": 2.0,
                    "Excess return (%/yr)": 1.0,
                    "Net alpha (%/yr)": 0.5,
                    "Gross alpha (%/yr)": 1.0,
                    "Information ratio": 0.5,
                    "Selected Y": 0.5,
                },
                {
                    "Fund": "B",
                    "Category": "Passive ETF",
                    "ETF": 1,
                    "Active": 0,
                    "ETF×Active": 0,
                    "Fees (%)": 0.1,
                    "AUM": 2e9,
                    "Trading days": 200,
                    "Beta": 0.9,
                    "Tracking error (%)": 1.0,
                    "Excess return (%/yr)": -0.5,
                    "Net alpha (%/yr)": -0.2,
                    "Gross alpha (%/yr)": -0.1,
                    "Information ratio": -0.5,
                    "Selected Y": -0.2,
                },
                {
                    "Fund": "C",
                    "Category": "Active ETF",
                    "ETF": 1,
                    "Active": 1,
                    "ETF×Active": 1,
                    "Fees (%)": 0.2,
                    "AUM": 3e9,
                    "Trading days": 150,
                    "Beta": 1.1,
                    "Tracking error (%)": 3.0,
                    "Excess return (%/yr)": 0.2,
                    "Net alpha (%/yr)": 0.1,
                    "Gross alpha (%/yr)": 0.3,
                    "Information ratio": 0.07,
                    "Selected Y": 0.1,
                },
            ]
        )
        consolidated = build_consolidated_group_stats(table)
        active_row = consolidated.loc[
            (consolidated["Indicator"].eq("Overview"))
            & (consolidated["Statistic"].eq("Number of funds"))
        ].iloc[0]
        self.assertEqual(active_row["Active"], 2.0)
        self.assertEqual(active_row["Passive"], 1.0)
        self.assertEqual(active_row["ETF"], 2.0)
        self.assertEqual(active_row["Mutual Funds"], 1.0)
        self.assertEqual(active_row["Active MF"], 1.0)
        self.assertEqual(active_row["Passive ETF"], 1.0)

    def test_category_flags(self):
        self.assertEqual(category_flags("Active MF")[1:], (0, 1, 0))
        self.assertEqual(category_flags("Passive ETF")[1:], (1, 0, 0))


class FilterGroupTests(unittest.TestCase):
    def test_active_mf_filter(self):
        frame = pd.DataFrame({"Active": [1, 0, 1], "ETF": [0, 0, 1]})
        subset = _filter_group(frame, active=1, etf=0)
        self.assertEqual(len(subset), 1)


if __name__ == "__main__":
    unittest.main()