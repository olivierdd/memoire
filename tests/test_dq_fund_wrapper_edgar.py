import unittest

from helpers.funds_functions.dq_fund_wrapper_edgar import (
    normalize_lipper_wrapper,
    proof_open_end_from_ncen,
    proof_wrapper_from_ncen,
    proof_wrapper_from_yahoo,
    evaluate_fund_row,
    summarize_lipper_edgar_wrapper_comparison,
)


class NormalizeWrapperTests(unittest.TestCase):
    def test_lipper_values(self):
        self.assertEqual(normalize_lipper_wrapper("ETF"), "ETF")
        self.assertEqual(normalize_lipper_wrapper("mutual fund"), "mutual fund")


class NcenProofTests(unittest.TestCase):
    def test_open_end_n1a(self):
        proof = proof_open_end_from_ncen(
            {
                "registrant_classification_type": "N-1A",
                "is_open_end": True,
                "accession_number": "acc",
            }
        )
        self.assertTrue(proof["classification"])
        self.assertEqual(proof["source"], "edgar_n_cen")

    def test_wrapper_etf_ticker_match(self):
        n_cen = {
            "accession_number": "acc",
            "series": {"series_id": "S1", "name": "Test", "has_etf": True},
            "etf": {"ticker": "VTV", "exchange": "ARCX"},
        }
        proof = proof_wrapper_from_ncen(n_cen, "VTV", True)
        self.assertEqual(proof["classification"], "ETF")

    def test_wrapper_mutual_when_etf_other_ticker(self):
        n_cen = {
            "accession_number": "acc",
            "series": {"series_id": "S1", "name": "Test", "has_etf": True},
            "etf": {"ticker": "VTV"},
        }
        proof = proof_wrapper_from_ncen(n_cen, "VIVIX", True)
        self.assertEqual(proof["classification"], "mutual fund")

    def test_wrapper_mutual_without_etf_flag(self):
        n_cen = {
            "accession_number": "acc",
            "series": {"series_id": "S1", "name": "Test", "has_etf": False},
            "etf": None,
        }
        proof = proof_wrapper_from_ncen(n_cen, "AUXFX", True)
        self.assertEqual(proof["classification"], "mutual fund")

    def test_wrapper_none_when_not_open_end(self):
        n_cen = {
            "accession_number": "acc",
            "series": {"series_id": "S1", "has_etf": False},
        }
        proof = proof_wrapper_from_ncen(n_cen, "XYZ", False)
        self.assertIsNone(proof["classification"])


class YahooProofTests(unittest.TestCase):
    def test_mutualfund(self):
        proof = proof_wrapper_from_yahoo({"quote_type": "MUTUALFUND", "symbol": "X"})
        self.assertEqual(proof["classification"], "mutual fund")


class SummarizeComparisonTests(unittest.TestCase):
    def test_counts(self):
        cache = {
            "records": {
                "A": {
                    "fund_wrapper": {"classification": "ETF"},
                    "comparison": {"lipper_matches_edgar_wrapper": True},
                },
                "B": {
                    "fund_wrapper": {"classification": "mutual fund"},
                    "comparison": {"lipper_matches_edgar_wrapper": False},
                },
                "C": {
                    "fund_wrapper": {"classification": None},
                    "comparison": {"lipper_matches_edgar_wrapper": None},
                },
            }
        }
        summary = summarize_lipper_edgar_wrapper_comparison(cache=cache)
        self.assertEqual(summary["total_funds"], 3)
        self.assertEqual(summary["lipper_edgar_match"], 1)
        self.assertEqual(summary["lipper_edgar_mismatch"], 1)
        self.assertEqual(summary["no_edgar_fund_wrapper"], 1)


class EvaluateRowTests(unittest.TestCase):
    def test_lipper_comparison(self):
        filing_facts = {
            "S0001": {
                "n_cen": {
                    "registrant_classification_type": "N-1A",
                    "is_open_end": True,
                    "accession_number": "acc",
                    "series": {"series_id": "S0001", "has_etf": False},
                    "etf": None,
                }
            }
        }
        row = evaluate_fund_row(
            isin="US1234567890",
            name="Fund",
            lipper_fund_wrapper="mutual fund",
            market_identifier="AAA",
            edgartools_series_id="S0001",
            filing_facts=filing_facts,
            yahoo_cache={},
            fd_cache={},
        )
        self.assertTrue(row["comparison"]["lipper_matches_edgar_wrapper"])


if __name__ == "__main__":
    unittest.main()
