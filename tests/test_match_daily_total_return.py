import unittest

import pandas as pd

from helpers.funds_functions.match_daily_total_return import (
    datastream_names_match,
    match_daily_total_return,
)


def _sheet(columns: list[tuple[str, str, list]]) -> pd.DataFrame:
    """Build a D-Timeseries frame from (id, name, observations)."""
    width = len(columns) + 1
    rows: list[list] = [[None] * width for _ in range(6)]
    rows[0][0] = "id"
    rows[1][0] = "name"
    rows[4][0] = "Note"
    rows[5][0] = "Date"
    longest = max((len(values) for _, _, values in columns), default=1)
    data = [[None] * width for _ in range(longest)]
    for position, (identifier, name, values) in enumerate(columns, start=1):
        rows[0][position] = identifier
        rows[1][position] = f"{name} - TOT RETURN IND"
        rows[4][position] = "Total return index, daily"
        for offset, value in enumerate(values):
            data[offset][position] = value
    return pd.DataFrame(rows + data)


class DatastreamNameTests(unittest.TestCase):
    def test_accepts_datastream_short_forms(self):
        self.assertTrue(
            datastream_names_match(
                "AUXIER FCS.FD.INVR.SHS.",
                "Auxier Focus Fund;Investor",
            )
        )
        self.assertTrue(
            datastream_names_match(
                "PRCL.FUND.LGCP.S&P 500 IDX.FD.INSTL.CL.",
                "Principal LargeCap S&P 500 Index Fund;Inst",
            )
        )
        self.assertTrue(datastream_names_match("GMO QLT.FUND CLASS VI", "GMO Quality Fund;VI"))
        self.assertTrue(
            datastream_names_match(
                "NYLIM PINE STONE US EQUITY FUND I",
                "NYLIM PineStone US Equity Fund;I",
            )
        )

    def test_rejects_a_different_product_word(self):
        self.assertFalse(
            datastream_names_match(
                "GLDS.STRUCD.US.EQ.FD. CL.A",
                "Goldman Sachs US Equity Insights Fund;A",
            )
        )
        self.assertFalse(
            datastream_names_match(
                "BROWN ADVISORY FLEXIBLE VAL.FD.INSTL.SHS.",
                "Brown Advisory Flexible Equity Fund;Institutional",
            )
        )
        self.assertFalse(datastream_names_match("SEQUOIA ETF", "Sequoia Fund"))
        self.assertFalse(
            datastream_names_match(
                "MFS UN.STD.EQ.FD.CL.C",
                "MFS Blended Research Core Equity Mutual fund Class C",
            )
        )


class MatchDailyTotalReturnTests(unittest.TestCase):
    def test_matches_on_isin_and_confirms_the_sheet_name(self):
        funds = pd.DataFrame(
            [
                {
                    "Name": "Auxier Focus Fund;Investor",
                    "ISIN": "US3499031793",
                    "openfigi_name": "AUXIER FOCUS FUND-INV",
                    "edgar_name": None,
                }
            ]
        )
        daily = _sheet([("US3499031793", "AUXIER FCS.FD.INVR.SHS.", [1.0, 2.0])])

        out = match_daily_total_return(funds, daily)

        self.assertTrue(out.loc[0, "has_daily_total_return"])
        self.assertEqual(out.loc[0, "daily_tr_observations"], 2)
        self.assertEqual(out.loc[0, "daily_tr_name"], "AUXIER FCS.FD.INVR.SHS.")
        self.assertTrue(out.loc[0, "daily_tr_name_match"])
        self.assertEqual(out.loc[0, "daily_tr_name_source"], "Name")

    def test_uses_openfigi_when_the_sheet_name_omits_the_sponsor(self):
        funds = pd.DataFrame(
            [
                {
                    "Name": "Washington Mutual Investors Mutual Fund Class 529 A",
                    "ISIN": "US9393305027",
                    "openfigi_name": "AMER FND WASH MUT INV-529A",
                    "edgar_name": None,
                }
            ]
        )
        daily = _sheet(
            [("US9393305027", "AMERICAN FDS WASHINGTON MUTUAL INV FD 529-A", [1.0])]
        )

        out = match_daily_total_return(funds, daily)

        self.assertTrue(out.loc[0, "has_daily_total_return"])
        self.assertTrue(out.loc[0, "daily_tr_name_match"])
        self.assertEqual(out.loc[0, "daily_tr_name_source"], "openfigi_name")

    def test_keeps_a_series_when_every_name_disagrees(self):
        funds = pd.DataFrame(
            [
                {
                    "Name": "Goldman Sachs US Equity Insights Fund;A",
                    "ISIN": "US38141W6205",
                    "openfigi_name": "GLDMN SCHS US EQTY INSG-A",
                    "edgar_name": "Goldman Sachs US Equity Insights Fund Class A",
                }
            ]
        )
        daily = _sheet([("US38141W6205", "GLDS.STRUCD.US.EQ.FD. CL.A", [1.0, None, 3.0])])

        out = match_daily_total_return(funds, daily)

        self.assertTrue(out.loc[0, "has_daily_total_return"])
        self.assertEqual(out.loc[0, "daily_tr_observations"], 2)
        self.assertFalse(out.loc[0, "daily_tr_name_match"])
        self.assertIsNone(out.loc[0, "daily_tr_name_source"])

    def test_ignores_an_empty_series(self):
        funds = pd.DataFrame([{"Name": "Auxier Focus Fund;Investor", "ISIN": "US3499031793"}])
        daily = _sheet([("US3499031793", "AUXIER FCS.FD.INVR.SHS.", [None, None])])

        out = match_daily_total_return(funds, daily)

        self.assertFalse(out.loc[0, "has_daily_total_return"])
        self.assertEqual(out.loc[0, "daily_tr_observations"], 0)

    def test_matches_a_column_without_an_isin_by_name(self):
        funds = pd.DataFrame(
            [
                {"Name": "Franklin Managed Trust Dividend Portfolio;C", "ISIN": "US0000000000"},
                {"Name": "Other Fund", "ISIN": "US1111111111"},
            ]
        )
        daily = _sheet(
            [
                (
                    "FRANKLIN MGD.TST.RDV. PRTF.CII",
                    "FRANKLIN MGD.TST.RDV. PRTF.CII",
                    [4.0],
                )
            ]
        )

        out = match_daily_total_return(funds, daily)

        self.assertTrue(out.loc[0, "has_daily_total_return"])
        self.assertEqual(out.loc[0, "daily_tr_name_source"], "Name")
        self.assertFalse(out.loc[1, "has_daily_total_return"])

    def test_does_not_assign_one_series_to_two_funds(self):
        funds = pd.DataFrame(
            [
                {"Name": "Auxier Focus Fund;Investor", "ISIN": "US0000000000"},
                {"Name": "Auxier Focus Fund;Investor", "ISIN": "US1111111111"},
            ]
        )
        daily = _sheet([("AUXIER MNEMONIC", "AUXIER FCS.FD.INVR.SHS.", [1.0])])

        out = match_daily_total_return(funds, daily)

        self.assertFalse(out["has_daily_total_return"].any())


if __name__ == "__main__":
    unittest.main()
