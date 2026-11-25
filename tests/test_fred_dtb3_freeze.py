"""Tests for the frozen FRED DTB3 loader used in Step 10."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.fred_dtb3_freeze import (
    fred_dtb3_download_date,
    load_fred_dtb3_manifest,
    load_frozen_fred_dtb3,
    resolve_fred_dtb3_freeze_dir,
)


class FredDtb3FreezeTests(unittest.TestCase):
    def test_repo_freeze_loads_panel_window(self):
        rates = load_frozen_fred_dtb3()
        self.assertGreater(rates.notna().sum(), 2000)
        self.assertIn(pd.Timestamp("2015-11-03"), rates.index)
        self.assertAlmostEqual(float(rates.loc[pd.Timestamp("2015-11-03")]), 0.06)
        self.assertEqual(fred_dtb3_download_date(), "2026-11-25")
        manifest = load_fred_dtb3_manifest()
        self.assertEqual(manifest.get("series_id"), "DTB3")
        freeze_dir = resolve_fred_dtb3_freeze_dir()
        self.assertTrue((freeze_dir / "DTB3.csv").is_file())

    def test_blank_fred_rows_stay_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "DTB3.csv").write_text(
                "observation_date,DTB3\n"
                "2015-11-03,0.06\n"
                "2015-11-04,\n"
                "2015-11-05,0.05\n",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                '{"download_date": "2026-11-25", "series_id": "DTB3"}',
                encoding="utf-8",
            )
            rates = load_frozen_fred_dtb3(freeze_dir=root)
            self.assertAlmostEqual(
                float(rates.loc[pd.Timestamp("2015-11-03")]), 0.06
            )
            self.assertTrue(pd.isna(rates.loc[pd.Timestamp("2015-11-04")]))
            self.assertEqual(fred_dtb3_download_date(freeze_dir=root), "2026-11-25")

    def test_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_frozen_fred_dtb3(freeze_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()
