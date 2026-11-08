import json
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pandas as pd

from helpers.funds_functions import fetch_edgar_filing_facts as mod
from helpers.funds_functions.fetch_edgar_filing_facts import (
    INDEX_FUND_LABEL,
    MANAGEMENT_STYLE_ACTIVE,
    MANAGEMENT_STYLE_PASSIVE,
    _benchmark_indices,
    _fee_rows,
    _series_worklist,
    extract_ncen_blob,
    is_open_end_registrant,
    management_style_from_ncen_labels,
    ncen_primary_doc_url,
    parse_ncen_fund_types_for_series,
    refresh_edgar_filing_facts_cache,
)


class SeriesWorklistTests(unittest.TestCase):
    def test_deduplicates_series_id(self):
        funds = pd.DataFrame(
            {
                "edgartools_series_id": ["S1", "S1", "S2"],
                "edgartools_cik": ["1", "1", "2"],
                "market_identifier": ["AAA", "AAA", "BBB"],
            }
        )
        worklist = _series_worklist(funds)
        self.assertEqual(len(worklist), 2)


class ExtractorTests(unittest.TestCase):
    def test_benchmark_indices_skips_return_rows(self):
        prospectus = MagicMock()
        prospectus.tickers = ["VFIAX"]
        prospectus.performance = pd.DataFrame(
            {
                "label": [
                    "Return Before Taxes",
                    "S&P 500 Index (reflects no deduction for fees, expenses, or taxes)",
                ]
            }
        )
        indices = _benchmark_indices(prospectus)
        self.assertEqual(len(indices), 1)
        self.assertIn("S&P 500", indices[0])

    def test_fee_rows_prefers_net_for_ter(self):
        prospectus = MagicMock()
        prospectus.fees = pd.DataFrame(
            [
                {
                    "class_name": "Admiral",
                    "ticker": "VFIAX",
                    "class_id": "C1",
                    "management_fee": Decimal("0.04"),
                    "twelve_b1_fee": None,
                    "other_expenses": None,
                    "total_annual_expenses": Decimal("0.05"),
                    "fee_waiver": None,
                    "net_expenses": Decimal("0.04"),
                }
            ]
        )
        rows = _fee_rows(prospectus)
        self.assertEqual(rows[0]["ter_pct"], 0.04)
        self.assertEqual(rows[0]["net_expense_ratio_pct"], 0.04)

    def test_extract_ncen_blob(self):
        filing = MagicMock(accession_no="acc-1", filing_date="2026-01-01", form="N-CEN")
        filing.xml.return_value = None
        census = MagicMock(spec=mod.FundCensus)
        census.report_date = "2025-12-31"
        census.name = "Test Trust"
        census.classification_type = "N-1A"
        census.series_data.return_value = pd.DataFrame(
            [
                {
                    "name": "Test Fund",
                    "series_id": "S0001",
                    "lei": "LEI",
                    "fund_type": "open-end",
                    "avg_net_assets": Decimal("1000"),
                    "aggregate_commission": Decimal("0"),
                    "num_advisers": 1,
                    "num_custodians": 1,
                    "has_etf": False,
                }
            ]
        )
        census.etf_data.return_value = pd.DataFrame()
        census.series = []

        blob = extract_ncen_blob(census, filing, "S0001")
        self.assertEqual(blob["accession_number"], "acc-1")
        self.assertFalse(blob["series"]["has_etf"])
        self.assertEqual(blob["registrant_classification_type"], "N-1A")
        self.assertTrue(blob["is_open_end"])

    def test_is_open_end_registrant(self):
        self.assertTrue(is_open_end_registrant("N-1A"))
        self.assertFalse(is_open_end_registrant("N-2"))
        self.assertIsNone(is_open_end_registrant(None))

    def test_parse_ncen_fund_types_index_fund_new_schema(self):
        xml = """
        <edgarSubmission>
          <formData>
            <managementInvestmentQuestionSeriesInfo>
              <managementInvestmentQuestion>
                <mgmtInvSeriesId>S000006027</mgmtInvSeriesId>
                <fundTypes>
                  <indexFundInfo fundType="Index Fund">
                    <isIndexFundAffiliated>N</isIndexFundAffiliated>
                    <indexFundReturnDiffBeforeExpense>0.00329600</indexFundReturnDiffBeforeExpense>
                  </indexFundInfo>
                </fundTypes>
              </managementInvestmentQuestion>
            </managementInvestmentQuestionSeriesInfo>
          </formData>
        </edgarSubmission>
        """
        parsed = parse_ncen_fund_types_for_series(xml, "S000006027")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["labels"], [INDEX_FUND_LABEL])
        self.assertTrue(parsed["is_index_fund"])
        self.assertEqual(parsed["management_style"], MANAGEMENT_STYLE_PASSIVE)
        self.assertEqual(
            parsed["index_fund_info"]["return_diff_before_expense_pct"], 0.003296
        )

    def test_parse_ncen_fund_types_etf_and_index(self):
        xml = """
        <edgarSubmission>
          <formData>
            <managementInvestmentQuestionSeriesInfo>
              <managementInvestmentQuestion>
                <mgmtInvSeriesId>S000004310</mgmtInvSeriesId>
                <fundTypes>
                  <fundType>Exchange-Traded Fund</fundType>
                  <indexFundInfo fundType="Index Fund"/>
                </fundTypes>
              </managementInvestmentQuestion>
            </managementInvestmentQuestionSeriesInfo>
          </formData>
        </edgarSubmission>
        """
        parsed = parse_ncen_fund_types_for_series(xml, "S000004310")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(
            parsed["labels"], ["Exchange-Traded Fund", INDEX_FUND_LABEL]
        )
        self.assertTrue(parsed["is_index_fund"])

    def test_parse_ncen_fund_types_legacy_na_is_active(self):
        xml = """
        <edgarSubmission>
          <formData>
            <managementInvestmentQuestionSeriesInfo>
              <managementInvestmentQuestion>
                <mgmtInvSeriesId>S000004570</mgmtInvSeriesId>
                <fundType>N/A</fundType>
              </managementInvestmentQuestion>
            </managementInvestmentQuestionSeriesInfo>
          </formData>
        </edgarSubmission>
        """
        parsed = parse_ncen_fund_types_for_series(xml, "S000004570")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertFalse(parsed["is_index_fund"])
        self.assertEqual(parsed["management_style"], MANAGEMENT_STYLE_ACTIVE)

    def test_ncen_primary_doc_url(self):
        url = ncen_primary_doc_url("0000819118", "0000035402-26-002761")
        self.assertEqual(
            url,
            "https://www.sec.gov/Archives/edgar/data/819118/"
            "000003540226002761/primary_doc.xml",
        )

    def test_management_style_from_ncen_labels(self):
        self.assertEqual(
            management_style_from_ncen_labels([INDEX_FUND_LABEL]),
            MANAGEMENT_STYLE_PASSIVE,
        )
        self.assertEqual(
            management_style_from_ncen_labels(["Fund of Funds"]),
            MANAGEMENT_STYLE_ACTIVE,
        )
        self.assertEqual(
            management_style_from_ncen_labels([], has_legacy_na=True),
            MANAGEMENT_STYLE_ACTIVE,
        )
        self.assertIsNone(management_style_from_ncen_labels([]))


class CacheRefreshTests(unittest.TestCase):
    def test_refresh_skips_cached_series(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-edgar-filing-facts.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "S0001": {
                            "cik": "0000000001",
                            "n_cen": {
                                "accession_number": "x",
                                "registrant_classification_type": "N-1A",
                                "is_open_end": True,
                                "fund_types": {
                                    "labels": [],
                                    "is_index_fund": False,
                                    "management_style": "Active",
                                },
                            },
                            "prospectus": None,
                            "errors": {},
                        }
                    }
                )
                + "\n"
            )
            funds = pd.DataFrame(
                {
                    "edgartools_series_id": ["S0001"],
                    "edgartools_cik": ["0000000001"],
                    "market_identifier": ["AAA"],
                }
            )
            with patch.object(mod, "fetch_series_filing_facts") as fetch:
                refresh_edgar_filing_facts_cache(funds, cache_file)
                fetch.assert_not_called()

    def test_refresh_refetches_when_ncen_missing_registrant_classification(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-edgar-filing-facts.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "S0001": {
                            "cik": "0000000001",
                            "n_cen": {"accession_number": "x", "series": {}},
                            "prospectus": None,
                            "errors": {},
                        }
                    }
                )
                + "\n"
            )
            funds = pd.DataFrame(
                {
                    "edgartools_series_id": ["S0001"],
                    "edgartools_cik": ["0000000001"],
                    "market_identifier": ["AAA"],
                }
            )
            with patch.object(mod, "fetch_series_filing_facts") as fetch:
                fetch.return_value = {"cik": "0000000001", "n_cen": {}, "prospectus": None}
                refresh_edgar_filing_facts_cache(funds, cache_file)
                fetch.assert_called_once()

    def test_refresh_backfills_when_ncen_missing_fund_types(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-edgar-filing-facts.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "S0001": {
                            "cik": "0000000001",
                            "n_cen": {
                                "accession_number": "x",
                                "registrant_classification_type": "N-1A",
                                "is_open_end": True,
                                "series": {"series_id": "S0001"},
                            },
                            "prospectus": {"fund_name": "Cached"},
                            "errors": {},
                        }
                    }
                )
                + "\n"
            )
            funds = pd.DataFrame(
                {
                    "edgartools_series_id": ["S0001"],
                    "edgartools_cik": ["0000000001"],
                    "market_identifier": ["AAA"],
                }
            )
            enriched = {
                "accession_number": "x",
                "registrant_classification_type": "N-1A",
                "is_open_end": True,
                "fund_types": {
                    "labels": ["Index Fund"],
                    "is_index_fund": True,
                    "management_style": "Passive",
                },
            }
            with patch.object(mod, "backfill_ncen_fund_types") as backfill:
                with patch.object(mod, "fetch_series_filing_facts") as fetch:
                    backfill.return_value = (enriched, None)
                    refresh_edgar_filing_facts_cache(funds, cache_file)
                    backfill.assert_called_once()
                    fetch.assert_not_called()
                    payload = json.loads(cache_file.read_text())
                    self.assertTrue(payload["S0001"]["n_cen"]["fund_types"]["is_index_fund"])
                    self.assertEqual(payload["S0001"]["prospectus"]["fund_name"], "Cached")


if __name__ == "__main__":
    unittest.main()
