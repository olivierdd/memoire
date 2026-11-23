import math
import unittest

import numpy as np
import pandas as pd

from helpers.timeseries_functions.series_v2_pipeline import (
    carry_holiday_placeholders,
    summarize_tr_consistency,
)


class CarryHolidayPlaceholdersTests(unittest.TestCase):
    def _panel(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        # Day 1→2: S&P flat (holiday). Day 2→3: S&P moves.
        dates = pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"])
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4],
                "id": ["S&P", "S&P", "US8085098551", "US8085098551"],
                "name": ["S&P TR", "S&P TR %", "Fund TR", "Fund TR %"],
                "category": ["Index"] * 4,
                "fee": [pd.NA] * 4,
                "note": [
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                ],
                "header": [
                    "S&P 500 TR",
                    "S&P 500 TR %",
                    "US8085098551 TR",
                    "US8085098551 TR %",
                ],
            }
        )
        observations = pd.DataFrame(
            {
                1: [100.0, 100.0, 101.0],
                2: [np.nan, 0.0, 0.01],
                3: [50.0, np.nan, 51.0],
                4: [np.nan, np.nan, np.nan],
            },
            index=pd.Index(dates, name="date"),
        )
        return catalog, observations

    def test_blanks_holiday_level_and_return_recomputes_next_session(self):
        catalog, observations = self._panel()
        corrected, log, holidays = carry_holiday_placeholders(catalog, observations)

        self.assertEqual(len(holidays), 1)
        self.assertEqual(holidays[0], pd.Timestamp("2020-01-03"))
        holiday = pd.Timestamp("2020-01-03")
        self.assertTrue(math.isnan(float(corrected.loc[holiday, 1])))
        self.assertTrue(math.isnan(float(corrected.loc[holiday, 2])))
        self.assertTrue(math.isnan(float(corrected.loc[holiday, 3])))
        self.assertTrue(math.isnan(float(corrected.loc[holiday, 4])))
        self.assertAlmostEqual(
            float(corrected.loc[pd.Timestamp("2020-01-06"), 4]), 51.0 / 50.0 - 1.0
        )
        self.assertFalse(log.empty)
        self.assertEqual(int(log.loc[0, "holidays_fixed"]), 1)

    def test_blanks_padded_holiday_instead_of_carry_or_zero(self):
        catalog, observations = self._panel()
        observations.loc[pd.Timestamp("2020-01-03"), 3] = 50.5
        observations.loc[pd.Timestamp("2020-01-03"), 4] = 0.01
        corrected, log, _ = carry_holiday_placeholders(catalog, observations)
        holiday = pd.Timestamp("2020-01-03")
        self.assertTrue(math.isnan(float(corrected.loc[holiday, 3])))
        self.assertTrue(math.isnan(float(corrected.loc[holiday, 4])))
        self.assertAlmostEqual(
            float(corrected.loc[pd.Timestamp("2020-01-06"), 4]), 51.0 / 50.0 - 1.0
        )
        self.assertFalse(log.empty)

    def test_gap_check_uses_holiday_calendar_after_spx_level_blanked(self):
        dates = pd.to_datetime(
            ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07", "2020-01-08"]
        )
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4],
                "id": ["S&P", "S&P", "US8085098551", "US8085098551"],
                "name": ["S&P TR", "S&P TR %", "Fund TR", "Fund TR %"],
                "category": ["Index"] * 4,
                "fee": [pd.NA] * 4,
                "note": [
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                    "Total return index, daily",
                    "Daily simple return = P(t)/P(t-1) - 1",
                ],
                "header": [
                    "S&P 500 TR",
                    "S&P 500 TR %",
                    "US8085098551 TR",
                    "US8085098551 TR %",
                ],
            }
        )
        observations = pd.DataFrame(
            {
                1: [100.0, 100.0, 101.0, 102.0, 103.0],
                2: [np.nan, 0.0, 0.01, 0.0099, 0.0098],
                3: [50.0, 50.0, 51.0, 51.5, 52.0],
                # Returns start 2020-01-02 so the daily window spans the holiday.
                4: [0.0, 0.01, 0.02, 0.0098, 0.0097],
            },
            index=pd.Index(dates, name="date"),
        )
        corrected, _, holidays = carry_holiday_placeholders(catalog, observations)

        _, issue_without, _ = summarize_tr_consistency(
            catalog, corrected, flags=("gaps",)
        )
        _, issue_with, _ = summarize_tr_consistency(
            catalog,
            corrected,
            flags=("gaps",),
            exchange_holidays=holidays,
        )
        fund_header = "US8085098551 TR %"
        gaps_without = int(
            issue_without.loc[issue_without["header"].eq(fund_header), "gaps"].iloc[0]
        )
        gaps_with = int(
            issue_with.loc[issue_with["header"].eq(fund_header), "gaps"].iloc[0]
        )
        self.assertEqual(gaps_without, len(holidays))
        self.assertEqual(gaps_with, 0)


if __name__ == "__main__":
    unittest.main()