import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from helpers.timeseries_functions.compare_regression_to_consolidation import (
    build_consolidation_comparison_rows,
    compare_regression_to_consolidation,
    _slice_consolidation_window,
)
from helpers.timeseries_functions.compute_fund_to_index_regression import (
    compute_fund_to_index_regression,
)
from helpers.timeseries_functions.load_consolidation_regression import (
    load_consolidation_fund_regression_reference,
    load_consolidation_regression_window,
)
from helpers.timeseries_functions.load_workbook import find_workbook

INDEX = "S&P 500 TR"
MASTER = "US0000000001 (Lipper)"
ISIN = "US0000000001"
WORKBOOK_RELATIVE = Path("input-data-alix") / "clean"
WORKBOOK_FILENAME = "CLEAN_RECOLTE DONNEES-EXCEL.xlsx"
REAL_ISIN = "US4613088016"


def _delta_as_float(delta: str) -> float:
    if not delta:
        return float("nan")
    if delta.endswith("%"):
        return float(delta.rstrip("%")) / 100.0
    return float(delta)


def _synthetic_frame() -> pd.DataFrame:
    dates = pd.date_range("2016-10-01", periods=12, freq="MS")
    index_ret = np.linspace(-0.02, 0.03, len(dates))
    fund_ret = 0.001 + 0.95 * index_ret
    return pd.DataFrame(
        {
            "Period": dates.strftime("%b %Y"),
            "Date": dates,
            INDEX: index_ret,
            MASTER: fund_ret,
        }
    )


class BuildConsolidationComparisonRowsTests(unittest.TestCase):
    def test_deltas_are_zero_when_reference_matches_ols(self):
        frame = _synthetic_frame()
        result = compute_fund_to_index_regression(
            frame,
            INDEX,
            MASTER,
            fund_name="Test",
            quiet=True,
        )
        fees_pct = 0.84
        consolidation = pd.Series(
            {
                "Fund": ISIN,
                "Months": result.n_months,
                "Beta": result.beta,
                "Tracking error (%)": result.regression["residual_volatility"] * 100,
                "Excess return (%/yr)": result.regression["excess_annualized"] * 100,
                "Net alpha (%/yr)": result.regression["alpha_annualized"] * 100,
                "Gross alpha (%/yr)": (
                    result.regression["alpha_annualized"] + fees_pct / 100
                )
                * 100,
                "Information ratio": result.regression["information_ratio"],
                "Fees (%)": fees_pct,
            }
        )
        rows = build_consolidation_comparison_rows(result, consolidation)
        for row in rows:
            delta = row["Delta (notebook − Consolidation)"]
            if row["Metric"] == "Months":
                self.assertEqual(delta, "0")
            elif row["Metric"] == "Beta":
                self.assertEqual(delta, "0.000000")
            elif row["Metric"] == "Information ratio":
                self.assertEqual(delta, "0.000000")
            else:
                self.assertIn(delta, ("0.0000%", "-0.0000%"))


class SliceConsolidationWindowTests(unittest.TestCase):
    def test_inclusive_date_bounds(self):
        frame = _synthetic_frame()
        start = pd.Timestamp("2016-10-01")
        end = pd.Timestamp("2017-03-01")
        sliced = _slice_consolidation_window(frame, INDEX, MASTER, start, end)
        self.assertEqual(len(sliced), 6)


class CompareRegressionToConsolidationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.workbook = find_workbook(WORKBOOK_RELATIVE, WORKBOOK_FILENAME)
        except FileNotFoundError:
            cls.workbook = None

    def setUp(self):
        if self.workbook is None:
            self.skipTest("workbook not available")

    def test_window_loaders_match_consolidation_row(self):
        start, end = load_consolidation_regression_window(
            WORKBOOK_RELATIVE, WORKBOOK_FILENAME
        )
        self.assertLessEqual(start, end)
        row = load_consolidation_fund_regression_reference(
            REAL_ISIN, WORKBOOK_RELATIVE, WORKBOOK_FILENAME
        )
        self.assertEqual(str(row["Fund"]), REAL_ISIN)
        self.assertGreater(float(row["Months"]), 0)

    def test_notebook_ols_matches_consolidation_for_sample_fund(self):
        from helpers.timeseries_functions.load_index_timeseries import (
            load_index_timeseries,
        )
        from helpers.timeseries_functions.load_lipper_timeseries import (
            load_lipper_timeseries,
        )
        from helpers.timeseries_functions.load_workbook import load_funds_sheet
        from helpers.timeseries_functions.load_workbook import load_workbook

        timeseries_df = load_workbook(WORKBOOK_RELATIVE, WORKBOOK_FILENAME)
        funds = load_funds_sheet(WORKBOOK_RELATIVE, WORKBOOK_FILENAME)
        sp_cache = Path("cache") / "cache-sp500-tr-indices.json"
        fund_timeseries, selected = load_lipper_timeseries(
            timeseries_df,
            funds,
            REAL_ISIN,
            sp_cache,
        )
        fund_timeseries = load_index_timeseries(fund_timeseries, sp_cache)
        master_column = f"{REAL_ISIN} (Lipper)"
        regression_result = compute_fund_to_index_regression(
            fund_timeseries,
            INDEX,
            master_column,
            fund_name=str(selected["Name"]),
            quiet=True,
        )
        comparison = compare_regression_to_consolidation(
            regression_result,
            fund_timeseries,
            INDEX,
            master_column,
            REAL_ISIN,
            WORKBOOK_RELATIVE,
            WORKBOOK_FILENAME,
            fund_name=str(selected["Name"]),
        )
        for _, row in comparison.iterrows():
            delta = _delta_as_float(row["Delta (notebook − Consolidation)"])
            if row["Metric"] == "Months":
                self.assertLess(abs(delta), 1e-9)
            elif row["Metric"] == "Beta":
                self.assertLess(abs(delta), 1e-4)
            elif row["Metric"] == "Information ratio":
                self.assertLess(abs(delta), 1e-4)
            else:
                self.assertLess(abs(delta), 1e-6)


if __name__ == "__main__":
    unittest.main()
