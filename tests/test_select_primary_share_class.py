import unittest

import pandas as pd

from helpers.funds_functions.select_primary_share_class import select_primary_share_class


def _row(
    series_id: str | None,
    class_id: str,
    *,
    series_name: str = "Example Fund",
    class_name: str = "Class A",
    company: str = "Example Trust",
    aum: float | None = None,
    isin: str = "US0000000000",
) -> dict:
    return {
        "edgartools_series_id": series_id,
        "edgartools_class_id": class_id,
        "edgar_series_name": series_name,
        "edgar_class_name": class_name,
        "edgar_company_name": company,
        "Fund Total Assets under Management": aum,
        "ISIN": isin,
        "edgartools_cik": "0000000001",
    }


class PrimaryShareClassTests(unittest.TestCase):
    def test_largest_aum_beats_a_more_retail_class(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C1", class_name="Investor Shares", aum=1, isin="US1"),
                _row("S1", "C2", class_name="ETF Shares", aum=10, isin="US2"),
            ]
        )
        kept, dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].tolist(), ["US2"])
        self.assertEqual(kept["primary_rule"].iloc[0], "largest aum")
        self.assertEqual(dropped["kept_isin"].tolist(), ["US2"])

    def test_blank_aum_does_not_count_as_zero(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C1", class_name="Admiral Shares", aum=None, isin="US1"),
                _row("S1", "C2", class_name="ETF Shares", aum=5, isin="US2"),
            ]
        )
        kept, _dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].iloc[0], "US2")

    def test_no_aum_keeps_investor_ahead_of_admiral(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C2", class_name="Admiral Shares", isin="US2"),
                _row("S1", "C1", class_name="Investor Shares", isin="US1"),
            ]
        )
        kept, _dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].iloc[0], "US1")
        self.assertEqual(kept["primary_rule"].iloc[0], "class rank")

    def test_unsuffixed_retail_beats_advisor_class_a(self):
        frame = pd.DataFrame(
            [
                _row(
                    "S1",
                    "C9",
                    series_name="Fidelity Magellan Fund",
                    class_name="Fidelity Advisor Magellan Fund: Class A",
                    isin="US9",
                ),
                _row(
                    "S1",
                    "C1",
                    series_name="Fidelity Magellan Fund",
                    class_name="Fidelity Magellan Fund",
                    isin="US1",
                ),
            ]
        )
        kept, _dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].iloc[0], "US1")

    def test_class_a_beats_a_529_class(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C9", class_name="Class 529-A", isin="US9"),
                _row("S1", "C1", class_name="Class A", isin="US1"),
            ]
        )
        kept, _dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].iloc[0], "US1")

    def test_gabelli_aaa_beats_class_a(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C2", class_name="Class A", company="GABELLI VALUE 25 FUND INC", isin="US2"),
                _row("S1", "C1", class_name="Class AAA", company="GABELLI VALUE 25 FUND INC", isin="US1"),
            ]
        )
        kept, _dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].iloc[0], "US1")

    def test_tied_aum_uses_the_class_name(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C2", class_name="Admiral Shares", aum=5, isin="US2"),
                _row("S1", "C1", class_name="Investor Shares", aum=5, isin="US1"),
            ]
        )
        kept, _dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].iloc[0], "US1")
        self.assertEqual(kept["primary_rule"].iloc[0], "class rank")

    def test_tied_class_rank_keeps_the_smallest_class_id(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C000000020", class_name="Class R6", isin="US2"),
                _row("S1", "C000000003", class_name="Class C", isin="US1"),
            ]
        )
        kept, _dropped = select_primary_share_class(frame)
        self.assertEqual(kept["ISIN"].iloc[0], "US1")
        self.assertEqual(kept["primary_rule"].iloc[0], "smallest class id")

    def test_different_series_of_one_registrant_both_stay(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C1", isin="US1"),
                _row("S2", "C2", series_name="Other Fund", isin="US2"),
            ]
        )
        kept, dropped = select_primary_share_class(frame)
        self.assertEqual(set(kept["ISIN"]), {"US1", "US2"})
        self.assertTrue(dropped.empty)

    def test_rows_without_a_series_stay(self):
        frame = pd.DataFrame(
            [
                _row(None, "C1", isin="US1"),
                _row(None, "C2", isin="US2"),
            ]
        )
        kept, dropped = select_primary_share_class(frame)
        self.assertEqual(len(kept), 2)
        self.assertTrue(dropped.empty)
        self.assertEqual(set(kept["primary_rule"]), {"no series"})

    def test_a_series_with_one_class_is_unchanged(self):
        frame = pd.DataFrame([_row("S1", "C1", isin="US1")])
        kept, dropped = select_primary_share_class(frame)
        self.assertEqual(kept["primary_rule"].iloc[0], "only class")
        self.assertTrue(dropped.empty)
