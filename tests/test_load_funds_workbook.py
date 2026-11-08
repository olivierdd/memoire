import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from helpers.funds_functions.load_workbook import (
    find_workbook,
    load_workbook,
    subgroup_counts,
)


class FindWorkbookTests(unittest.TestCase):
    def test_walks_parents_until_the_workbook_exists(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = root / "input-data-alix" / "clean" / "funds.xlsx"
            workbook.parent.mkdir(parents=True)
            workbook.write_bytes(b"")
            nested = root / "notebooks" / "drafts"
            nested.mkdir(parents=True)

            found = find_workbook(
                Path("input-data-alix") / "clean" / "funds.xlsx",
                start=nested,
            )

        self.assertEqual(found, workbook.resolve())

    def test_missing_workbook_names_the_start_directory(self):
        with TemporaryDirectory() as tmp:
            start = Path(tmp)
            with self.assertRaises(FileNotFoundError) as raised:
                find_workbook(Path("missing.xlsx"), start=start)

        self.assertIn(str(start.resolve()), str(raised.exception))


class LoadWorkbookTests(unittest.TestCase):
    def test_reads_the_funds_sheet_and_adds_its_funds_package(self):
        with TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "funds.xlsx"
            frame = pd.DataFrame(
                {
                    "ISIN": ["US1234567890"],
                    "RIC": ["ABC.N"],
                    "fund_wrapper": ["ETF"],
                    "fund_type": ["Active"],
                }
            )
            frame.to_excel(workbook, sheet_name="Funds", index=False)
            funds_dir = str(workbook.parent / "funds")
            sys.path = [entry for entry in sys.path if entry != funds_dir]

            loaded = load_workbook(workbook)

            self.assertEqual(sys.path[0], funds_dir)
            self.assertEqual(loaded["ISIN"].tolist(), ["US1234567890"])
            self.assertEqual(loaded["ISIN"].dtype, "string")
            self.assertEqual(loaded["RIC"].dtype, "string")
            sys.path.remove(funds_dir)


class SubgroupCountTests(unittest.TestCase):
    def test_counts_each_wrapper_and_type(self):
        funds = pd.DataFrame(
            {
                "fund_wrapper": ["ETF", "ETF", "mutual fund"],
                "fund_type": ["Active", "Active", "Passive"],
            }
        )

        counts = subgroup_counts(funds)

        self.assertEqual(
            counts.to_dict("records"),
            [
                {"fund_wrapper": "ETF", "fund_type": "Active", "count": 2},
                {"fund_wrapper": "mutual fund", "fund_type": "Passive", "count": 1},
            ],
        )


if __name__ == "__main__":
    unittest.main()
