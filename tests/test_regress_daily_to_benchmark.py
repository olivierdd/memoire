import json
import unittest
import warnings

import numpy as np
import pandas as pd

from helpers.timeseries_functions.regress_daily_to_benchmark import (
    BENCHMARK_TICKER_TO_HEADER,
    LIPPER_AS_OF,
    LIPPER_MATCH_TOLERANCES,
    SPX_BENCH_HEADER,
    clip_daily_panel_to_lipper_as_of,
    compound_daily_to_monthly,
    daily_series_sheets,
    fit_monthly_regression,
    fund_tr_return_header,
    horizon_sharpe_ratio,
    horizon_total_return_pct,
    lipper_horizon_match,
    monthly_scatter_frame,
    index_total_return_check,
    regression_rows_for_funds,
    total_return_lipper_report,
)


class RegressDailyToBenchmarkTests(unittest.TestCase):
    def test_daily_series_sheets_uses_final_only(self):
        sheets = daily_series_sheets(
            ["Funds final", "D-Timeseries raw", "D-Timeseries final"]
        )
        self.assertEqual(sheets, {"corrected": "D-Timeseries final"})

    def test_daily_series_sheets_requires_final(self):
        with self.assertRaises(ValueError):
            daily_series_sheets(["D-Timeseries raw"])

    def test_compound_drops_thin_benchmark_month(self):
        dates = pd.date_range("2020-01-01", periods=20, freq="B")
        daily = pd.DataFrame(
            {
                "S&P 500 TR %": [0.01] * 18 + [0.02, 0.02],
                "US0000000001 TR %": [0.005] * 20,
            },
            index=dates,
        )
        counts = daily["S&P 500 TR %"].groupby(daily.index.to_period("M")).count()
        monthly = compound_daily_to_monthly(daily, counts, min_bench_days=15)
        self.assertEqual(len(monthly), 1)
        self.assertEqual(str(monthly.index[0]), "2020-01")

    def test_total_return_and_sharpe(self):
        returns = np.array([0.01, 0.02, -0.01, 0.005])
        self.assertAlmostEqual(
            horizon_total_return_pct(returns), (np.prod(1 + returns) - 1) * 100
        )
        self.assertAlmostEqual(
            horizon_sharpe_ratio(returns),
            returns.mean() / returns.std(ddof=1) * np.sqrt(12),
        )

    def test_fit_monthly_regression_exact_line(self):
        bench = pd.Series(
            np.array([-0.02, 0.0, 0.01, 0.03]),
            index=pd.PeriodIndex(["2024-01", "2024-02", "2024-03", "2024-04"], freq="M"),
        )
        fund = 0.001 + 0.95 * bench.to_numpy()
        fund = pd.Series(fund, index=bench.index)
        result = fit_monthly_regression(fund, bench, horizon="3y", last_n_months=4)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result.alpha_pct_per_month, 0.1)
        self.assertAlmostEqual(result.beta, 0.95)
        self.assertAlmostEqual(result.r_squared, 1.0)
        self.assertEqual(result.months, 4)

    def test_flat_fund_leaves_r_squared_and_correlation_undefined(self):
        bench = pd.Series(
            np.array([-0.02, 0.0, 0.01, 0.03]),
            index=pd.PeriodIndex(["2024-01", "2024-02", "2024-03", "2024-04"], freq="M"),
        )
        fund = pd.Series(0.0, index=bench.index)
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            result = fit_monthly_regression(fund, bench, horizon="3y", last_n_months=4)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(np.isnan(result.r_squared))
        self.assertTrue(np.isnan(result.correlation))
        self.assertAlmostEqual(result.alpha_pct_per_month, 0.0)
        self.assertAlmostEqual(result.beta, 0.0)

    def test_monthly_scatter_frame_months_are_json_strings(self):
        monthly = pd.DataFrame(
            {
                "S&P 500 TR %": [0.01, 0.02, -0.01],
                fund_tr_return_header("US0000000005"): [0.0, 0.01, 0.02],
            },
            index=pd.period_range("2024-01", periods=3, freq="M"),
        )
        frame = monthly_scatter_frame(
            monthly, "US0000000005", "S&P 500 TR %", last_n_months=3
        )
        self.assertEqual(list(frame["month"]), ["2024-01", "2024-02", "2024-03"])
        json.dumps(frame.to_dict(orient="records"))

    def test_lipper_alpha_units_on_comparison_row(self):
        periods = pd.period_range("2024-01", periods=36, freq="M")
        bench = pd.Series(np.linspace(-0.01, 0.02, 36), index=periods)
        fund = pd.Series(0.02 / 100 + 1.0 * bench.to_numpy(), index=periods)
        monthly = pd.DataFrame(
            {
                "S&P 500 TR %": bench,
                fund_tr_return_header("US0000000002"): fund,
            }
        )
        funds = pd.DataFrame(
            [
                {
                    "Name": "Synthetic",
                    "ISIN": "US0000000002",
                    "Benchmark Ticker": ".SPXTR",
                    "Benchmark Name": "S&P 500 TR",
                    "Alpha for 3 Years to Last Month End": 0.02,
                    "Beta for 3 Years to Last Month End": 1.0,
                    "R-Squared for 3 Years to Last Month End": 0.99,
                    "Annualised Tracking Error for 3 Years to Last Month End": 0.5,
                    "Alpha for 5 Years to Last Month End": np.nan,
                    "Beta for 5 Years to Last Month End": np.nan,
                    "R-Squared for 5 Years to Last Month End": np.nan,
                    "Annualised Tracking Error for 5 Years to Last Month End": np.nan,
                    "Alpha for 10 Years to Last Month End": np.nan,
                    "Beta for 10 Years to Last Month End": np.nan,
                    "R-Squared for 10 Years to Last Month End": np.nan,
                    "Annualised Tracking Error for 10 Years to Last Month End": np.nan,
                }
            ]
        )
        out = regression_rows_for_funds(funds, monthly, series_source="test")
        row = out.loc[(out["horizon"].eq("3y"))].iloc[0]
        self.assertAlmostEqual(row["alpha_pct_per_month"], 0.02, places=1)
        self.assertAlmostEqual(row["lipper_alpha_pct_per_month"], 0.02)
        self.assertLess(abs(row["delta_alpha_pp_per_month"]), 0.02)

    def test_unknown_benchmark_ticker_not_comparable(self):
        monthly = pd.DataFrame(
            {
                "S&P 500 TR %": [0.01, 0.02],
                "US0000000003 TR %": [0.01, 0.02],
            },
            index=pd.period_range("2024-01", periods=2, freq="M"),
        )
        funds = pd.DataFrame(
            [
                {
                    "Name": "Other bench",
                    "ISIN": "US0000000003",
                    "Benchmark Ticker": ".SPVX",
                }
            ]
        )
        out = regression_rows_for_funds(funds, monthly, series_source="test")
        self.assertTrue(out["status"].eq("benchmark_not_on_sheet").all())

    def test_lipper_match_tolerances(self):
        tol = LIPPER_MATCH_TOLERANCES
        self.assertTrue(
            lipper_horizon_match(
                delta_alpha_pp_per_month=tol["alpha_pp_per_month"],
                delta_beta=tol["beta"],
                delta_r_squared=tol["r_squared"],
                delta_tracking_error_pp=tol["tracking_error_pp"],
                has_lipper=True,
            )
        )
        self.assertFalse(
            lipper_horizon_match(
                delta_alpha_pp_per_month=tol["alpha_pp_per_month"] + 0.01,
                delta_beta=0.0,
                delta_r_squared=0.0,
                delta_tracking_error_pp=0.0,
                has_lipper=True,
            )
        )
        self.assertIsNone(
            lipper_horizon_match(
                delta_alpha_pp_per_month=0.0,
                delta_beta=0.0,
                delta_r_squared=0.0,
                delta_tracking_error_pp=0.0,
                has_lipper=False,
            )
        )

    def test_benchmark_map_includes_spxtr(self):
        self.assertEqual(
            BENCHMARK_TICKER_TO_HEADER[".SPXTR"], "S&P 500 TR %"
        )

    def test_comma_decimal_lipper_performance(self):
        periods = pd.period_range("2024-01", periods=4, freq="M")
        bench = pd.Series([0.01, 0.02, -0.01, 0.0], index=periods)
        monthly = pd.DataFrame(
            {
                "S&P 500 TR %": bench,
                fund_tr_return_header("US78462F1030"): bench,
            }
        )
        funds = pd.DataFrame(
            [
                {
                    "Name": "SPDR",
                    "ISIN": "US78462F1030",
                    "Benchmark Ticker": ".SPXTR",
                    "10 Year Performance to Last Month End": "314,26",
                    "Beta for 10 Years to Last Month End": "1,00",
                }
            ]
        )
        out = regression_rows_for_funds(funds, monthly, series_source="test")
        row = out.loc[out["horizon"].eq("10y")].iloc[0]
        self.assertAlmostEqual(row["lipper_total_return_pct"], 314.26)
        self.assertAlmostEqual(row["lipper_beta"], 1.0)

    def test_total_return_report_keeps_full_windows(self):
        comparison = pd.DataFrame(
            [
                {
                    "status": "ok",
                    "horizon": "3y",
                    "months": 36,
                    "isin": "A",
                    "name": "Alpha",
                    "total_return_pct": 10.0,
                    "lipper_total_return_pct": 10.5,
                    "delta_total_return_pct": -0.5,
                    "window_start": "2023-10",
                    "window_end": "2026-09",
                },
                {
                    "status": "ok",
                    "horizon": "3y",
                    "months": 36,
                    "isin": "B",
                    "name": "Beta",
                    "total_return_pct": 20.0,
                    "lipper_total_return_pct": 30.0,
                    "delta_total_return_pct": -10.0,
                    "window_start": "2023-10",
                    "window_end": "2026-09",
                },
                {
                    "status": "ok",
                    "horizon": "3y",
                    "months": 20,
                    "isin": "C",
                    "name": "Short",
                    "total_return_pct": 5.0,
                    "lipper_total_return_pct": 4.0,
                    "delta_total_return_pct": 1.0,
                    "window_start": "2025-01",
                    "window_end": "2026-09",
                },
                {
                    "status": "ok",
                    "horizon": "3y",
                    "months": 36,
                    "isin": "D",
                    "name": "No Lipper",
                    "total_return_pct": 8.0,
                    "lipper_total_return_pct": np.nan,
                    "delta_total_return_pct": np.nan,
                    "window_start": "2023-10",
                    "window_end": "2026-09",
                },
                {
                    "status": "insufficient_months",
                    "horizon": "3y",
                    "months": np.nan,
                    "isin": "E",
                    "name": "Missing",
                    "total_return_pct": np.nan,
                    "lipper_total_return_pct": np.nan,
                    "delta_total_return_pct": np.nan,
                    "window_start": None,
                    "window_end": None,
                },
            ]
        )
        report = total_return_lipper_report(comparison)
        self.assertEqual(set(report.comparable["isin"]), {"A", "B"})
        self.assertEqual(list(report.short_window["isin"]), ["C"])
        row = report.summary.loc[report.summary["horizon"].eq("3y")].iloc[0]
        self.assertEqual(row["computed"], 4)
        self.assertEqual(row["full_window"], 3)
        self.assertEqual(row["lipper_present"], 3)
        self.assertEqual(row["compared"], 2)
        self.assertAlmostEqual(row["median_gap_pp"], -5.25)
        self.assertEqual(row["within_close"], 1)
        self.assertEqual(row["window_start"], "2023-10")
        self.assertEqual(row["same_window"], 2)
        empty = report.summary.loc[report.summary["horizon"].eq("10y")].iloc[0]
        self.assertEqual(empty["compared"], 0)
        self.assertTrue(np.isnan(empty["correlation"]))

    def test_index_check_uses_the_most_common_lipper_print(self):
        periods = pd.period_range("2016-10", periods=120, freq="M")
        monthly = pd.DataFrame(
            {"S&P 500 TR %": [0.01] * 120},
            index=periods,
        )
        expected = (1.01**36 - 1) * 100
        funds = pd.DataFrame(
            [
                {
                    "Benchmark Ticker": ".SPXTR",
                    "3 Year Performance to Last Month End": 11.0,
                    "Relative Performance for 3 Years to Last Month End, (%)": 1.0,
                },
                {
                    "Benchmark Ticker": ".SPXTR",
                    "3 Year Performance to Last Month End": 12.0,
                    "Relative Performance for 3 Years to Last Month End, (%)": 2.0,
                },
                {
                    "Benchmark Ticker": ".SPXTR",
                    "3 Year Performance to Last Month End": "20,00",
                    "Relative Performance for 3 Years to Last Month End, (%)": 5.0,
                },
                {
                    "Benchmark Ticker": ".SPXTR",
                    "3 Year Performance to Last Month End": 10.01,
                    "Relative Performance for 3 Years to Last Month End, (%)": 0.0,
                },
                {
                    "Benchmark Ticker": ".INX",
                    "3 Year Performance to Last Month End": 50.0,
                    "Relative Performance for 3 Years to Last Month End, (%)": 0.0,
                },
            ]
        )
        report = index_total_return_check(monthly, funds)
        row = report.loc[report["horizon"].eq("3y")].iloc[0]
        self.assertAlmostEqual(row["computed_pct"], expected)
        self.assertEqual(row["lipper_pct"], 10.0)
        self.assertEqual(row["funds_on_print"], 2)
        self.assertEqual(row["funds_within_cent"], 3)
        self.assertEqual(row["funds_with_both"], 4)
        self.assertEqual(row["window_start"], "2023-10")
        self.assertEqual(row["window_end"], "2026-09")
        self.assertTrue(row["full_window"])
        self.assertEqual(report["horizon"].tolist(), ["3y", "5y", "10y"])

    def test_index_check_requires_the_return_column(self):
        monthly = pd.DataFrame({"other": [0.01, 0.02]})
        funds = pd.DataFrame({"Benchmark Ticker": [".SPXTR"]})
        with self.assertRaises(KeyError):
            index_total_return_check(monthly, funds)

    def test_clip_daily_panel_drops_sessions_after_lipper_as_of(self):
        dates = pd.to_datetime(
            ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]
        )
        daily = pd.DataFrame(
            {
                SPX_BENCH_HEADER: [0.01, 0.02, 0.03, 0.04],
                "US0000000004 TR %": [0.005, 0.005, 0.005, 0.005],
            },
            index=dates,
        )
        clipped, counts = clip_daily_panel_to_lipper_as_of(daily)
        self.assertEqual(clipped.index.max(), LIPPER_AS_OF)
        self.assertEqual(len(clipped), 2)
        self.assertNotIn(pd.Period("2026-10"), counts.index)


if __name__ == "__main__":
    unittest.main()
