import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pandas as pd

from helpers.funds_functions.confirm_nport_series_classes import (
    CLASS_ABSENT,
    CONFIRMED,
    add_nport_same_series,
    fetch_nport_filings,
    label_for_class,
    parse_nport_series_check,
)


def _nport(
    series_id: str,
    class_ids: list[str],
    *,
    report_date: str = "2026-09-30",
    cik: str = "0000036405",
    holdings: bool = True,
) -> str:
    classes = "\n".join(
        f'<monthlyTotReturn classId="{class_id}" rtn1="0.01" rtn2="0.01" rtn3="0.01"/>'
        for class_id in class_ids
    )
    holding = "<invstOrSecs><invstOrSec><name>Example</name></invstOrSec></invstOrSecs>" if holdings else ""
    return f"""
    <edgarSubmission xmlns="http://www.sec.gov/edgar/nport">
      <formData>
        <genInfo>
          <regCik>{cik}</regCik>
          <seriesId>{series_id}</seriesId>
          <repPdDate>{report_date}</repPdDate>
        </genInfo>
        <fundInfo>
          <returnInfo>
            <monthlyTotReturns>
              {classes}
            </monthlyTotReturns>
          </returnInfo>
        </fundInfo>
        {holding}
      </formData>
    </edgarSubmission>
    """


def _row(series_id: str, class_id: str, cik: str = "0000036405") -> dict[str, str]:
    return {
        "edgartools_cik": cik,
        "edgartools_series_id": series_id,
        "edgartools_class_id": class_id,
    }


class ParseTests(unittest.TestCase):
    def test_reads_series_classes_and_holdings_with_namespace(self):
        parsed = parse_nport_series_check(
            _nport("S000002839", ["C000007773", "C000007774"])
        )
        self.assertEqual(parsed["series_id"], "S000002839")
        self.assertEqual(parsed["cik"], "0000036405")
        self.assertEqual(parsed["class_ids"], ["C000007773", "C000007774"])
        self.assertTrue(parsed["has_holdings"])
        self.assertEqual(parsed["report_date"], "2026-09-30")


class LabelTests(unittest.TestCase):
    def test_confirmed_when_class_is_on_the_series_filing_with_holdings(self):
        filing = parse_nport_series_check(_nport("S1", ["C1", "C2"]))
        label = label_for_class(series_id="S1", cik="0000036405", class_id="C2", filings=[filing])
        self.assertEqual(label, "confirmed (2026-09-30)")

    def test_padded_cik_matches_the_filing_cik(self):
        filing = parse_nport_series_check(_nport("S1", ["C1"], cik="36405"))
        label = label_for_class(series_id="S1", cik="0000036405", class_id="C1", filings=[filing])
        self.assertTrue(label.startswith(CONFIRMED))

    def test_previous_filing_confirms_a_class_missing_from_the_latest(self):
        latest = parse_nport_series_check(_nport("S1", ["C1"], report_date="2026-09-30"))
        previous = parse_nport_series_check(
            _nport("S1", ["C1", "C2"], report_date="2026-08-31")
        )
        label = label_for_class(
            series_id="S1",
            cik="36405",
            class_id="C2",
            filings=[latest, previous],
        )
        self.assertEqual(label, "confirmed (2026-08-31)")

    def test_class_absent_lists_both_report_dates(self):
        latest = parse_nport_series_check(_nport("S1", ["C1"], report_date="2026-09-30"))
        previous = parse_nport_series_check(_nport("S1", ["C1"], report_date="2026-08-31"))
        label = label_for_class(
            series_id="S1",
            class_id="C9",
            filings=[latest, previous],
        )
        self.assertEqual(label, "class absent (2026-09-30, 2026-08-31)")

    def test_series_mismatch(self):
        filing = parse_nport_series_check(_nport("S9", ["C1"]))
        label = label_for_class(series_id="S1", class_id="C1", filings=[filing])
        self.assertEqual(label, "series mismatch (2026-09-30)")

    def test_cik_mismatch(self):
        filing = parse_nport_series_check(_nport("S1", ["C1"], cik="0000000001"))
        label = label_for_class(series_id="S1", cik="0000036405", class_id="C1", filings=[filing])
        self.assertEqual(label, "CIK mismatch (2026-09-30)")

    def test_no_holdings(self):
        filing = parse_nport_series_check(_nport("S1", ["C1"], holdings=False))
        label = label_for_class(series_id="S1", class_id="C1", filings=[filing])
        self.assertEqual(label, "no holdings (2026-09-30)")

    def test_no_filing(self):
        self.assertEqual(
            label_for_class(series_id="S1", class_id="C1", filings=[]),
            "no N-PORT",
        )

    def test_missing_class_id(self):
        filing = parse_nport_series_check(_nport("S1", ["C1"]))
        self.assertEqual(
            label_for_class(series_id="S1", class_id=None, filings=[filing]),
            "no class id",
        )


class AttachTests(unittest.TestCase):
    def test_one_lookup_per_series_and_row_labels(self):
        frame = pd.DataFrame(
            [
                _row("S1", "C1"),
                _row("S1", "C2"),
                _row("S2", "C3", cik="0000000002"),
            ]
        )
        calls: list[tuple[str, set[str]]] = []

        def fetch(series_id: str, class_ids: set[str]) -> list[dict]:
            calls.append((series_id, set(class_ids)))
            if series_id == "S1":
                return [parse_nport_series_check(_nport("S1", ["C1", "C2"]))]
            return []

        out = add_nport_same_series(frame, fetch_filings=fetch)
        self.assertEqual([series for series, _classes in calls], ["S1", "S2"])
        self.assertEqual(calls[0][1], {"C1", "C2"})
        self.assertTrue(out["nport_same_series"].iloc[0].startswith(CONFIRMED))
        self.assertTrue(out["nport_same_series"].iloc[1].startswith(CONFIRMED))
        self.assertEqual(out["nport_same_series"].iloc[2], "no N-PORT")

    def test_fetch_error_labels_every_class_of_the_series(self):
        frame = pd.DataFrame([_row("S1", "C1"), _row("S1", "C2")])

        def fetch(_series_id: str, _class_ids: set[str]) -> list[dict]:
            raise RuntimeError("timeout")

        out = add_nport_same_series(frame, fetch_filings=fetch)
        self.assertEqual(out["nport_same_series"].tolist(), ["error: timeout", "error: timeout"])

    def test_class_absent_constant_is_the_label_prefix(self):
        self.assertEqual(CLASS_ABSENT, "class absent")


class FetchTests(unittest.TestCase):
    def test_latest_filing_is_enough_when_it_confirms_every_requested_class(self):
        latest = MagicMock()
        latest.xml.return_value = _nport("S1", ["C1"], report_date="2026-09-30")
        previous = MagicMock()
        previous.xml.return_value = _nport("S1", ["C1", "C2"], report_date="2026-08-31")
        fund = MagicMock()
        fund.get_filings.return_value = [latest, previous]
        factory = MagicMock(return_value=fund)

        with TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.json"
            with patch(
                "helpers.funds_functions.confirm_nport_series_classes.ensure_sec_identity"
            ):
                first = fetch_nport_filings(
                    "S1",
                    {"C1"},
                    cache_path=cache,
                    fund_factory=factory,
                )
                self.assertEqual(len(first), 1)
                previous.xml.assert_not_called()

                second = fetch_nport_filings(
                    "S1",
                    {"C1"},
                    cache_path=cache,
                    fund_factory=factory,
                )
        self.assertEqual(second, first)
        self.assertEqual(factory.call_count, 1)

    def test_cache_miss_that_does_not_confirm_reads_the_previous_filing(self):
        latest = MagicMock()
        latest.xml.return_value = _nport("S1", ["C1"], report_date="2026-09-30")
        previous = MagicMock()
        previous.xml.return_value = _nport("S1", ["C1", "C2"], report_date="2026-08-31")
        fund = MagicMock()
        fund.get_filings.return_value = [latest, previous]

        with TemporaryDirectory() as directory:
            with patch(
                "helpers.funds_functions.confirm_nport_series_classes.ensure_sec_identity"
            ):
                parsed = fetch_nport_filings(
                    "S1",
                    {"C1", "C2"},
                    cache_path=Path(directory) / "cache.json",
                    fund_factory=lambda _series: fund,
                )
        self.assertEqual(
            [filing["report_date"] for filing in parsed],
            ["2026-09-30", "2026-08-31"],
        )
        self.assertEqual(
            label_for_class(series_id="S1", class_id="C2", filings=parsed),
            "confirmed (2026-08-31)",
        )
