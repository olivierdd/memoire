import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from helpers.format_excel.constants import VISIBLE_SHEETS
from helpers.format_excel.enrich_funds_selection import enrich_funds_selection
from helpers.format_excel.retarget_formulas import build_retarget_spec, retarget_formula
from helpers.format_excel.sheet_visibility import apply_sheet_visibility

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_INPUT = REPO_ROOT / "output-data" / "v2-funds-normalized-cleaned.xlsx"
REFERENCE_TEMPLATE = (
    REPO_ROOT / "usefull-references" / "v2-funds-normalized-formatted-v3.xlsx"
)


class RetargetFormulaTests(unittest.TestCase):
    def test_replaces_template_dimensions(self):
        spec = build_retarget_spec(
            funds_last_row=2000,
            dts_last_row=2500,
            dts_last_col="ZZZ",
            select_outcome_col="CY",
            select_quality_col="CZ",
        )
        formula = (
            "=INDEX('D-Timeseries final'!$A$7:$BGI$2877,1,"
            "MATCH($I$1,Funds!$BN$2:$BN$2611))"
        )
        updated = retarget_formula(formula, spec)
        self.assertIn("$ZZZ$2500", updated)
        self.assertIn("$CY$", updated)
        self.assertNotIn("BGI", updated)
        self.assertNotIn("2611", updated)


class EnrichSelectionTests(unittest.TestCase):
    def test_select_columns_match_funds_final(self):
        workbook = Workbook()
        funds = workbook.active
        funds.title = "Funds"
        funds.append(["ds.isin", "ds.name"])
        funds.append(["US111", "One"])
        funds.append(["US222", "Two"])
        final = workbook.create_sheet("Funds final")
        final.append(["ISIN", "Name"])
        final.append(["US111", "One"])

        selection = enrich_funds_selection(workbook)
        headers = {cell.value: cell.column for cell in funds[1]}
        outcome_col = headers["select.outcome"]
        self.assertTrue(funds.cell(row=2, column=outcome_col).value)
        self.assertFalse(funds.cell(row=3, column=outcome_col).value)
        from openpyxl.utils import get_column_letter

        self.assertEqual(
            selection["select_outcome"],
            get_column_letter(outcome_col),
        )


class SheetVisibilityTests(unittest.TestCase):
    def test_only_analysis_tabs_visible(self):
        workbook = Workbook()
        workbook.active.title = "Funds"
        workbook.create_sheet("Funds final")
        workbook.create_sheet("Extra")
        states = apply_sheet_visibility(workbook)
        self.assertEqual(states["Funds"], "hidden")
        self.assertEqual(states["Funds final"], "visible")
        self.assertEqual(states["Extra"], "hidden")
        for name in VISIBLE_SHEETS:
            if name in workbook.sheetnames:
                self.assertEqual(
                    workbook[name].sheet_state, Worksheet.SHEETSTATE_VISIBLE
                )


@unittest.skipUnless(
    PIPELINE_INPUT.is_file() and REFERENCE_TEMPLATE.is_file(),
    "requires cleaned workbook and reference template",
)
class FormatWorkbookIntegrationTests(unittest.TestCase):
    def test_format_produces_loadable_workbook(self):
        from helpers.format_excel.format_workbook import format_workbook

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "formatted.xlsx"
            result = format_workbook(PIPELINE_INPUT, output)
            self.assertTrue(output.is_file())
            self.assertEqual(result.select_outcome_col, "CY")
            visible = [n for n, s in result.sheet_states.items() if s == "visible"]
            self.assertEqual(
                set(visible),
                set(VISIBLE_SHEETS) & set(result.sheet_states.keys()),
            )

            from openpyxl import load_workbook

            workbook = load_workbook(output, read_only=True)
            try:
                self.assertIn("Fund Analysis", workbook.sheetnames)
                self.assertEqual(
                    workbook["Funds final"].sheet_state, Worksheet.SHEETSTATE_VISIBLE
                )
            finally:
                workbook.close()


if __name__ == "__main__":
    unittest.main()