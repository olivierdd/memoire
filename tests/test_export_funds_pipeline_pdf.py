import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from helpers.funds_functions.export_funds_pipeline_pdf import (
    build_funds_v2_report,
    write_pipeline_pdf,
)


class ExportFundsPipelinePdfTests(unittest.TestCase):
    def test_writes_pdf(self):
        report = build_funds_v2_report(
            generated_at="2026-11-22 12:00",
            excel_export="output-data/v2-funds-normalized.xlsx",
            funnel=[["Loaded", "10", "—"], ["Final", "5", "−5"]],
            counts={
                "loaded": 10,
                "selected": 8,
                "after_openfigi": 7,
                "after_primary": 6,
                "after_style": 5,
                "final": 5,
                "drop_openfigi": 1,
                "drop_primary": 1,
                "drop_other": 1,
                "drop_name_gap": 0,
                "drop_no_tr": 0,
                "yahoo_filled": 1,
                "cusip_filled": 2,
                "confirmed": 3,
                "reclassified": 1,
            },
            matrix={
                "active_mf": 2,
                "passive_mf": 1,
                "active_etf": 1,
                "passive_etf": 1,
            },
            enrichments_funds=["OpenFIGI fields"],
            enrichments_series=["Yahoo TR backfill"],
        )
        with TemporaryDirectory() as tmp:
            path = write_pipeline_pdf(report, Path(tmp) / "report.pdf")
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
