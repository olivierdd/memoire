import unittest

import pandas as pd

from helpers.funds_functions.filter_daily_timeseries import (
    backfill_fees_from_funds,
    coerce_fee_value,
    fee_from_fund_row,
    filter_daily_timeseries,
)


def _sheet() -> pd.DataFrame:
    rows = [
        [
            "id",
            "S&P 500 Composite TR",
            "US T-Bill 3M",
            "US1111111111",
            "US2222222222",
            None,
            None,
            "#ERROR (invalid code)",
        ],
        [
            "name",
            "S&P 500 COMPOSITE - TOT RETURN IND",
            "US TREASURY BILL RATE - 3 MONTH (EP) NADJ",
            "KEPT FUND - TOT RETURN IND",
            "DROPPED FUND - PRICE",
            None,
            "KEPT FUND - TOT RETURN IND - daily return",
            "#ERROR (invalid Datastream code)",
        ],
        [
            "category",
            "Index",
            "Risk-free rate",
            "Active MF",
            "Passive MF",
            None,
            None,
            None,
        ],
        ["fee (%/year)", None, None, 0.5, 0.2, None, None, None],
        [
            "Note",
            "Total return index, daily",
            "Annualised rate in %, monthly (month-end)",
            "Total return index, daily",
            "Price, daily",
            None,
            "Daily simple return = P(t)/P(t-1) - 1",
            "Total return index, daily",
        ],
        ["Date", "2020-01-02", 1.5, 100, 50, None, 0.01, None],
    ]
    return pd.DataFrame(rows)


class FilterDailyTimeseriesTests(unittest.TestCase):
    def test_keeps_remaining_funds_with_the_index_and_risk_free_rate(self):
        filtered, roles = filter_daily_timeseries(
            _sheet(),
            kept_isins=["US1111111111"],
            kept_labels=["KEPT FUND"],
        )

        self.assertEqual(
            list(filtered.iloc[0]),
            [
                "id",
                "S&P 500 Composite TR",
                "US T-Bill 3M",
                "US1111111111",
                None,
            ],
        )
        self.assertEqual(
            roles,
            ["labels", "index", "risk-free rate", "fund", "fund"],
        )
        self.assertEqual(filtered.iloc[1, 4], "KEPT FUND - TOT RETURN IND - daily return")

    def test_drops_a_name_match_that_is_not_a_remaining_fund(self):
        filtered, roles = filter_daily_timeseries(
            _sheet(),
            kept_isins=[],
            kept_labels=[],
        )

        self.assertEqual(list(filtered.iloc[0]), ["id", "S&P 500 Composite TR", "US T-Bill 3M"])
        self.assertEqual(roles, ["labels", "index", "risk-free rate"])

    def test_coerce_fee_value_accepts_comma_decimals(self):
        self.assertEqual(coerce_fee_value("0,09"), 0.09)
        self.assertEqual(coerce_fee_value(0.51), 0.51)
        self.assertIsNone(coerce_fee_value(""))
        self.assertIsNone(coerce_fee_value(None))

    def test_fee_from_fund_row_reads_known_ter_columns(self):
        row = pd.Series({"ISIN": "US1111111111", "Total Expense Ratio": 0.82})
        self.assertEqual(fee_from_fund_row(row), 0.82)
        row_ds = pd.Series({"ISIN": "US1111111111", "ds.total_expense_ratio": "0,20"})
        self.assertEqual(fee_from_fund_row(row_ds), 0.2)

    def test_backfill_fees_from_funds_fills_blank_yahoo_columns(self):
        daily = _sheet()
        # Blank fee on the kept fund column (simulates Yahoo append with fee=None).
        daily.iat[3, 3] = None
        funds = pd.DataFrame(
            {
                "ISIN": ["US1111111111"],
                "Total Expense Ratio": [0.82],
            }
        )
        filled, n = backfill_fees_from_funds(daily, funds)
        self.assertEqual(n, 1)
        self.assertEqual(filled.iat[3, 3], 0.82)
        # Existing fees are left alone.
        self.assertEqual(filled.iat[3, 4], 0.2)


if __name__ == "__main__":
    unittest.main()
