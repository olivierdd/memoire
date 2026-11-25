import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.series_v2_panel_cache import (
    CACHE_VERSION,
    load_or_build_panel_cache,
    load_panel_cache,
    panel_cache_fingerprint,
    panel_cache_is_fresh,
    save_panel_cache,
)


class SeriesV2PanelCacheTests(unittest.TestCase):
    def _toy_panel(self) -> dict:
        dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
        catalog = pd.DataFrame(
            {
                "column": [1, 2],
                "id": ["S&P", "US1"],
                "name": ["S&P TR", "Fund TR"],
                "category": ["Index", "Active MF"],
                "fee": [float("nan"), 0.5],
                "note": ["Total return index, daily", "Total return index, daily"],
                "header": ["S&P 500 TR", "US1 TR"],
                "observations": [3, 2],
                "first_date": [dates[0], dates[0]],
                "last_date": [dates[-1], dates[1]],
                "source": ["Lipper", "Yahoo"],
            }
        )
        observations = pd.DataFrame(
            {1: [100.0, 100.0, 101.0], 2: [10.0, 10.1, float("nan")]},
            index=pd.Index(dates, name="date"),
        )
        yahoo_tr_log = pd.DataFrame(
            {
                "isin": ["US1"],
                "ticker": ["FUND"],
                "status": ["replaced"],
                "tr_days_filled": [2],
                "tr_days_blank": [1],
                "price_days_filled": [2],
                "price_days_blank": [1],
                "tr_column": [2],
                "tr_return_column": [3],
                "price_column": [4],
                "price_return_column": [5],
            }
        )
        return {
            "catalog": catalog,
            "observations": observations,
            "yahoo_tr_log": yahoo_tr_log,
            "label_rows": 6,
            "sheet_name": "D-Timeseries final",
            "columns_on_sheet": 10,
            "columns_loaded": 2,
            "columns_skipped": 8,
            "columns_skipped_tna": 7,
            "columns_skipped_composite_price": 1,
            "sample_end_date": dates[-1],
            "yahoo_tr_download_date": "2026-01-01",
        }

    def _write_workbook_stub(self, root: Path) -> Path:
        workbook = root / "output-data" / "v2-funds-normalized.xlsx"
        workbook.parent.mkdir(parents=True, exist_ok=True)
        workbook.write_bytes(b"fake-xlsx")
        return workbook

    def test_roundtrip_restores_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = self._write_workbook_stub(root)
            cache_dir = root / "cache" / "series-v2-panel"
            panel = self._toy_panel()
            fingerprint = panel_cache_fingerprint(
                workbook,
                sheet_name=panel["sheet_name"],
                freeze_dir=root / "missing-freeze",
                replacements={"US1": "FUND"},
            )
            save_panel_cache(
                catalog=panel["catalog"],
                observations=panel["observations"],
                yahoo_tr_log=panel["yahoo_tr_log"],
                fingerprint=fingerprint,
                meta_fields={
                    "label_rows": panel["label_rows"],
                    "sheet_name": panel["sheet_name"],
                    "columns_on_sheet": panel["columns_on_sheet"],
                    "columns_loaded": panel["columns_loaded"],
                    "columns_skipped": panel["columns_skipped"],
                    "columns_skipped_tna": panel["columns_skipped_tna"],
                    "columns_skipped_composite_price": panel[
                        "columns_skipped_composite_price"
                    ],
                    "sample_end_date": str(panel["sample_end_date"].date()),
                    "yahoo_tr_download_date": panel["yahoo_tr_download_date"],
                },
                cache_dir=cache_dir,
            )
            self.assertTrue(
                panel_cache_is_fresh(fingerprint, cache_dir=cache_dir)
            )
            loaded = load_panel_cache(fingerprint, cache_dir=cache_dir)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertTrue(loaded["loaded_from_cache"])
            self.assertEqual(int(loaded["columns_loaded"]), 2)
            self.assertEqual(list(loaded["observations"].columns), [1, 2])
            pd.testing.assert_frame_equal(
                loaded["catalog"].reset_index(drop=True),
                panel["catalog"].reset_index(drop=True),
                check_dtype=False,
            )
            pd.testing.assert_frame_equal(
                loaded["observations"],
                panel["observations"],
                check_dtype=False,
            )

    def test_stale_when_workbook_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = self._write_workbook_stub(root)
            cache_dir = root / "cache" / "series-v2-panel"
            panel = self._toy_panel()
            fingerprint = panel_cache_fingerprint(
                workbook,
                sheet_name=panel["sheet_name"],
                freeze_dir=root / "missing-freeze",
                replacements={"US1": "FUND"},
            )
            save_panel_cache(
                catalog=panel["catalog"],
                observations=panel["observations"],
                yahoo_tr_log=panel["yahoo_tr_log"],
                fingerprint=fingerprint,
                meta_fields={
                    "label_rows": panel["label_rows"],
                    "sheet_name": panel["sheet_name"],
                    "columns_on_sheet": panel["columns_on_sheet"],
                    "columns_loaded": panel["columns_loaded"],
                    "columns_skipped": panel["columns_skipped"],
                    "columns_skipped_tna": panel["columns_skipped_tna"],
                    "columns_skipped_composite_price": panel[
                        "columns_skipped_composite_price"
                    ],
                    "sample_end_date": str(panel["sample_end_date"].date()),
                    "yahoo_tr_download_date": panel["yahoo_tr_download_date"],
                },
                cache_dir=cache_dir,
            )
            workbook.write_bytes(b"fake-xlsx-changed")
            stale = panel_cache_fingerprint(
                workbook,
                sheet_name=panel["sheet_name"],
                freeze_dir=root / "missing-freeze",
                replacements={"US1": "FUND"},
            )
            self.assertFalse(panel_cache_is_fresh(stale, cache_dir=cache_dir))
            self.assertIsNone(load_panel_cache(stale, cache_dir=cache_dir))

    def test_load_or_build_writes_then_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = self._write_workbook_stub(root)
            cache_dir = root / "cache" / "series-v2-panel"
            panel = self._toy_panel()
            builds = {"n": 0}

            def build():
                builds["n"] += 1
                return panel

            first = load_or_build_panel_cache(
                workbook=workbook,
                sheet_name=panel["sheet_name"],
                build=build,
                freeze_dir=root / "missing-freeze",
                replacements={"US1": "FUND"},
                cache_dir=cache_dir,
            )
            second = load_or_build_panel_cache(
                workbook=workbook,
                sheet_name=panel["sheet_name"],
                build=build,
                freeze_dir=root / "missing-freeze",
                replacements={"US1": "FUND"},
                cache_dir=cache_dir,
            )
            self.assertEqual(builds["n"], 1)
            self.assertFalse(first["loaded_from_cache"])
            self.assertTrue(second["loaded_from_cache"])
            meta = json.loads((cache_dir / "meta.json").read_text())
            self.assertEqual(meta["fingerprint"]["cache_version"], CACHE_VERSION)
            self.assertEqual(meta["sheet_name"], panel["sheet_name"])


if __name__ == "__main__":
    unittest.main()
