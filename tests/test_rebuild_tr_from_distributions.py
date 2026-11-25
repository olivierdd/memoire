import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from helpers.timeseries_functions.rebuild_tr_from_distributions import (
    align_events_to_sessions,
    annotate_rebuild_log_lipper_status,
    lipper_gate_should_adopt,
    lipper_gate_should_adopt_only_if_pass,
    lipper_test_status,
    primary_lipper_horizon,
    recompute_tr_level,
    rebuild_fund_tr,
    summarize_lipper_gap_distribution,
    summarize_lipper_tolerance_sensitivity,
    summarize_rebuild_gate_transparency,
    total_return_percent_from_price,
)


class RebuildTrFromDistributionsTests(unittest.TestCase):
    def test_total_return_percent_reinvests_distribution(self):
        dates = pd.date_range("2024-12-11", periods=3, freq="B")
        price = pd.Series([15.655, 15.472, 15.531], index=dates)
        distributions = pd.Series([0.0, 0.185, 0.0], index=dates)
        returns = total_return_percent_from_price(price, distributions)
        self.assertAlmostEqual(returns.iloc[1], (15.472 + 0.185) / 15.655 - 1.0, places=6)

    def test_vontobel_style_price_drop_without_distribution_in_tr(self):
        dates = pd.date_range("2025-12-17", periods=2, freq="B")
        price = pd.Series([18.75, 3.76], index=dates)
        distributions = pd.Series([0.0, 0.0], index=dates)
        returns = total_return_percent_from_price(price, distributions)
        self.assertAlmostEqual(returns.iloc[1], 3.76 / 18.75 - 1.0, places=6)

    def test_total_return_spans_holiday_na_prior(self):
        """After Step 2 blanks holidays, the next session must use the last print."""
        dates = pd.to_datetime(["2024-12-23", "2024-12-24", "2024-12-26"])
        price = pd.Series([100.0, np.nan, 101.0], index=dates)
        distributions = pd.Series([0.0, 0.0, 0.50], index=dates)
        returns = total_return_percent_from_price(price, distributions)
        self.assertTrue(pd.isna(returns.iloc[1]))
        self.assertAlmostEqual(returns.iloc[2], (101.0 + 0.50) / 100.0 - 1.0, places=6)

    def test_align_events_to_sessions_forward(self):
        sessions = pd.date_range("2024-12-12", periods=3, freq="B")
        events = pd.Series({pd.Timestamp("2024-12-13"): 0.185})
        aligned = align_events_to_sessions(sessions, events)
        self.assertAlmostEqual(aligned.iloc[1], 0.185)

    def test_lipper_gate_prefers_improvement(self):
        before = {"10y": -25.0, "5y": -9.0, "3y": -3.0}
        after = {"10y": -0.2, "5y": -0.1, "3y": -0.05}
        self.assertTrue(lipper_gate_should_adopt(before, after))

    def test_lipper_gate_keeps_legacy_when_worse(self):
        before = {"10y": -2.0, "5y": -1.0, "3y": -0.5}
        after = {"10y": -8.0, "5y": -4.0, "3y": -1.0}
        self.assertFalse(lipper_gate_should_adopt(before, after))

    def test_primary_horizon_falls_back_10y_to_5y_to_3y(self):
        self.assertEqual(
            primary_lipper_horizon({"10y": -1.0, "5y": -2.0, "3y": -3.0}),
            "10y",
        )
        self.assertEqual(
            primary_lipper_horizon({"10y": float("nan"), "5y": -2.0, "3y": -3.0}),
            "5y",
        )
        self.assertEqual(
            primary_lipper_horizon({"10y": float("nan"), "5y": float("nan"), "3y": -3.0}),
            "3y",
        )
        self.assertIsNone(
            primary_lipper_horizon(
                {"10y": float("nan"), "5y": float("nan"), "3y": float("nan")}
            )
        )

    def test_lipper_test_status_uses_fallback_horizon(self):
        self.assertEqual(
            lipper_test_status({"10y": float("nan"), "5y": 0.2, "3y": 2.0}),
            ("pass", "5y"),
        )
        self.assertEqual(
            lipper_test_status({"10y": float("nan"), "5y": float("nan"), "3y": 2.0}),
            ("fail", "3y"),
        )
        self.assertEqual(
            lipper_test_status(
                {"10y": float("nan"), "5y": float("nan"), "3y": float("nan")}
            ),
            ("unscored", None),
        )

    def test_lipper_gate_falls_back_when_10y_missing(self):
        before = {"10y": float("nan"), "5y": -9.0, "3y": -3.0}
        after_pass_and_improve = {"10y": float("nan"), "5y": -0.2, "3y": -0.1}
        after_improve_but_fail = {"10y": float("nan"), "5y": -4.0, "3y": -1.0}
        after_worse = {"10y": float("nan"), "5y": -12.0, "3y": -5.0}
        self.assertTrue(lipper_gate_should_adopt(before, after_pass_and_improve))
        self.assertFalse(lipper_gate_should_adopt(before, after_improve_but_fail))
        self.assertFalse(lipper_gate_should_adopt(before, after_worse))

    def test_lipper_gate_does_not_skip_to_shorter_when_10y_exists(self):
        before = {"10y": -2.0, "5y": -9.0, "3y": -3.0}
        # 10y is worse; a close 5y must not override when 10y is available.
        after = {"10y": -8.0, "5y": -0.1, "3y": -0.05}
        self.assertFalse(lipper_gate_should_adopt(before, after))

    def test_lipper_gate_requires_pass_and_improve(self):
        before = {"10y": -25.0, "5y": -9.0, "3y": -3.0}
        after_improved_fail = {"10y": -8.0, "5y": -4.0, "3y": -1.0}
        after_pass_and_improve = {"10y": -0.2, "5y": -0.1, "3y": -0.05}
        after_pass_but_worse = {"10y": -0.4, "5y": -0.3, "3y": -0.2}
        before_already_close = {"10y": -0.05, "5y": -0.02, "3y": -0.01}
        self.assertFalse(lipper_gate_should_adopt(before, after_improved_fail))
        self.assertFalse(
            lipper_gate_should_adopt_only_if_pass(before, after_improved_fail)
        )
        self.assertTrue(lipper_gate_should_adopt(before, after_pass_and_improve))
        self.assertTrue(
            lipper_gate_should_adopt_only_if_pass(before, after_pass_and_improve)
        )
        # Rebuild passes but Datastream was already closer → refuse production;
        # looser pass-only counterfactual would still adopt.
        self.assertFalse(
            lipper_gate_should_adopt(before_already_close, after_pass_but_worse)
        )
        self.assertTrue(
            lipper_gate_should_adopt_only_if_pass(
                before_already_close, after_pass_but_worse
            )
        )

    def test_summarize_rebuild_gate_transparency_post_adopt_and_sensitivity(self):
        log = pd.DataFrame(
            [
                {
                    "isin": "US1",
                    "ticker": "AAA",
                    "decision": "adopted",
                    "gap_10y_before": -10.0,
                    "gap_10y_after": -0.1,
                    "gap_5y_before": -5.0,
                    "gap_5y_after": -0.05,
                    "gap_3y_before": -2.0,
                    "gap_3y_after": -0.02,
                },
                {
                    "isin": "US2",
                    "ticker": "BBB",
                    "decision": "adopted",
                    "gap_10y_before": -20.0,
                    "gap_10y_after": -8.0,
                    "gap_5y_before": -9.0,
                    "gap_5y_after": -4.0,
                    "gap_3y_before": -3.0,
                    "gap_3y_after": -1.0,
                },
                {
                    "isin": "US3",
                    "ticker": "CCC",
                    "decision": "kept_legacy",
                    "gap_10y_before": -0.05,
                    "gap_10y_after": -0.3,
                    "gap_5y_before": -0.02,
                    "gap_5y_after": -0.2,
                    "gap_3y_before": -0.01,
                    "gap_3y_after": -0.1,
                },
            ]
        )
        summary, fail_table = summarize_rebuild_gate_transparency(log)
        self.assertEqual(summary["n_funds"], 3)
        self.assertEqual(summary["n_adopted"], 2)
        self.assertEqual(summary["n_kept_legacy"], 1)
        self.assertEqual(summary["adopted_pass"], 1)
        self.assertEqual(summary["adopted_fail"], 1)
        self.assertEqual(summary["adopted_unscored"], 0)
        # Pass-only counterfactual adopts US1 (pass) and US3 (pass, no improve).
        self.assertEqual(summary["strict_would_adopt"], 2)
        self.assertEqual(summary["strict_would_keep"], 1)
        self.assertEqual(summary["adopted_under_both"], 1)
        self.assertEqual(summary["adopted_only_under_production"], 1)
        self.assertEqual(summary["pass_only_extra"], 1)
        self.assertEqual(list(fail_table["isin"]), ["US2"])
        self.assertFalse(bool(fail_table.loc[0, "strict_would_adopt"]))

    def test_annotate_rebuild_log_lipper_status(self):
        log = pd.DataFrame(
            [
                {
                    "isin": "US1",
                    "ticker": "AAA",
                    "decision": "adopted",
                    "gap_10y_before": -10.0,
                    "gap_10y_after": -0.1,
                    "gap_5y_before": -5.0,
                    "gap_5y_after": -0.05,
                    "gap_3y_before": -2.0,
                    "gap_3y_after": -0.02,
                },
                {
                    "isin": "US2",
                    "ticker": "BBB",
                    "decision": "kept_legacy",
                    "gap_10y_before": -20.0,
                    "gap_10y_after": -8.0,
                    "gap_5y_before": -9.0,
                    "gap_5y_after": -4.0,
                    "gap_3y_before": -3.0,
                    "gap_3y_after": -1.0,
                },
            ]
        )
        out = annotate_rebuild_log_lipper_status(log)
        self.assertTrue(out.loc[0, "lipper_fail_after"] == False)
        self.assertEqual(out.loc[0, "lipper_status_after"], "pass")
        self.assertTrue(bool(out.loc[1, "lipper_fail_after"]))
        self.assertEqual(out.loc[1, "lipper_status_after"], "fail")
        self.assertTrue(bool(out.loc[1, "lipper_dual_fail"]))

    def test_summarize_lipper_gap_distribution(self):
        log = pd.DataFrame(
            [
                {
                    "gap_10y_before": -10.0,
                    "gap_10y_after": -0.5,
                    "gap_5y_before": -5.0,
                    "gap_5y_after": -0.4,
                    "gap_3y_before": -2.0,
                    "gap_3y_after": -0.3,
                },
                {
                    "gap_10y_before": -30.0,
                    "gap_10y_after": -1.0,
                    "gap_5y_before": -8.0,
                    "gap_5y_after": -0.6,
                    "gap_3y_before": -4.0,
                    "gap_3y_after": -0.7,
                },
            ]
        )
        table = summarize_lipper_gap_distribution(log)
        self.assertEqual(len(table), 6)
        row_10y_ds = table.loc[
            (table["Series"] == "Datastream TR") & (table["Horizon"] == "10y")
        ].iloc[0]
        self.assertEqual(int(row_10y_ds["n"]), 2)
        self.assertAlmostEqual(float(row_10y_ds["median"]), -20.0)

    def test_summarize_lipper_tolerance_sensitivity(self):
        log = pd.DataFrame(
            [
                {
                    "isin": "US1",
                    "ticker": "AAA",
                    "decision": "adopted",
                    "gap_10y_before": -10.0,
                    "gap_10y_after": -0.1,
                    "gap_5y_before": -5.0,
                    "gap_5y_after": -0.05,
                    "gap_3y_before": -2.0,
                    "gap_3y_after": -0.02,
                },
                {
                    "isin": "US2",
                    "ticker": "BBB",
                    "decision": "kept_legacy",
                    "gap_10y_before": -0.3,
                    "gap_10y_after": -0.4,
                    "gap_5y_before": -0.2,
                    "gap_5y_after": -0.25,
                    "gap_3y_before": -0.1,
                    "gap_3y_after": -0.15,
                },
            ]
        )
        table = summarize_lipper_tolerance_sensitivity(
            log, close_pp_values=(0.25, 0.5, 1.0)
        )
        self.assertEqual(list(table["tau_pp"]), [0.25, 0.5, 1.0])
        row_025 = table.loc[table["tau_pp"] == 0.25].iloc[0]
        row_05 = table.loc[table["tau_pp"] == 0.5].iloc[0]
        row_10 = table.loc[table["tau_pp"] == 1.0].iloc[0]
        # US1: before −10 fails all τ; after −0.1 passes all τ → adopt.
        # US2: before −0.3 / after −0.4 pass at 0.5+ but do not improve.
        self.assertEqual(int(row_025["datastream_pass"]), 0)
        self.assertEqual(int(row_025["rebuild_pass"]), 1)
        self.assertEqual(int(row_025["would_adopt"]), 1)
        self.assertEqual(int(row_05["datastream_pass"]), 1)
        self.assertEqual(int(row_05["rebuild_pass"]), 2)
        self.assertEqual(int(row_05["would_adopt"]), 1)
        self.assertEqual(int(row_10["datastream_pass"]), 1)
        self.assertEqual(int(row_10["rebuild_pass"]), 2)
        self.assertEqual(int(row_10["would_adopt"]), 1)

    def test_recompute_tr_level(self):
        dates = pd.date_range("2024-01-02", periods=3, freq="B")
        returns = pd.Series([0.01, 0.02, -0.01], index=dates)
        levels = recompute_tr_level(returns, anchor_level=100.0, anchor_index=dates[0])
        self.assertAlmostEqual(levels.iloc[2], 100.0 * 1.02 * 0.99, places=6)

    @patch(
        "helpers.timeseries_functions.rebuild_tr_from_distributions.fetch_yahoo_cash_events"
    )
    def test_rebuild_partial_dividend_improves_gap(self, mock_yahoo):
        dates = pd.bdate_range("2016-01-04", "2026-09-30")
        n = len(dates)
        price = pd.Series(15.0, index=dates, dtype=float)
        price_pct = price.pct_change().fillna(0.0)
        spx = pd.Series(0.0005, index=dates)
        legacy_tr = price_pct.copy()
        ex = pd.Timestamp("2024-12-13")
        if ex in legacy_tr.index:
            legacy_tr.loc[ex] = -0.0095
        legacy_level = (1 + legacy_tr).cumprod() * 100.0
        mock_yahoo.return_value = pd.DataFrame(
            {"distribution": [0.185]},
            index=pd.DatetimeIndex([ex]),
        )
        fund_row = pd.Series(
            {
                "Name": "Schwab S&P 500 Index Fund",
                "Benchmark Ticker": ".SPXTR",
                "fund_type": "Passive",
                "is_index_or_idx": True,
                "10 Year Performance to Last Month End": 315.17,
                "5 Year Performance to Last Month End": 90.52,
                "3 Year Performance to Last Month End": 85.45,
            }
        )
        bench_counts = spx.groupby(spx.index.to_period("M")).count()
        cache: dict = {"SWPPX": {"events": [], "source": "yahoo"}}
        new_pct, _, meta = rebuild_fund_tr(
            isin="US8085098551",
            session_dates=pd.DatetimeIndex(dates),
            price=price,
            legacy_tr_pct=legacy_tr,
            legacy_tr_level=legacy_level,
            spx_tr_pct=spx,
            price_pct=price_pct,
            fund_row=fund_row,
            ticker="SWPPX",
            bench_counts=bench_counts,
            distributions_cache=cache,
        )
        # Rebuild narrows the Lipper gap on the ex-day fix, but the flat price
        # path still fails Lipper, so pass-and-improve keeps Datastream.
        self.assertFalse(meta.adopted)
        self.assertEqual(meta.decision, "kept_legacy")
        self.assertEqual(meta.source, "unchanged")
        self.assertLess(
            abs(float(meta.gap_after["10y"])),
            abs(float(meta.gap_before["10y"])),
        )
        # Returned series is the legacy TR when adoption is refused.
        pd.testing.assert_series_equal(new_pct, legacy_tr)


if __name__ == "__main__":
    unittest.main()
