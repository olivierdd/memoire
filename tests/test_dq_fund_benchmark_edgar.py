import unittest

from helpers.funds_functions.dq_fund_benchmark_edgar import (
    SP500_PRICE,
    SP500_TOTAL_RETURN,
    SP500_UNSPECIFIED,
    classify_sp500_benchmark_label,
    evaluate_fund_row,
    is_sp500_series_name,
    normalize_lipper_benchmark,
    proof_sp500_benchmark,
    summarize_lipper_edgar_benchmark_comparison,
)


class ClassifyBenchmarkLabelTests(unittest.TestCase):
    def test_generic_sp500_index(self):
        hit = classify_sp500_benchmark_label(
            "S&P 500 ® Index (reflects no deduction for fees, expenses or taxes)"
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit["variant"], SP500_UNSPECIFIED)

    def test_total_return(self):
        hit = classify_sp500_benchmark_label(
            "S&P 500 Total Return Index (reflects no deduction for fees, expenses or taxes)"
        )
        self.assertEqual(hit["variant"], SP500_TOTAL_RETURN)

    def test_price_index(self):
        hit = classify_sp500_benchmark_label(
            "Standard & Poor's 500 Composite Stock Price Index"
        )
        self.assertEqual(hit["variant"], SP500_PRICE)

    def test_typographic_apostrophe_in_poors(self):
        hit = classify_sp500_benchmark_label(
            "Standard & Poor\u2019s 500 Index (reflects no deduction for fees, expenses, or taxes)"
        )
        self.assertIsNotNone(hit)
        self.assertEqual(hit["variant"], SP500_UNSPECIFIED)
        self.assertIn("\u2019", hit["raw_label"])

    def test_excludes_growth(self):
        self.assertIsNone(
            classify_sp500_benchmark_label(
                "S&P 500 Growth Index (reflects no deduction for fees, expenses or taxes)"
            )
        )


class SeriesNameTests(unittest.TestCase):
    def test_sp500_index_fund_name(self):
        self.assertTrue(is_sp500_series_name("Schwab S&P 500 Index Fund"))

    def test_buffer_excluded(self):
        self.assertFalse(is_sp500_series_name("NVIT S&P 500 1-Year Buffer Fund Jan"))


class ProofTests(unittest.TestCase):
    def test_prospectus_benchmark_indices(self):
        facts = {
            "S0001": {
                "n_cen": {"series": {"series_id": "S0001", "name": "Focus Fund"}},
                "prospectus": {
                    "accession_number": "acc-1",
                    "filing_date": "2026-01-01",
                    "form": "497K",
                    "fund_name": "Focus Fund",
                    "benchmark_indices": [
                        "Russell 1000 Index (reflects no deduction for fees, expenses or taxes)",
                        "S&P 500 Index Return (reflects no deduction for fees, expenses or taxes)",
                    ],
                    "investment_objective": "Long-term capital appreciation.",
                },
            }
        }
        proof = proof_sp500_benchmark(
            series_id="S0001", fund_name="Focus Fund", filing_facts=facts
        )
        self.assertTrue(proof["classification"])
        self.assertEqual(proof["source"], "edgar_prospectus_benchmark_indices")
        self.assertEqual(proof["variant"], SP500_UNSPECIFIED)

    def test_name_fallback_when_benchmark_empty(self):
        facts = {
            "S0002": {
                "n_cen": {"series": {"series_id": "S0002", "name": "Schwab S&P 500 Index Fund"}},
                "prospectus": {
                    "fund_name": "Schwab S&P 500 Index Fund",
                    "benchmark_indices": [],
                    "investment_objective": "x" * 50,
                },
            }
        }
        proof = proof_sp500_benchmark(
            series_id="S0002",
            fund_name="Schwab S&P 500 Index Fund;Investor",
            filing_facts=facts,
        )
        self.assertTrue(proof["classification"])
        self.assertIn("name", proof["source"])


class LipperNormalizationTests(unittest.TestCase):
    def test_lipper_tr_flag(self):
        lipper = normalize_lipper_benchmark("S&P 500 TR", True)
        self.assertTrue(lipper["references_sp500"])
        self.assertEqual(lipper["variant"], SP500_TOTAL_RETURN)


class EvaluateRowTests(unittest.TestCase):
    def test_lipper_edgar_match(self):
        facts = {
            "S0001": {
                "n_cen": {"series": {"series_id": "S0001", "name": "500 Index Fund"}},
                "prospectus": {
                    "benchmark_indices": [
                        "S&P 500 Total Return Index (reflects no deduction for fees, expenses or taxes)"
                    ],
                    "investment_objective": "Match the index.",
                },
            }
        }
        row = evaluate_fund_row(
            isin="US1234567890",
            name="Fund",
            lipper_benchmark_name="S&P 500 TR",
            lipper_is_sp500=True,
            market_identifier="VFIAX",
            edgartools_series_id="S0001",
            filing_facts=facts,
        )
        self.assertTrue(row["comparison"]["lipper_matches_edgar_sp500_presence"])
        self.assertTrue(row["comparison"]["lipper_matches_edgar_sp500_variant"])

    def test_vanguard_institutional_index_curly_apostrophe(self):
        facts = {
            "S000002853": {
                "n_cen": {
                    "series": {
                        "series_id": "S000002853",
                        "name": "VANGUARD INSTITUTIONAL INDEX FUND",
                    }
                },
                "prospectus": {
                    "accession_number": "0000862084-26-000060",
                    "fund_name": "Vanguard Institutional Index Fund",
                    "benchmark_indices": [
                        "Dow Jones U.S. Total Stock Market Float Adjusted Index (reflects no deduction for fees, expenses, or taxes)",
                        "Standard & Poor\u2019s 500 Index (reflects no deduction for fees, expenses, or taxes)",
                    ],
                    "investment_objective": (
                        "Vanguard Institutional Index Fund seeks to track the performance "
                        "of a benchmark index that measures the investment return of "
                        "large-capitalization stocks."
                    ),
                },
            }
        }
        row = evaluate_fund_row(
            isin="US9220401007",
            name="Vanguard Institutional Index Fund;Institutional",
            lipper_benchmark_name="S&P 500 TR",
            lipper_is_sp500=True,
            market_identifier="VINIX",
            edgartools_series_id="S000002853",
            filing_facts=facts,
        )
        proof = row["sp500_benchmark"]
        self.assertTrue(proof["classification"])
        self.assertEqual(proof["variant"], SP500_UNSPECIFIED)
        self.assertEqual(proof["source"], "edgar_prospectus_benchmark_indices")
        self.assertTrue(row["comparison"]["lipper_matches_edgar_sp500_presence"])
        self.assertTrue(row["comparison"]["lipper_matches_edgar_sp500_variant"])

    def test_missing_series_is_not_a_presence_mismatch(self):
        row = evaluate_fund_row(
            isin="US0669235337",
            name="iShares S&P 500 Index Fund;Service",
            lipper_benchmark_name="S&P 500 TR",
            lipper_is_sp500=True,
            market_identifier="BSPSX",
            edgartools_series_id=None,
            filing_facts={},
        )
        self.assertIsNone(row["sp500_benchmark"]["classification"])
        self.assertIsNone(row["comparison"]["edgar_references_sp500"])
        self.assertIsNone(row["comparison"]["lipper_matches_edgar_sp500_presence"])

    def test_explicit_edgar_negative_is_a_mismatch(self):
        facts = {
            "S0009": {
                "n_cen": {"series": {"series_id": "S0009", "name": "Focus Fund"}},
                "prospectus": {
                    "fund_name": "Focus Fund",
                    "benchmark_indices": [
                        "Russell 1000 Index (reflects no deduction for fees, expenses or taxes)"
                    ],
                    "investment_objective": "x" * 40,
                },
            }
        }
        row = evaluate_fund_row(
            isin="US0000000001",
            name="Focus Fund",
            lipper_benchmark_name="S&P 500 TR",
            lipper_is_sp500=True,
            market_identifier="FOCUS",
            edgartools_series_id="S0009",
            filing_facts=facts,
        )
        self.assertFalse(row["sp500_benchmark"]["classification"])
        self.assertFalse(row["comparison"]["edgar_references_sp500"])
        self.assertFalse(row["comparison"]["lipper_matches_edgar_sp500_presence"])


class SummarizeTests(unittest.TestCase):
    def test_counts(self):
        cache = {
            "records": {
                "A": {
                    "lipper_is_sp500": True,
                    "comparison": {
                        "lipper_references_sp500": True,
                        "edgar_references_sp500": True,
                        "lipper_matches_edgar_sp500_presence": True,
                        "lipper_matches_edgar_sp500_variant": True,
                    },
                },
                "B": {
                    "lipper_is_sp500": True,
                    "comparison": {
                        "lipper_references_sp500": True,
                        "edgar_references_sp500": False,
                        "lipper_matches_edgar_sp500_presence": False,
                    },
                },
            }
        }
        summary = summarize_lipper_edgar_benchmark_comparison(cache=cache)
        self.assertEqual(summary["lipper_edgar_presence_match"], 1)
        self.assertEqual(summary["lipper_edgar_presence_mismatch"], 1)


if __name__ == "__main__":
    unittest.main()
