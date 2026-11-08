import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from openpyxl import load_workbook

from helpers.timeseries_functions.save_timeseries_check import find_project_root
from helpers.timeseries_functions.write_timeseries_checks_excel import (
    EXCLUSIONS_SHEET_NAME,
    SHEET_NAME,
    write_timeseries_checks_excel,
)

FIXTURE_ISIN = "US3538257060"


class WriteTimeseriesChecksExcelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checks_root = find_project_root() / "output-data" / "timeseries-checks"
        if not (cls.checks_root / FIXTURE_ISIN).is_dir():
            raise unittest.SkipTest("Missing timeseries-check fixture")

    def test_writes_main_exclusions_and_methodology(self) -> None:
        funds = pd.DataFrame(
            {
                "ISIN": [FIXTURE_ISIN],
                "Name": ["Franklin Rising Dividends Fund;R"],
                "fund_wrapper": ["mutual fund"],
                "fund_type": ["Active"],
            }
        )
        with TemporaryDirectory() as tmp:
            dest = Path(tmp) / "CLEAN_RECOLTE DONNEES-EXCEL_timeseries-checks.xlsx"
            write_timeseries_checks_excel(
                funds, dest, checks_root=self.checks_root
            )
            self.assertTrue(dest.is_file())
            book = load_workbook(dest)
            self.assertIn(SHEET_NAME, book.sheetnames)
            self.assertIn(EXCLUSIONS_SHEET_NAME, book.sheetnames)
            self.assertIn("Methodology", book.sheetnames)

            main = book[SHEET_NAME]
            self.assertEqual(main["A1"].value, "Fund (Lipper)")
            self.assertEqual(main["A3"].value, FIXTURE_ISIN)

            excl = book[EXCLUSIONS_SHEET_NAME]
            self.assertEqual(excl["A1"].value, "ISIN")
            self.assertGreater(excl.max_row, 100)


if __name__ == "__main__":
    unittest.main()
