import unittest

import pandas as pd

from helpers.funds_functions.filter_daily_timeseries import filter_daily_timeseries


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


if __name__ == "__main__":
    unittest.main()
