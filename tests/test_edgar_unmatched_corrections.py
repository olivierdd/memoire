import json
import unittest
from pathlib import Path

import pandas as pd

from helpers.funds_functions.edgar_unmatched_corrections import (
    CLOSED_CORRECTIONS,
    NAME_CORRECTIONS,
    STATUS_CLOSED,
    STATUS_NAME,
    STATUS_TICKER,
    STATUS_UNMATCHABLE,
    UNMATCHABLE_CORRECTIONS,
    apply_edgar_unmatched_corrections,
    correction_catalog,
    correction_review,
)


def _reference() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cik": "0000893818",
                "company_name": "BlackRock Funds III",
                "series_id": "S000004272",
                "series_name": "iShares S&amp;P 500 Index Fund",
                "class_id": "C000117728",
                "class_name": "Service Shares",
                "ticker": None,
            },
            {
                "cik": 315774,
                "company_name": "FORUM FUNDS",
                "series_id": "S000004570",
                "series_name": "Auxier Focus Fund",
                "class_id": "C000012493",
                "class_name": "Investor Shares",
                "ticker": "AUXFX",
            },
        ]
    )


def _funds() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Name": [
                "iShares S&P 500 Index Fund;Service",
                "Johnson Disciplined Large-Cap Fund",
                "State Street SPDR S&P 500 ETF Trust",
                "Auxier Focus Fund;Investor",
                "Invesco Main Street All Cap Fund;Y",
            ],
            "ISIN": [
                "US0669235337",
                "US4791648656",
                "US78462F1030",
                "US3499031793",
                "US00141B7588",
            ],
            "openfigi_market_id": ["BSPSX", None, "SPY", "AUXFX", "OMSYX"],
            "edgar_isin_found": [False, False, False, True, False],
            "edgar_name": [None, None, None, "Auxier Focus Fund Investor Shares", None],
            "edgar_name_match": [False, False, False, True, False],
            "edgartools_cik": [None, None, None, "0000315774", None],
            "edgartools_series_id": [None, None, None, "S000004570", None],
            "edgartools_class_id": [None, None, None, "C000012493", None],
            "edgar_company_name": [None, None, None, "FORUM FUNDS", None],
            "edgar_series_name": [None, None, None, "Auxier Focus Fund", None],
            "edgar_class_name": [None, None, None, "Investor Shares", None],
        }
    )


class EdgarUnmatchedCorrectionTests(unittest.TestCase):
    def test_catalog_covers_each_reviewed_fund_once(self):
        isins = [row[0] for row in (*NAME_CORRECTIONS, *CLOSED_CORRECTIONS, *UNMATCHABLE_CORRECTIONS)]
        self.assertEqual(len(isins), 43)
        self.assertEqual(len(isins), len(set(isins)))
        self.assertEqual(len(NAME_CORRECTIONS), 34)
        self.assertEqual(len(CLOSED_CORRECTIONS), 6)
        self.assertEqual(len(UNMATCHABLE_CORRECTIONS), 3)
        catalog = correction_catalog()
        self.assertEqual(catalog["category"].tolist().count(STATUS_NAME), 34)
        self.assertEqual(catalog["class_id"].dropna().nunique(), 34)

    def test_name_match_fills_the_series_and_leaves_the_other_groups_empty(self):
        checked = apply_edgar_unmatched_corrections(_funds(), _reference())

        service = checked.loc[checked["ISIN"].eq("US0669235337")].iloc[0]
        self.assertTrue(service["edgar_isin_found"])
        self.assertEqual(service["edgar_match_status"], STATUS_NAME)
        self.assertEqual(service["edgartools_class_id"], "C000117728")
        self.assertEqual(service["edgartools_series_id"], "S000004272")
        self.assertEqual(service["edgartools_cik"], "0000893818")
        self.assertEqual(service["edgar_series_name"], "iShares S&P 500 Index Fund")
        self.assertTrue(service["edgar_name_match"])

        closed = checked.loc[checked["ISIN"].eq("US4791648656")].iloc[0]
        self.assertFalse(closed["edgar_isin_found"])
        self.assertEqual(closed["edgar_match_status"], STATUS_CLOSED)
        self.assertIsNone(closed["edgartools_class_id"])
        self.assertIn("16 December 2011", closed["edgar_match_note"])

        spy = checked.loc[checked["ISIN"].eq("US78462F1030")].iloc[0]
        self.assertFalse(spy["edgar_isin_found"])
        self.assertEqual(spy["edgar_match_status"], STATUS_UNMATCHABLE)
        self.assertIsNone(spy["edgartools_series_id"])

        ticker = checked.loc[checked["ISIN"].eq("US3499031793")].iloc[0]
        self.assertEqual(ticker["edgar_match_status"], STATUS_TICKER)
        self.assertEqual(ticker["edgartools_class_id"], "C000012493")
        self.assertTrue(ticker["edgar_isin_found"])

        missing_class = checked.loc[checked["ISIN"].eq("US00141B7588")].iloc[0]
        self.assertFalse(missing_class["edgar_isin_found"])
        self.assertIsNone(missing_class["edgar_match_status"])
        self.assertIn("C000209245", missing_class["edgar_match_note"])

    def test_review_marks_rows_once_the_status_is_on_the_fund(self):
        before = correction_review(_funds())
        self.assertEqual(before["applied"].tolist(), ["no"] * len(before))
        checked = apply_edgar_unmatched_corrections(_funds(), _reference())
        after = correction_review(checked)
        applied = dict(zip(after["ISIN"], after["applied"]))
        self.assertEqual(applied["US0669235337"], "yes")
        self.assertEqual(applied["US4791648656"], "yes")
        self.assertEqual(applied["US78462F1030"], "yes")
        self.assertEqual(applied["US00141B7588"], "no")

    def test_name_corrections_match_the_sec_reference_cache(self):
        cache = Path(__file__).resolve().parents[1] / "cache" / "cache-edgar-fund-data.json"
        if not cache.is_file():
            self.skipTest("EDGAR fund reference cache is not on disk")
        reference = pd.DataFrame(json.loads(cache.read_text())["records"])
        for isin, class_id, series_id, _detail in NAME_CORRECTIONS:
            hits = reference.loc[reference["class_id"].eq(class_id)]
            self.assertEqual(len(hits), 1, isin)
            self.assertEqual(hits.iloc[0]["series_id"], series_id, isin)


if __name__ == "__main__":
    unittest.main()
