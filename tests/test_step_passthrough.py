import unittest

import pandas as pd

from helpers.timeseries_functions.series_v2_pipeline import (
    exchange_holidays_from_panel,
    skip_gap_step,
    skip_holiday_step,
    skip_wide_step,
)


class StepPassthroughTests(unittest.TestCase):
    def test_skip_holiday_leaves_observations_and_lists_holidays(self):
        observations = pd.DataFrame(
            {1: [100.0, 100.0, 101.0]},
            index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
        )
        catalog = pd.DataFrame(
            [
                {
                    "column": 1,
                    "id": "S&P 500 TR",
                    "header": "S&P 500 TR",
                    "note": "Total return index, daily",
                    "category": "Index",
                },
            ]
        )
        payload = skip_holiday_step(catalog, observations)
        self.assertTrue(payload["skipped"])
        pd.testing.assert_frame_equal(payload["observations"], observations)
        self.assertGreaterEqual(len(payload["holiday_dates"]), 0)
        expected_holidays = exchange_holidays_from_panel(catalog, observations)
        self.assertEqual(len(payload["holiday_dates"]), len(expected_holidays))

    def test_skip_gap_chains_observations(self):
        holiday = skip_holiday_step(
            pd.DataFrame(
                [{"column": 1, "id": "X", "header": "X TR %", "note": "Daily simple return", "category": "Index"}]
            ),
            pd.DataFrame({"1": [0.01]}, index=pd.to_datetime(["2024-01-02"])),
        )
        gap = skip_gap_step(holiday)
        self.assertTrue(gap["skipped"])
        pd.testing.assert_frame_equal(gap["observations"], holiday["observations"])

    def test_skip_wide_keeps_full_catalog(self):
        catalog = pd.DataFrame(
            [
                {"column": 1, "id": "A", "header": "A TR %", "note": "Daily simple return", "category": "Active MF"},
                {"column": 2, "id": "B", "header": "B TR %", "note": "Daily simple return", "category": "Active MF"},
            ]
        )
        spike = {
            "observations": pd.DataFrame(
                {"1": [0.01], "2": [0.02]},
                index=pd.to_datetime(["2024-01-02"]),
            )
        }
        wide = skip_wide_step(catalog, spike)
        self.assertTrue(wide["skipped"])
        self.assertEqual(len(wide["catalog"]), len(catalog))


if __name__ == "__main__":
    unittest.main()