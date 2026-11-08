import unittest

import altair as alt
import numpy as np
import pandas as pd

from helpers.timeseries_functions.compute_fund_to_index_regression import (
    compute_fund_to_index_regression,
)

INDEX = "S&P 500 TR"
MASTER = "Fund (Lipper)"


def _frame(index_return, fund_return) -> pd.DataFrame:
    dates = pd.date_range("2016-01-01", periods=len(index_return), freq="MS")
    return pd.DataFrame(
        {
            "Period": dates.strftime("%b %Y"),
            "Date": dates,
            INDEX: np.asarray(index_return, dtype=float),
            MASTER: np.asarray(fund_return, dtype=float),
        }
    )


class ComputeFundToIndexRegressionTests(unittest.TestCase):
    def test_exact_line(self):
        index_return = np.array([-0.02, 0.0, 0.01, 0.03])
        fund_return = 0.001 + 0.95 * index_return
        result = compute_fund_to_index_regression(
            _frame(index_return, fund_return),
            INDEX,
            MASTER,
            fund_name="Exact",
            quiet=True,
        )
        self.assertAlmostEqual(result.alpha, 0.001)
        self.assertAlmostEqual(result.beta, 0.95)
        self.assertAlmostEqual(result.r_squared, 1.0)
        self.assertEqual(result.n_months, 4)
        self.assertAlmostEqual(result.regression["alpha_annualized"], 0.012)
        self.assertAlmostEqual(result.regression["residual_se"], 0.0)

    def test_matches_normal_equations(self):
        index_return = np.array([0.01, -0.02, 0.03, 0.00, -0.01, 0.02])
        fund_return = np.array([0.012, -0.015, 0.025, 0.001, -0.008, 0.018])
        result = compute_fund_to_index_regression(
            _frame(index_return, fund_return),
            INDEX,
            MASTER,
            fund_name="Noisy",
            quiet=True,
        )
        design = np.column_stack([np.ones(len(index_return)), index_return])
        estimates, *_ = np.linalg.lstsq(design, fund_return, rcond=None)
        residual = fund_return - design @ estimates
        degrees = len(index_return) - 2
        residual_ss = float(residual @ residual)
        total_ss = float(((fund_return - fund_return.mean()) ** 2).sum())
        residual_se = float(np.sqrt(residual_ss / degrees))
        covariance = residual_se**2 * np.linalg.inv(design.T @ design)
        std_error = np.sqrt(np.diag(covariance))

        self.assertAlmostEqual(result.alpha, float(estimates[0]))
        self.assertAlmostEqual(result.beta, float(estimates[1]))
        self.assertAlmostEqual(result.r_squared, 1 - residual_ss / total_ss)
        self.assertAlmostEqual(result.regression["residual_se"], residual_se)
        np.testing.assert_allclose(
            result.coefficient_table["Std. error"].to_numpy(),
            std_error,
        )
        self.assertLess(
            result.coefficient_table.loc["Alpha", "95% low"],
            result.alpha,
        )
        self.assertGreater(
            result.coefficient_table.loc["Alpha", "95% high"],
            result.alpha,
        )
        self.assertEqual(
            list(result.coefficient_table.index),
            ["Alpha", "Beta"],
        )
        self.assertRegex(result.coefficient_table.loc["Beta", "p-value"], r"^(< 0\.0001|\d\.\d{4})$")

    def test_drops_missing_months_and_keeps_fund_statistics(self):
        index_return = np.array([-0.02, 0.0, 0.01, 0.03])
        fund_return = np.array([-0.01, 0.002, 0.004, 0.02])
        frame = _frame(index_return, fund_return)
        missing = pd.DataFrame(
            {
                "Period": ["Dec 2015"],
                "Date": [pd.Timestamp("2015-12-01")],
                INDEX: [np.nan],
                MASTER: [0.01],
            }
        )
        frame = pd.concat([missing, frame], ignore_index=True)
        result = compute_fund_to_index_regression(
            frame,
            INDEX,
            MASTER,
            fund_name="Gaps",
            quiet=True,
        )
        excess = fund_return - index_return
        expected_ratio = float(excess.mean() * 12) / float(
            np.std(excess, ddof=1) * np.sqrt(12)
        )
        self.assertEqual(result.n_months, 4)
        self.assertAlmostEqual(result.regression["information_ratio"], expected_ratio)
        self.assertAlmostEqual(
            result.regression["excess_annualized"],
            float(excess.mean() * 12),
        )
        self.assertIn("R²", result.fit_table.index)
        self.assertIsInstance(result.returns_chart, alt.TopLevelMixin)
        self.assertIsInstance(result.regression_chart, alt.TopLevelMixin)

    def test_requires_three_months(self):
        with self.assertRaisesRegex(ValueError, "at least 3 months"):
            compute_fund_to_index_regression(
                _frame([0.01, 0.02], [0.01, 0.02]),
                INDEX,
                MASTER,
                fund_name="Short",
                quiet=True,
            )


if __name__ == "__main__":
    unittest.main()
