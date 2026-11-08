import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from pptx import Presentation

from helpers.timeseries_functions.fund_llm_dossier import timeseries_check_dir
from helpers.timeseries_functions.fund_timeseries_report import (
    CHART_SHAPES,
    NO_LLM,
    REPORT_FILENAME,
    TEMPLATE_PATH,
    load_report_data,
    report_values,
    write_fund_timeseries_report,
)
from helpers.timeseries_functions.save_timeseries_check import find_project_root

SAMPLE_ISIN = "US4613088016"


class FundTimeseriesReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check_dir = timeseries_check_dir(
            SAMPLE_ISIN, project_root=find_project_root()
        )

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_report_values_cover_quality_checks_and_fit_table(self) -> None:
        values = report_values(load_report_data(self.check_dir), datetime.now())
        self.assertEqual(values["isin"], SAMPLE_ISIN)
        self.assertEqual(values["matched_months"], "200")
        self.assertEqual(values["fit_f_pvalue"], "< 0.0001")
        checks = values["quality_checks"]
        self.assertIn("Gaps: none", checks)
        self.assertTrue(all("Yahoo" not in line for line in checks))
        self.assertFalse(any("2020-04-01" in line for line in checks))

    def test_report_fills_every_token_and_both_charts(self) -> None:
        out = write_fund_timeseries_report(
            self.check_dir, output_path=self.tmp / "report.pptx"
        )
        deck = Presentation(str(out))
        self.assertEqual(len(deck.slides), 1)
        slide = deck.slides[0]
        text = _slide_text(slide)
        self.assertNotRegex(text, r"\{[a-z0-9_]+\}")
        self.assertIn(SAMPLE_ISIN, text)
        self.assertIn(load_report_data(self.check_dir).regression["equation"], text)
        pictures = {shape.name for shape in slide.shapes if shape.shape_type == 13}
        self.assertTrue(set(CHART_SHAPES) <= pictures)

    def test_report_without_llm_evaluation(self) -> None:
        work = self.tmp / SAMPLE_ISIN
        shutil.copytree(self.check_dir, work)
        (work / "outputs/llm-evaluation-openai.json").unlink()
        out = write_fund_timeseries_report(work, output_path=self.tmp / "report.pptx")
        text = _slide_text(Presentation(str(out)).slides[0])
        self.assertIn(NO_LLM, text)
        self.assertIn("not available", text)

    def test_writing_in_place_updates_manifest(self) -> None:
        work = self.tmp / SAMPLE_ISIN
        shutil.copytree(self.check_dir, work)
        manifest = json.loads((work / "manifest.json").read_text())
        manifest["files"] = [
            item for item in manifest["files"] if item["path"] != REPORT_FILENAME
        ]
        (work / "manifest.json").write_text(json.dumps(manifest))

        write_fund_timeseries_report(work)
        self.assertTrue((work / REPORT_FILENAME).is_file())
        paths = [
            item["path"]
            for item in json.loads((work / "manifest.json").read_text())["files"]
        ]
        self.assertEqual(paths.count(REPORT_FILENAME), 1)

    def test_unknown_token_in_template_is_rejected(self) -> None:
        template = self._template_with_footer_text("{not_a_token}")
        with self.assertRaisesRegex(KeyError, "not_a_token"):
            write_fund_timeseries_report(
                self.check_dir, output_path=self.tmp / "r.pptx", template=template
            )

    def test_token_split_across_runs_is_rejected(self) -> None:
        template = self._template_with_footer_text("{is", "in}")
        with self.assertRaisesRegex(ValueError, "split across text runs"):
            write_fund_timeseries_report(
                self.check_dir, output_path=self.tmp / "r.pptx", template=template
            )

    def _template_with_footer_text(self, *runs: str) -> Path:
        deck = Presentation(str(TEMPLATE_PATH))
        footer = next(s for s in deck.slides[0].shapes if s.name == "footer")
        paragraph = footer.text_frame.paragraphs[0]
        for run in paragraph.runs[1:]:
            run._r.getparent().remove(run._r)
        paragraph.runs[0].text = runs[0]
        for text in runs[1:]:
            paragraph.add_run().text = text
        path = self.tmp / "template.pptx"
        deck.save(str(path))
        return path


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
