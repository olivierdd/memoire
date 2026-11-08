import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from helpers.funds_functions.classify_fund_management_style import (
    classify_fund_management_style,
)
from helpers.funds_functions.fund_management_style_rules import (
    decide_series,
    label_from_ncen,
    label_from_objective,
    label_from_statutory_text,
    prospectus_excerpt,
    style_from_jev_choice,
)
from helpers.funds_functions.fetch_edgar_filing_facts import parse_ncen_fund_types_for_series


def _ncen(series_id: str, body: str) -> str:
    return f"""
    <edgarSubmission>
      <formData>
        <managementInvestmentQuestionSeriesInfo>
          <managementInvestmentQuestion>
            <mgmtInvSeriesId>{series_id}</mgmtInvSeriesId>
            {body}
          </managementInvestmentQuestion>
        </managementInvestmentQuestionSeriesInfo>
      </formData>
    </edgarSubmission>
    """


class LabelTests(unittest.TestCase):
    def test_index_fund_info_is_passive(self):
        xml = _ncen(
            "S1",
            """
            <fundTypes>
              <fundType>Exchange-Traded Fund</fundType>
              <indexFundInfo fundType="Index Fund"></indexFundInfo>
            </fundTypes>
            """,
        )
        label, detail = label_from_ncen(parse_ncen_fund_types_for_series(xml, "S1"))
        self.assertEqual(label, "Passive")
        self.assertIn("Index Fund", detail)

    def test_etf_without_index_block_is_active(self):
        xml = _ncen("S1", "<fundTypes><fundType>Exchange-Traded Fund</fundType></fundTypes>")
        label, _detail = label_from_ncen(parse_ncen_fund_types_for_series(xml, "S1"))
        self.assertEqual(label, "Active")

    def test_fund_of_funds_is_other(self):
        xml = _ncen("S1", "<fundTypes><fundType>Fund of Funds</fundType></fundTypes>")
        label, _detail = label_from_ncen(parse_ncen_fund_types_for_series(xml, "S1"))
        self.assertEqual(label, "Other")

    def test_legacy_na_does_not_decide(self):
        xml = _ncen("S1", "<fundType>N/A</fundType>")
        label, detail = label_from_ncen(parse_ncen_fund_types_for_series(xml, "S1"))
        self.assertIsNone(label)
        self.assertIn("N/A", detail)

    def test_missing_series_does_not_decide(self):
        xml = _ncen("S1", "<fundType>N/A</fundType>")
        label, detail = label_from_ncen(parse_ncen_fund_types_for_series(xml, "S9"))
        self.assertIsNone(label)
        self.assertIn("absent", detail)

    def test_tracking_language_is_passive(self):
        label, _detail = label_from_objective(
            "The fund seeks to track the performance of a benchmark index."
        )
        self.assertEqual(label, "Passive")

    def test_not_actively_managed_is_not_read_as_active(self):
        label, _detail = label_from_objective("The fund is not actively managed.")
        self.assertEqual(label, "Passive")

    def test_selection_language_is_active(self):
        label, _detail = label_from_objective(
            "The fund seeks capital appreciation through security selection."
        )
        self.assertEqual(label, "Active")

    def test_growth_of_capital_is_active(self):
        label, _detail = label_from_objective(
            "The fund's investment objective is to provide you with growth of capital."
        )
        self.assertEqual(label, "Active")

    def test_capital_growth_with_extra_words_is_active(self):
        label, _detail = label_from_objective(
            "The Fund seeks both capital growth and income."
        )
        self.assertEqual(label, "Active")

    def test_approximate_index_return_is_passive(self):
        label, _detail = label_from_objective(
            "The Portfolio seeks to approximate the total investment return of the S&P 500 Index."
        )
        self.assertEqual(label, "Passive")

    def test_benchmark_row_alone_does_not_decide(self):
        decision = decide_series(
            ncen_xml=None,
            series_id="S1",
            objective=None,
            statutory_text="Average annual returns. S&P 500 Index reflects no deduction for fees.",
            series_name=None,
        )
        self.assertEqual(decision["style"], "Unknown")


class FrameTests(unittest.TestCase):
    def test_series_share_one_label_and_cache(self):
        xml = _ncen(
            "S1",
            """
            <fundTypes>
              <fundType>Exchange-Traded Fund</fundType>
              <indexFundInfo fundType="Index Fund"></indexFundInfo>
            </fundTypes>
            """,
        )
        calls = {"ncen": 0, "objective": 0}

        def ncen(_cik: str) -> str:
            calls["ncen"] += 1
            return xml

        def objective(_series_id: str) -> str | None:
            calls["objective"] += 1
            return None

        def statutory(_series_id: str) -> tuple[str | None, str | None]:
            return None, None

        funds = pd.DataFrame(
            {
                "Name": ["Admiral", "ETF"],
                "edgartools_cik": ["102909", "0000102909"],
                "edgartools_series_id": ["S1", "S1"],
                "edgar_series_name": ["Index Fund", "Index Fund"],
            }
        )
        with TemporaryDirectory() as directory:
            cache = Path(directory) / "style.json"
            first = classify_fund_management_style(
                funds,
                cache_path=cache,
                fetch_ncen_xml=ncen,
                fetch_497k_objective=objective,
                fetch_485_text=statutory,
            )
            second = classify_fund_management_style(
                funds,
                cache_path=cache,
                fetch_ncen_xml=ncen,
                fetch_497k_objective=objective,
                fetch_485_text=statutory,
            )
        self.assertEqual(first["fund_management_style"].tolist(), ["Passive", "Passive"])
        self.assertEqual(first["fund_management_style_source"].tolist(), ["N-CEN", "N-CEN"])
        self.assertEqual(second["fund_management_style"].tolist(), ["Passive", "Passive"])
        self.assertEqual(calls["ncen"], 1)
        self.assertEqual(calls["objective"], 0)
        self.assertLess(
            list(first.columns).index("edgar_series_name"),
            list(first.columns).index("fund_management_style"),
        )

    def test_na_census_uses_497k(self):
        xml = _ncen("S2", "<fundType>N/A</fundType>")
        funds = pd.DataFrame(
            {
                "edgartools_cik": ["0000000002"],
                "edgartools_series_id": ["S2"],
                "edgar_series_name": ["Contrafund"],
            }
        )
        seen: list[str] = []

        def judge(text: str, _name: str | None) -> tuple[str, str]:
            seen.append(text)
            return "Active", "Jev Active confidence 0.91"

        with TemporaryDirectory() as directory:
            out = classify_fund_management_style(
                funds,
                cache_path=Path(directory) / "style.json",
                fetch_ncen_xml=lambda _cik: xml,
                fetch_497k_objective=lambda _series: "The fund seeks capital appreciation.",
                fetch_485_text=lambda _series: ("unused statutory text", "485BPOS"),
                judge_prospectus=judge,
            )
        self.assertEqual(seen, ["The fund seeks capital appreciation."])
        self.assertEqual(out.loc[0, "fund_management_style"], "Active")
        self.assertEqual(out.loc[0, "fund_management_style_source"], "Jev")

    def test_missing_series_is_unknown(self):
        funds = pd.DataFrame(
            {"edgartools_cik": [None], "edgartools_series_id": [None], "edgar_series_name": [None]}
        )
        with TemporaryDirectory() as directory:
            out = classify_fund_management_style(
                funds,
                cache_path=Path(directory) / "style.json",
                fetch_ncen_xml=lambda _cik: None,
                fetch_497k_objective=lambda _series: None,
                fetch_485_text=lambda _series: (None, None),
            )
        self.assertEqual(out.loc[0, "fund_management_style"], "Unknown")
        self.assertEqual(out.loc[0, "fund_management_style_detail"], "no EDGAR series")

    def test_missing_identifiers_are_not_sent_to_edgar(self):
        calls: list[str] = []
        funds = pd.DataFrame(
            {
                "edgartools_cik": [float("nan"), "nan"],
                "edgartools_series_id": [float("nan"), "NaN"],
                "edgar_series_name": [None, None],
            }
        )

        def ncen(cik: str) -> str | None:
            calls.append(cik)
            return None

        with TemporaryDirectory() as directory:
            out = classify_fund_management_style(
                funds,
                cache_path=Path(directory) / "style.json",
                fetch_ncen_xml=ncen,
                fetch_497k_objective=lambda series: calls.append(series) or None,
                fetch_485_text=lambda series: calls.append(series) or (None, None),
            )
        self.assertEqual(calls, [])
        self.assertEqual(out["fund_management_style"].tolist(), ["Unknown", "Unknown"])


class StatutoryTextTests(unittest.TestCase):
    def test_strategy_paragraph_is_read_past_the_table_of_contents(self):
        text = """
        Investment Objective ................ 3
        Principal Investment Strategies ...... 4
        Selected American Shares
        Investment Objective
        The Fund seeks current income.
        Principal Investment Strategies of the Fund
        The Fund invests principally in common stocks issued by large companies.
        """
        label, _detail = label_from_statutory_text(text, "Selected American Shares")
        self.assertEqual(label, "Active")
        excerpt = prospectus_excerpt(text, "Selected American Shares")
        self.assertNotIn("......", excerpt)
        self.assertIn("invests principally in common stocks", excerpt)


class JevChoiceTests(unittest.TestCase):
    def test_low_confidence_is_not_accepted(self):
        self.assertIsNone(style_from_jev_choice("Active", 0.4))
        self.assertEqual(style_from_jev_choice("Passive", 0.6), "Passive")
        self.assertIsNone(style_from_jev_choice("Maybe", 0.9))
