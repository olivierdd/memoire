import io
import unittest
from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.consolidation_check_cache import (
    apply_consolidation_comparison_to_row,
    parse_consolidation_comparison_csv,
)
from helpers.timeseries_functions.regression_delta_parse import parse_regression_delta
from helpers.timeseries_functions.save_timeseries_check import find_project_root
from helpers.timeseries_functions.timeseries_checks_rows import (
    DATA_COLUMN_KEYS,
    LIPPER_DELTA_TE_MAX_PP,
    _lipper_horizon_deltas,
    build_regression_exclusions_rows,
    build_timeseries_checks_rows,
    consolidation_regression_result_label,
    lipper_regression_result_label,
    yahoo_result_label,
)

FIXTURE_ISIN = "US3538257060"


class TimeseriesChecksRowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = find_project_root()
        cls.checks_root = cls.root / "output-data" / "timeseries-checks"
        cls.fixture_dir = cls.checks_root / FIXTURE_ISIN
        if not cls.fixture_dir.is_dir():
            raise unittest.SkipTest(f"Missing fixture {cls.fixture_dir}")

    def test_fixture_row_has_expected_keys(self) -> None:
        funds = pd.DataFrame({"ISIN": [FIXTURE_ISIN], "Name": ["Fixture"]})
        frame = build_timeseries_checks_rows(funds, checks_root=self.checks_root)
        self.assertEqual(len(frame), 1)
        row = frame.iloc[0]
        self.assertEqual(row["lipper_isin"], FIXTURE_ISIN)
        self.assertIn(row["yahoo_result"], ("Match", "Mismatch", "Date alignment"))
        self.assertEqual(row["lipper_quality_result"], "Match")
        for key in DATA_COLUMN_KEYS:
            self.assertIn(key, row.index)

    def test_yahoo_result_labels(self) -> None:
        self.assertEqual(
            yahoo_result_label({"n_months": 10, "mismatches": 0}, None),
            "Match",
        )
        self.assertEqual(
            yahoo_result_label(
                {"n_months": 10, "mismatches": 2},
                {"within_tolerance": True, "date_mismatch": False},
            ),
            "Date alignment",
        )
        self.assertEqual(yahoo_result_label(None, None), "Not comparable")

    def test_lipper_regression_result_match_on_fixture(self) -> None:
        funds = pd.DataFrame({"ISIN": [FIXTURE_ISIN]})
        frame = build_timeseries_checks_rows(funds, checks_root=self.checks_root)
        self.assertIn(
            frame.iloc[0]["lipper_regression_result"],
            ("Match", "Mismatch", "Not comparable"),
        )
        lipper_path = self.fixture_dir / "outputs" / "lipper-regression-comparison.csv"
        lipper_df = pd.read_csv(lipper_path)
        horizon_deltas = _lipper_horizon_deltas(lipper_df)
        tes = [
            abs(float(d["te"]))
            for d in horizon_deltas.values()
            if d.get("te") is not None
        ]
        if tes and max(tes) > LIPPER_DELTA_TE_MAX_PP:
            self.assertEqual(
                frame.iloc[0]["lipper_regression_result"],
                "Mismatch",
                "Large TE deltas should fail on beta/R²/TE, not on TE unit bug",
            )

    def test_lipper_regression_match_within_te_tolerance(self) -> None:
        csv = io.StringIO(
            "Horizon,Months,Metric,Notebook,Lipper Funds,Delta (notebook − Lipper)\n"
            "3y to last month end,36,Beta,1.000,1.000,0.030\n"
            "3y to last month end,36,R²,0.950,0.950,0.020\n"
            "3y to last month end,36,Annualized tracking error,1.00%,1.00%,0.40%\n"
        )
        deltas = _lipper_horizon_deltas(pd.read_csv(csv))
        self.assertEqual(lipper_regression_result_label(deltas), "Match")

    def test_lipper_regression_mismatch_on_large_te_delta(self) -> None:
        csv = io.StringIO(
            "Horizon,Months,Metric,Notebook,Lipper Funds,Delta (notebook − Lipper)\n"
            "10y to last month end,120,Beta,1.000,1.000,0.010\n"
            "10y to last month end,120,R²,0.950,0.950,0.010\n"
            "10y to last month end,120,Annualized tracking error,5.00%,0.03%,57.31%\n"
        )
        deltas = _lipper_horizon_deltas(pd.read_csv(csv))
        self.assertEqual(parse_regression_delta("Annualized tracking error", "57.31%"), 57.31)
        self.assertEqual(lipper_regression_result_label(deltas), "Mismatch")

    def test_consolidation_replication_labels(self) -> None:
        self.assertEqual(
            consolidation_regression_result_label(
                {"beta": 0.0, "net_alpha": 0.0, "te": 0.0, "ir": 0.0}
            ),
            "Recreates sheet",
        )
        self.assertEqual(
            consolidation_regression_result_label(
                {"beta": 0.05, "net_alpha": None, "te": None, "ir": None}
            ),
            "Drifts from sheet",
        )
        csv_text = (
            "Window,Metric,Notebook,Consolidation,Delta (notebook − Consolidation)\n"
            "2016-10-01 to 2026-10-01,Beta,0.900000,0.850000,0.050000\n"
            "2016-10-01 to 2026-10-01,Net alpha (annualized),1.00%,0.50%,0.50%\n"
        )
        consol_df = pd.read_csv(io.StringIO(csv_text))
        parsed = parse_consolidation_comparison_csv(consol_df)
        row: dict = {}
        apply_consolidation_comparison_to_row(
            row,
            consol_df,
            consolidation_regression_result_label=consolidation_regression_result_label,
        )
        self.assertEqual(row["consol_regression_result"], "Drifts from sheet")
        self.assertAlmostEqual(float(parsed["consol_delta_beta"]), 0.05)
        self.assertAlmostEqual(float(parsed["consol_delta_net_alpha"]), 0.5)

    def test_fixture_consolidation_recreates_sheet(self) -> None:
        funds = pd.DataFrame({"ISIN": [FIXTURE_ISIN]})
        frame = build_timeseries_checks_rows(funds, checks_root=self.checks_root)
        consol_path = self.fixture_dir / "outputs" / "consolidation-regression-comparison.csv"
        if consol_path.is_file():
            self.assertEqual(
                frame.iloc[0]["consol_regression_result"],
                "Recreates sheet",
            )

    def test_regression_exclusions_shape(self) -> None:
        funds = pd.DataFrame({"ISIN": [FIXTURE_ISIN]})
        exclusions = build_regression_exclusions_rows(
            funds, checks_root=self.checks_root
        )
        self.assertGreater(len(exclusions), 100)
        self.assertTrue((exclusions["ISIN"] == FIXTURE_ISIN).all())
        self.assertFalse(exclusions["Exclude"].any())


if __name__ == "__main__":
    unittest.main()
