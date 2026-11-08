import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pptx import Presentation

from helpers.timeseries_functions.fund_llm_dossier import timeseries_check_dir
from helpers.timeseries_functions.fund_timeseries_report import (
    REPORT_FILENAME,
    load_report_data,
)
from helpers.timeseries_functions.run_fund_batch import (
    _CHECK_MARKERS,
    combine_fund_reports,
    fund_check_dir,
    funds_with_timeseries,
    saved_fund_outputs,
)
from helpers.timeseries_functions.save_timeseries_check import find_project_root

SAMPLE_ISIN = "US4613088016"


class RunFundBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sample_report = (
            timeseries_check_dir(SAMPLE_ISIN, project_root=find_project_root())
            / "outputs/fund-timeseries-report.pptx"
        )

    def test_funds_with_timeseries_keeps_numeric_columns_only(self) -> None:
        timeseries_df = pd.DataFrame(
            {
                "id": ["name", "category", "2010-01-01", "2010-02-01"],
                "US1111111111": ["Fund A", "Active MF", None, 0.01],
                "US2222222222": ["Fund B", "Active MF", None, None],
                "not-an-isin": ["x", "y", 1.0, 2.0],
            }
        )
        funds = pd.DataFrame(
            {
                "ISIN": ["US1111111111", "US2222222222"],
                "Name": ["Fund A", "Fund B"],
            }
        )
        eligible = funds_with_timeseries(timeseries_df, funds)
        self.assertEqual(eligible["ISIN"].tolist(), ["US1111111111"])
        self.assertNotIn("not-an-isin", eligible.columns)

    def test_saved_fund_outputs_detects_sample_fund(self) -> None:
        if not self.sample_report.is_file():
            self.skipTest("sample fund report missing")
        root = find_project_root() / "output-data" / "timeseries-checks"
        cached = saved_fund_outputs(SAMPLE_ISIN, checks_root=root)
        self.assertIsNotNone(cached)
        check_dir, report_path = cached  # type: ignore[misc]
        self.assertEqual(check_dir, fund_check_dir(SAMPLE_ISIN, checks_root=root))
        self.assertEqual(report_path, self.sample_report)

    def test_saved_fund_outputs_respects_require_llm_and_require_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            isin = "US0000000001"
            check_dir = fund_check_dir(isin, checks_root=root)
            for relative in _CHECK_MARKERS:
                path = check_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            llm_path = check_dir / "outputs/llm-evaluation-openai.json"
            llm_path.parent.mkdir(parents=True, exist_ok=True)
            llm_path.write_text("{}", encoding="utf-8")
            report_path = check_dir / REPORT_FILENAME
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_bytes(b"pptx")

            self.assertIsNotNone(
                saved_fund_outputs(
                    isin,
                    require_llm=False,
                    require_report=False,
                    checks_root=root,
                )
            )
            cached = saved_fund_outputs(
                isin,
                require_llm=False,
                require_report=True,
                checks_root=root,
            )
            self.assertIsNotNone(cached)
            assert cached is not None
            self.assertEqual(cached[1], report_path)

            llm_path.unlink()
            self.assertIsNone(
                saved_fund_outputs(
                    isin,
                    require_llm=True,
                    require_report=False,
                    checks_root=root,
                )
            )
            self.assertIsNotNone(
                saved_fund_outputs(
                    isin,
                    require_llm=False,
                    require_report=False,
                    checks_root=root,
                )
            )

            report_path.unlink()
            self.assertIsNone(
                saved_fund_outputs(
                    isin,
                    require_llm=False,
                    require_report=True,
                    checks_root=root,
                )
            )

    def test_combine_fund_reports_duplicates_slide_with_images(self) -> None:
        if not self.sample_report.is_file():
            self.skipTest("sample fund report missing")
        equation = load_report_data(
            timeseries_check_dir(SAMPLE_ISIN, project_root=find_project_root())
        ).regression["equation"]

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "combined.pptx"
            combine_fund_reports([self.sample_report, self.sample_report], dest)
            deck = Presentation(str(dest))
            self.assertEqual(len(deck.slides), 2)
            for slide in deck.slides:
                text = _slide_text(slide)
                self.assertIn(SAMPLE_ISIN, text)
                self.assertIn(equation, text)
                pictures = sum(1 for shape in slide.shapes if shape.shape_type == 13)
                self.assertGreaterEqual(pictures, 2)


def _slide_text(slide) -> str:
    parts: list[str] = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            parts.append(shape.text_frame.text)
        elif shape.has_table:
            parts.extend(cell.text for row in shape.table.rows for cell in row.cells)
    return "\n".join(parts)


if __name__ == "__main__":
    unittest.main()
