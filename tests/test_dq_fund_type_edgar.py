import unittest

from helpers.funds_functions.dq_fund_type_edgar import (
    FUND_TYPE_ACTIVE,
    FUND_TYPE_PASSIVE,
    evaluate_fund_row,
    normalize_lipper_fund_type,
    proof_fund_type_from_ncen,
    summarize_lipper_edgar_fund_type_comparison,
)


class NormalizeFundTypeTests(unittest.TestCase):
    def test_lipper_values(self):
        self.assertEqual(normalize_lipper_fund_type("Active"), FUND_TYPE_ACTIVE)
        self.assertEqual(normalize_lipper_fund_type("Passive"), FUND_TYPE_PASSIVE)
        self.assertEqual(normalize_lipper_fund_type("To Check"), "To Check")


class NcenFundTypeProofTests(unittest.TestCase):
    def test_index_fund_is_passive(self):
        proof = proof_fund_type_from_ncen(
            {
                "accession_number": "acc",
                "series": {"series_id": "S1", "name": "500 Index Fund"},
                "fund_types": {
                    "labels": ["Index Fund"],
                    "is_index_fund": True,
                    "management_style": "Passive",
                },
            }
        )
        self.assertEqual(proof["classification"], FUND_TYPE_PASSIVE)
        self.assertEqual(proof["source"], "edgar_n_cen")

    def test_legacy_na_is_active(self):
        proof = proof_fund_type_from_ncen(
            {
                "accession_number": "acc",
                "series": {"series_id": "S1", "name": "Focus Fund"},
                "fund_types": {
                    "labels": [],
                    "is_index_fund": False,
                    "management_style": "Active",
                },
            }
        )
        self.assertEqual(proof["classification"], FUND_TYPE_ACTIVE)

    def test_fund_of_funds_is_active(self):
        proof = proof_fund_type_from_ncen(
            {
                "accession_number": "acc",
                "series": {"series_id": "S1"},
                "fund_types": {
                    "labels": ["Fund of Funds"],
                    "is_index_fund": False,
                    "management_style": "Active",
                },
            }
        )
        self.assertEqual(proof["classification"], FUND_TYPE_ACTIVE)

    def test_missing_fund_types_enrichment(self):
        proof = proof_fund_type_from_ncen(
            {"accession_number": "acc", "series": {"series_id": "S1"}}
        )
        self.assertIsNone(proof["classification"])
        self.assertIn("backfill", proof["logic"])


class SummarizeFundTypeComparisonTests(unittest.TestCase):
    def test_counts(self):
        cache = {
            "records": {
                "A": {
                    "fund_type": {"classification": "Passive"},
                    "comparison": {
                        "lipper_fund_type_normalized": "Passive",
                        "lipper_matches_edgar_fund_type": True,
                    },
                },
                "B": {
                    "fund_type": {"classification": "Active"},
                    "comparison": {
                        "lipper_fund_type_normalized": "Passive",
                        "lipper_matches_edgar_fund_type": False,
                    },
                },
            }
        }
        summary = summarize_lipper_edgar_fund_type_comparison(cache=cache)
        self.assertEqual(summary["lipper_edgar_match"], 1)
        self.assertEqual(summary["lipper_edgar_mismatch"], 1)


class EvaluateFundTypeRowTests(unittest.TestCase):
    def test_lipper_comparison(self):
        filing_facts = {
            "S0001": {
                "n_cen": {
                    "accession_number": "acc",
                    "series": {"series_id": "S0001", "name": "Index"},
                    "fund_types": {
                        "labels": ["Index Fund"],
                        "is_index_fund": True,
                        "management_style": "Passive",
                    },
                }
            }
        }
        row = evaluate_fund_row(
            isin="US1234567890",
            name="Fund",
            lipper_fund_type="Passive",
            market_identifier="AAA",
            edgartools_series_id="S0001",
            filing_facts=filing_facts,
        )
        self.assertTrue(row["comparison"]["lipper_matches_edgar_fund_type"])
        self.assertEqual(row["lipper_fund_type"], "Passive")


if __name__ == "__main__":
    unittest.main()
