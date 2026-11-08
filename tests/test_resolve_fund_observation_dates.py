import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.load_index_timeseries import (
    INDEX_COLUMN,
    INDEX_SOURCE_COLUMN,
    load_index_timeseries,
)
from helpers.timeseries_functions.resolve_fund_observation_dates import (
    DATE_SHIFT_COLUMN,
    INDEX_DATE_COLUMN,
    resolve_fund_observation_dates,
)

LIPPER = "US0000000001 (Lipper)"


def _sessions(start: str, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _level_from_returns(sessions: pd.DatetimeIndex, returns: list[float]) -> pd.Series:
    level = [100.0]
    for r in returns:
        level.append(level[-1] * (1 + r))
    return pd.Series(level[1:], index=sessions[: len(returns)], dtype=float)


class ResolveFundObservationDatesTests(unittest.TestCase):
    def test_recorded_dates_reproduce_lipper_no_shift(self) -> None:
        sessions = _sessions("2021-10-01", 10)
        yahoo_level = _level_from_returns(
            sessions, [0.01, -0.02, 0.015, 0.005, -0.01, 0.02, 0.0, 0.01, 0.01]
        )
        dates = sessions[1:8]
        lipper = [
            float(yahoo_level.loc[d] / yahoo_level.loc[sessions[i]] - 1)
            for i, d in enumerate(dates, start=1)
        ]
        frame = pd.DataFrame(
            {
                "Period": [d.strftime("%b %Y") for d in dates],
                "Date": dates,
                "Time": "Close",
                LIPPER: lipper,
            }
        )
        out = resolve_fund_observation_dates(frame, LIPPER, yahoo_level)
        self.assertTrue((out[DATE_SHIFT_COLUMN] == 0).all())
        self.assertTrue((out["Date"] == out[INDEX_DATE_COLUMN]).all())

    def test_dec_2021_pattern_shifts_end_by_one_session(self) -> None:
        sessions = _sessions("2021-10-01", 80)
        yahoo_level = pd.Series(100.0, index=sessions, dtype=float)
        index_dates = pd.to_datetime(
            ["2021-11-01", "2021-12-01", "2022-01-03", "2022-02-01"]
        )
        resolved_end = pd.Timestamp("2021-11-30")
        self.assertIn(resolved_end, yahoo_level.index)
        yahoo_level.loc[index_dates[0]] = 101.0
        yahoo_level.loc[resolved_end] = 98.99
        yahoo_level.loc[index_dates[1]] = 99.50
        yahoo_level.loc[index_dates[2]] = 104.0
        yahoo_level.loc[index_dates[3]] = 105.0
        start_nov = index_dates[0]
        lipper_dec = float(
            yahoo_level.loc[resolved_end] / yahoo_level.loc[start_nov] - 1
        )
        lipper_jan = float(
            yahoo_level.loc[index_dates[2]] / yahoo_level.loc[resolved_end] - 1
        )
        frame = pd.DataFrame(
            {
                "Period": ["Nov 2021", "Dec 2021", "Jan 2022", "Feb 2022"],
                "Date": index_dates,
                "Time": "Close",
                LIPPER: [float("nan"), lipper_dec, lipper_jan, 0.01],
            }
        )
        out = resolve_fund_observation_dates(frame, LIPPER, yahoo_level)
        dec_row = out.loc[out["Period"].eq("Dec 2021")].iloc[0]
        self.assertEqual(pd.Timestamp(dec_row["Date"]), resolved_end)
        self.assertLess(int(dec_row[DATE_SHIFT_COLUMN]), 0)
        jan_row = out.loc[out["Period"].eq("Jan 2022")].iloc[0]
        self.assertEqual(pd.Timestamp(jan_row["Date"]), index_dates[2])
        yahoo_dec = float(
            yahoo_level.loc[dec_row["Date"]] / yahoo_level.loc[start_nov] - 1
        )
        yahoo_jan = float(
            yahoo_level.loc[jan_row["Date"]] / yahoo_level.loc[dec_row["Date"]] - 1
        )
        self.assertAlmostEqual(
            (1 + yahoo_dec) * (1 + yahoo_jan) - 1,
            (1 + lipper_dec) * (1 + lipper_jan) - 1,
            places=8,
        )

    def test_genuine_disagreement_keeps_index_date(self) -> None:
        sessions = _sessions("2021-01-01", 6)
        yahoo_level = _level_from_returns(sessions, [0.01, 0.01, 0.01, 0.01, 0.01])
        dates = sessions[[1, 2, 3]]
        frame = pd.DataFrame(
            {
                "Period": ["Feb 2021", "Mar 2021", "Apr 2021"],
                "Date": dates,
                "Time": "Close",
                LIPPER: [0.01, 0.60, 0.01],
            }
        )
        out = resolve_fund_observation_dates(frame, LIPPER, yahoo_level)
        mar = out.loc[out["Period"].eq("Mar 2021")].iloc[0]
        self.assertEqual(pd.Timestamp(mar["Date"]), pd.Timestamp(dates[1]))
        self.assertEqual(int(mar[DATE_SHIFT_COLUMN]), 0)

    def test_monotonic_dates_after_resolution(self) -> None:
        sessions = _sessions("2020-01-01", 20)
        yahoo_level = _level_from_returns(sessions, [0.005] * 19)
        dates = sessions[5:15]
        lipper = (yahoo_level / yahoo_level.shift(1) - 1).loc[dates]
        frame = pd.DataFrame(
            {
                "Period": [d.strftime("%b %Y") for d in dates],
                "Date": dates,
                "Time": "Close",
                LIPPER: lipper.to_numpy(),
            }
        )
        out = resolve_fund_observation_dates(frame, LIPPER, yahoo_level)
        resolved = pd.to_datetime(out["Date"])
        self.assertTrue(resolved.is_monotonic_increasing)
        self.assertTrue((resolved.diff().dropna() > pd.Timedelta(0)).all())

    def test_load_index_cache_vs_yahoo_window(self) -> None:
        sessions = _sessions("2021-10-01", 80)
        yahoo_level = pd.Series(100.0, index=sessions, dtype=float)
        sp500 = pd.Series(200.0, index=sessions, dtype=float)
        index_dates = pd.to_datetime(
            ["2021-11-01", "2021-12-01", "2022-01-03", "2022-02-01"]
        )
        resolved_end = pd.Timestamp("2021-11-30")
        yahoo_level.loc[index_dates[0]] = 101.0
        yahoo_level.loc[resolved_end] = 98.99
        yahoo_level.loc[index_dates[1]] = 99.50
        sp500.loc[index_dates[0]] = 210.0
        sp500.loc[resolved_end] = 205.0
        sp500.loc[index_dates[1]] = 206.0
        lipper_dec = float(
            yahoo_level.loc[resolved_end] / yahoo_level.loc[index_dates[0]] - 1
        )
        frame = pd.DataFrame(
            {
                "Period": ["Nov 2021", "Dec 2021", "Jan 2022", "Feb 2022"],
                "Date": index_dates,
                "Time": "Close",
                LIPPER: [float("nan"), lipper_dec, 0.05, 0.01],
            }
        )
        frame = resolve_fund_observation_dates(frame, LIPPER, yahoo_level)
        cache = pd.DataFrame(
            {
                "Date": index_dates,
                "S&P 500 TR (Lipper)": [100.0, 101.0, 99.0, 103.0],
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "sp.json"
            cache.to_json(cache_path, orient="records", date_format="iso")
            out = load_index_timeseries(
                frame,
                cache_path,
                sp500_close=sp500,
            )
        nov = out.loc[out["Period"].eq("Nov 2021")].iloc[0]
        dec = out.loc[out["Period"].eq("Dec 2021")].iloc[0]
        self.assertTrue(pd.isna(nov[INDEX_COLUMN]))
        self.assertTrue(pd.isna(nov[INDEX_SOURCE_COLUMN]))
        feb = out.loc[out["Period"].eq("Feb 2022")].iloc[0]
        self.assertEqual(feb[INDEX_SOURCE_COLUMN], "Lipper cache")
        self.assertEqual(dec[INDEX_SOURCE_COLUMN], "Yahoo ^SP500TR (shifted window)")
        expected = float(sp500.loc[resolved_end] / sp500.loc[index_dates[0]] - 1)
        self.assertAlmostEqual(float(dec[INDEX_COLUMN]), expected, places=6)


if __name__ == "__main__":
    unittest.main()
