import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

import pandas as pd

from helpers.timeseries_functions.check_timeseries_consistency import (
    check_timeseries_consistency,
    locate_timeseries_issues,
)
from helpers.timeseries_functions.plot_timeseries_issues import (
    ISSUE_INDEX,
    ISSUE_LEVEL,
    ISSUE_SCALE,
    ISSUE_SPIKE,
    issue_markers,
    plot_timeseries_issues,
)

INDEX = "S&P 500 TR"
MASTER = "Fund (Lipper)"
COMPARISON = "Fund (Yahoo)"


def _frame(master, index, comparison=None, periods=None, dates=None) -> pd.DataFrame:
    count = len(master)
    if dates is None:
        dates = pd.date_range("2010-01-01", periods=count, freq="MS")
    if periods is None:
        periods = ["Jan 2010", "Feb 2010", "Mar 2010", "Apr 2010", "May 2010", "Jun 2010"]
        periods = periods[:count]
        if len(periods) < count:
            periods = list(pd.to_datetime(dates).strftime("%b %Y"))
    if comparison is None:
        comparison = index
    return pd.DataFrame(
        {
            "Period": periods,
            "Date": pd.to_datetime(dates),
            MASTER: master,
            COMPARISON: comparison,
            INDEX: index,
        }
    )


def _checks(frame, **kwargs):
    return locate_timeseries_issues(
        frame,
        INDEX,
        MASTER,
        COMPARISON,
        master_timeseries="Lipper",
        comparison_timeseries="Yahoo",
        **kwargs,
    )


class LocateTimeseriesIssuesTest(unittest.TestCase):
    def test_opening_month_without_a_return_is_not_a_gap(self):
        frame = _frame([None, 0.01, 0.01, 0.01], [0.0, 0.01, 0.01, 0.01])
        lipper, yahoo = _checks(frame)
        self.assertFalse(lipper.months["gap"].any())
        self.assertFalse(yahoo.months["gap"].any())

    def test_missing_return_skipped_month_and_long_gap(self):
        dates = pd.to_datetime(["2010-01-01", "2010-02-01", "2010-03-01", "2010-05-20"])
        periods = ["Jan 2010", "Feb 2010", "Mar 2010", "May 2010"]
        frame = _frame(
            [0.01, None, 0.01, 0.01],
            [0.01, 0.01, 0.01, 0.01],
            periods=periods,
            dates=dates,
        )
        lipper, _yahoo = _checks(frame)
        months = lipper.months
        self.assertTrue(months.at[1, "gap"])
        self.assertTrue(months.at[1, "missing"])
        self.assertTrue(months.at[3, "gap"])
        self.assertTrue(months.at[3, "skipped"])
        self.assertTrue(months.at[3, "long_gap"])

        marks = issue_markers(lipper).set_index("Period")
        self.assertEqual(marks.at["Feb 2010", "Detail"], "missing return")
        self.assertEqual(
            marks.at["May 2010", "Detail"],
            "skipped month, 80 days since the previous date",
        )
        spec = json.dumps(plot_timeseries_issues(_checks(frame), INDEX).to_dict())
        self.assertIn("missing return", spec)
        self.assertIn("80 days since the previous date", spec)

    def test_reversal_is_a_spike_and_the_giveback_month_is_not(self):
        master = [0.0, 0.25, -0.1875, 0.0, 0.0, 0.0]
        frame = _frame(master, [0.0] * 6)
        lipper, yahoo = _checks(frame)
        self.assertEqual(list(lipper.months.index[lipper.months["spike"]]), [1])
        self.assertFalse(yahoo.months["spike"].any())

        marked = issue_markers(lipper)
        spike = marked[marked["Issue"] == ISSUE_SPIKE]
        self.assertEqual(list(spike["Period"]), ["Feb 2010"])
        self.assertIn("reverses the next month, the index does not", spike["Detail"].iloc[0])
        self.assertIn("bp", spike["Detail"].iloc[0])

        buffer = StringIO()
        with redirect_stdout(buffer):
            check_timeseries_consistency(
                frame,
                INDEX,
                MASTER,
                COMPARISON,
                master_timeseries="Lipper",
                comparison_timeseries="Yahoo",
            )
        report = buffer.getvalue()
        self.assertIn(
            "        2010-02-01  Feb 2010  +25.00%  "
            "S&P 500 TR +0.00%  reverses the next month, the index does not",
            report,
        )
        self.assertIn("    Abnormal spikes: 1", report)
        self.assertIn("Yahoo\n    Gaps: none", report)
        self.assertIn("    Abnormal spikes: none", report)

    def test_level_jump_is_not_also_called_a_spike(self):
        master = [0.0, 0.80, 0.02, 0.02, 0.02]
        frame = _frame(master, [0.0] * 5)
        lipper, _yahoo = _checks(frame)
        self.assertEqual(list(lipper.months.index[lipper.months["level_jump"]]), [1])
        self.assertFalse(lipper.months["spike"].any())
        marked = issue_markers(lipper)
        self.assertEqual(list(marked["Issue"]), [ISSUE_LEVEL])
        self.assertIn("level does not come back", marked["Detail"].iloc[0])
        self.assertIn("bp", marked["Detail"].iloc[0])

    def test_lasting_scale_change_marks_the_later_months(self):
        master = [0.01] * 3 + [0.20] * 5
        periods = [
            "Jan 2010",
            "Feb 2010",
            "Mar 2010",
            "Apr 2010",
            "May 2010",
            "Jun 2010",
            "Jul 2010",
            "Aug 2010",
        ]
        frame = _frame(master, [0.01] * 8, periods=periods)
        lipper, _yahoo = _checks(frame, scale_window=3, scale_factor=4)
        self.assertEqual(lipper.scale_at, 3)
        self.assertFalse(lipper.months["spike"].any())
        self.assertTrue(lipper.months["wide"].iloc[3:].all())
        self.assertFalse(lipper.months["wide"].iloc[:3].any())

        marked = issue_markers(lipper)
        scale = marked[marked["Issue"] == ISSUE_SCALE]
        self.assertEqual(list(scale["Period"]), ["Apr 2010"])
        self.assertIn("median |return| goes from", scale["Detail"].iloc[0])
        later = marked[marked["Issue"] == ISSUE_INDEX]
        self.assertEqual(len(later), 5)
        self.assertTrue(later["Detail"].str.contains("because the scale has changed").all())
        chart = plot_timeseries_issues(
            _checks(frame, scale_window=3, scale_factor=4),
            INDEX,
        )
        spec = json.dumps(chart.to_dict())
        self.assertIn(ISSUE_SCALE, spec)
        self.assertIn(ISSUE_INDEX, spec)


class PlotTimeseriesIssuesTest(unittest.TestCase):
    def test_chart_marks_the_flagged_month(self):
        master = [0.0, 0.25, -0.1875, 0.0, 0.0, 0.0]
        frame = _frame(master, [0.0] * 6)
        checks = _checks(frame)
        chart = plot_timeseries_issues(checks, INDEX)
        spec = json.dumps(chart.to_dict())
        self.assertIn(ISSUE_SPIKE, spec)
        self.assertIn("Lipper", spec)
        self.assertIn("Yahoo", spec)
        self.assertIn("1 abnormal spike", spec)
        self.assertIn("No gaps, spikes, scale shifts", spec)

    def test_clean_series_has_no_issue_marks(self):
        frame = _frame([0.01, 0.02, -0.01, 0.0], [0.01, 0.015, -0.008, 0.002])
        checks = _checks(frame)
        self.assertTrue(issue_markers(checks[0]).empty)
        spec = json.dumps(plot_timeseries_issues(checks, INDEX).to_dict())
        self.assertNotIn(ISSUE_SPIKE, spec)
        self.assertIn("No gaps, spikes, scale shifts", spec)


if __name__ == "__main__":
    unittest.main()
