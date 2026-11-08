import unittest

import pandas as pd

from helpers.funds_functions.match_edgar_identifiers import match_edgar_identifiers


def _reference() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cik": 315774,
                "company_name": "FORUM FUNDS",
                "series_id": "S000004570",
                "series_name": "Auxier Focus Fund",
                "class_id": "C000012493",
                "class_name": "Investor Shares",
                "ticker": "AUXFX",
            },
            {
                "cik": 1,
                "company_name": "VALUE LINE",
                "series_id": "S1",
                "series_name": "Value Line Select Growth",
                "class_id": "C1",
                "class_name": "Investor",
                "ticker": "GROW",
            },
        ]
    )


class MatchEdgarIdentifiersTests(unittest.TestCase):
    def test_isin_flag_and_name(self):
        funds = pd.DataFrame(
            {
                "Name": [
                    "Auxier Focus Fund;Investor",
                    "Value Line Select Core Mutual Fund Investor Class",
                    "Missing Fund",
                    "Auxier Focus Fund;Investor",
                ],
                "ISIN": ["US3499031793", "US0000000001", "US0000000002", "US9999999999"],
                "CUSIP": ["349903179", "111111111", None, "349903179"],
            }
        )
        checked = match_edgar_identifiers(
            funds,
            fund_reference=_reference(),
            isin_tickers={"US3499031793": {"ticker": "AUXFX"}, "US0000000001": "GROW"},
        )

        self.assertEqual(checked["edgar_isin_found"].tolist(), [True, True, False, False])
        self.assertNotIn("edgar_cusip_found", checked.columns)
        self.assertNotIn("is_edgartools", checked.columns)
        self.assertEqual(checked["edgar_name"].iloc[0], "Auxier Focus Fund Investor Shares")
        self.assertEqual(checked["edgar_name_match"].tolist(), [True, False, False, False])
        self.assertEqual(checked["edgartools_class_id"].iloc[0], "C000012493")
        self.assertTrue(pd.isna(checked["edgar_name"].iloc[2]))
        self.assertTrue(pd.isna(checked["edgartools_cik"].iloc[3]))

    def test_column_order(self):
        funds = pd.DataFrame(
            {"Name": ["Auxier Focus Fund;Investor"], "ISIN": ["US3499031793"], "CUSIP": ["349903179"]}
        )
        checked = match_edgar_identifiers(
            funds,
            fund_reference=_reference(),
            isin_tickers={"US3499031793": "AUXFX"},
        )
        columns = list(checked.columns)
        self.assertLess(columns.index("Name"), columns.index("edgar_name"))
        self.assertLess(columns.index("edgar_name"), columns.index("edgar_name_match"))
        self.assertLess(columns.index("ISIN"), columns.index("edgar_isin_found"))


if __name__ == "__main__":
    unittest.main()
