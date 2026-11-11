import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from helpers.timeseries_functions.rebuild_tr_from_distributions import (
    align_events_to_sessions,
    lipper_gate_should_adopt,
    recompute_tr_level,
    rebuild_fund_tr,
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
        self.assertTrue(meta.adopted)
        self.assertEqual(meta.source, "yahoo")
        if ex in new_pct.index:
            self.assertGreater(new_pct.loc[ex], legacy_tr.loc[ex])


if __name__ == "__main__":
    unittest.main()
