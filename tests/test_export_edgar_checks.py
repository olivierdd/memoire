import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import openpyxl
import pandas as pd

from helpers.funds_functions.edgar_checks_rows import (
    DATA_COLUMN_KEYS,
    benchmark_presence_result_label,
    benchmark_variant_result_label,
    build_edgar_checks_rows,
    default_decision_include,
    fund_type_result_label,
    wrapper_result_label,
)
from helpers.funds_functions.edgar_checks_methodology import METHODOLOGY_SHEET_NAME
from helpers.funds_functions.write_edgar_checks_excel import (
    SHEET_NAME,
    build_edgar_checks_frame,
    write_edgar_checks_excel,
)


class DecisionDefaultsTests(unittest.TestCase):
    def test_default_include_from_lipper_fund_type(self):
        self.assertTrue(default_decision_include("Active"))
        self.assertTrue(default_decision_include("To Check"))
        self.assertFalse(default_decision_include(None))
        self.assertFalse(default_decision_include("   "))


class ResultLabelTests(unittest.TestCase):
    def test_wrapper_match_mismatch_not_comparable(self):
        self.assertEqual(wrapper_result_label({"lipper_matches_edgar_wrapper": True}, "ETF"), "Match")
        self.assertEqual(wrapper_result_label({"lipper_matches_edgar_wrapper": False}, "ETF"), "Mismatch")
        self.assertEqual(wrapper_result_label({}, None), "Not comparable")

    def test_fund_type_not_comparable_when_lipper_unlabeled(self):
        comp = {"lipper_fund_type_normalized": "To Check", "lipper_matches_edgar_fund_type": False}
        self.assertEqual(fund_type_result_label(comp, "Active"), "Not comparable")

    def test_benchmark_presence_and_variant(self):
        comp = {"lipper_matches_edgar_sp500_presence": True}
        self.assertEqual(benchmark_presence_result_label(comp), "Match")
        comp2 = {
            "edgar_references_sp500": True,
            "lipper_references_sp500": True,
            "lipper_matches_edgar_sp500_variant": True,
        }
        self.assertEqual(benchmark_variant_result_label(comp2), "Match")


class BuildRowsTests(unittest.TestCase):
    def _minimal_funds(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ISIN": "US1111111111",
                    "Name": "Fund A",
                    "market_identifier": "AAA",
                    "fund_wrapper": "ETF",
                    "fund_type": "Active",
                    "Benchmark Name": "S&P 500 TR",
                    "is_S&P500": True,
                    "edgartools_series_id": "S000000001",
                },
            ]
        )

    def test_flat_frame_column_order(self):
        funds = self._minimal_funds()
        frame = build_edgar_checks_frame(funds)
        self.assertEqual(list(frame.columns)[0], "lipper_isin")
        self.assertEqual(len(frame.columns), len(DATA_COLUMN_KEYS))

    def test_edgar_fields_from_dq_cache_without_enriched_funds_row(self):
        funds = pd.DataFrame(
            [
                {
                    "ISIN": "US1111111111",
                    "Name": "Fund A",
                    "fund_wrapper": "ETF",
                    "fund_type": "Active",
                    "Benchmark Name": "S&P 500 TR",
                    "is_S&P500": True,
                }
            ]
        )
        filing_facts = {
            "S000000001": {
                "n_cen": {"filing_date": "2026-01-01", "series": {"name": "S"}},
                "prospectus": {"form": "485BPOS"},
            }
        }
        wrapper = {
            "records": {
                "US1111111111": {
                    "market_identifier": "AAA",
                    "edgartools_series_id": "S000000001",
                    "fund_wrapper": {"classification": "ETF", "source": "edgar_n_cen", "logic": "ok"},
                    "comparison": {"lipper_matches_edgar_wrapper": True},
                }
            }
        }
        df = build_edgar_checks_rows(
            funds,
            filing_facts=filing_facts,
            dq_wrapper=wrapper,
            dq_type={"records": {}},
            dq_benchmark={"records": {}},
            fund_reference_by_ticker={
                "AAA": {
                    "ticker": "AAA",
                    "cik": 1,
                    "series_id": "S000000001",
                    "class_id": "C1",
                    "company_name": "Co",
                    "series_name": "Series",
                    "class_name": "Inst",
                }
            },
        )
        self.assertEqual(df.iloc[0]["ticker"], "AAA")
        self.assertEqual(df.iloc[0]["ncen_filing_date"], "2026-01-01")
        self.assertEqual(list(df.columns), DATA_COLUMN_KEYS)
        self.assertTrue(df.iloc[0]["decision_include"])
        self.assertEqual(df.iloc[0]["decision_final_wrapper"], "ETF")
        self.assertEqual(df.iloc[0]["decision_final_type"], "Active")


class ExportWorkbookTests(unittest.TestCase):
    def test_single_sheet_workbook_from_scratch(self):
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "fixture.xlsx"
            dst = Path(tmp) / "fixture_edgar-checks.xlsx"
            openpyxl.Workbook().save(src)

            funds = pd.DataFrame(
                [
                    {
                        "ISIN": "US1",
                        "Name": "N",
                        "fund_wrapper": "ETF",
                        "fund_type": "Active",
                        "Benchmark Name": None,
                        "is_S&P500": False,
                    }
                ]
            )
            write_edgar_checks_excel(funds, dst)

            with zipfile.ZipFile(dst) as zf:
                sheet_parts = [
                    n
                    for n in zf.namelist()
                    if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
                ]
                self.assertEqual(
                    sheet_parts,
                    ["xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"],
                )

            out = openpyxl.load_workbook(dst)
            self.assertEqual(out.sheetnames, [SHEET_NAME, METHODOLOGY_SHEET_NAME])
            meth = out[METHODOLOGY_SHEET_NAME]
            combined = " ".join(
                str(meth.cell(r, 2).value or "") for r in range(1, meth.max_row + 1)
            )
            self.assertIn("N-CEN", combined)
            ws = out[SHEET_NAME]
            self.assertEqual(ws["A3"].value, "US1")
            self.assertEqual(ws.freeze_panes, "C3")


if __name__ == "__main__":
    unittest.main()
