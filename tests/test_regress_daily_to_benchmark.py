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
    fit_monthly_regression,
    fund_tr_return_header,
    horizon_sharpe_ratio,
    horizon_total_return_pct,
    lipper_horizon_match,
    monthly_scatter_frame,
    regression_rows_for_funds,
)


class RegressDailyToBenchmarkTests(unittest.TestCase):
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
