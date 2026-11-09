import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.write_excel import write_excel


class WriteExcelTests(unittest.TestCase):
    def test_round_trip_keeps_values_and_header(self):
        frame = pd.DataFrame({"ISIN": ["US1234567890"], "name": ["Example"]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funds.xlsx"

            written = write_excel(frame, path)

            self.assertEqual(written, path)
            loaded = pd.read_excel(path, dtype={"ISIN": "string"})
            self.assertEqual(loaded["ISIN"].tolist(), ["US1234567890"])
            self.assertEqual(loaded["name"].tolist(), ["Example"])

    def test_header_false_writes_the_values_as_the_first_row(self):
        frame = pd.DataFrame([["label", "US1234567890"]])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.xlsx"

            write_excel(frame, path, header=False)

            loaded = pd.read_excel(path, header=None, dtype="string")
            self.assertEqual(loaded.iloc[0].tolist(), ["label", "US1234567890"])

    def test_replaces_an_existing_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funds.xlsx"
            path.write_bytes(b"not a workbook")

            write_excel(pd.DataFrame({"n": [1]}), path)

            loaded = pd.read_excel(path)
            self.assertEqual(loaded["n"].tolist(), [1])

    def test_builds_the_workbook_outside_the_destination_folder(self):
        frame = pd.DataFrame({"n": [1]})
        written_to: list[Path] = []
        original = pd.DataFrame.to_excel

        def spy(self, excel_writer, *args, **kwargs):
            written_to.append(Path(excel_writer))
            return original(self, excel_writer, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            pd.DataFrame, "to_excel", spy
        ):
            destination = Path(tmp) / "output-data" / "funds.xlsx"
            write_excel(frame, destination)

            self.assertEqual(len(written_to), 1)
            self.assertNotEqual(written_to[0].parent, destination.parent)
            self.assertFalse(written_to[0].exists())
            self.assertTrue(destination.is_file())
            self.assertEqual(list(destination.parent.iterdir()), [destination])
