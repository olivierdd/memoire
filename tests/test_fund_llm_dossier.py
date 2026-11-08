import json
import unittest
from pathlib import Path

from helpers.timeseries_functions.fund_llm_dossier import (
    build_dossier,
    build_user_prompt,
    dossier_json,
    timeseries_check_dir,
)
from helpers.timeseries_functions.save_timeseries_check import find_project_root

SAMPLE_ISIN = "US4613088016"


class FundLlmDossierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check_dir = timeseries_check_dir(
            SAMPLE_ISIN, project_root=find_project_root()
        )

    def test_build_dossier_excludes_name_and_management_label(self) -> None:
        dossier = build_dossier(self.check_dir)
        profile = dossier["fund_profile"]
        self.assertIsInstance(profile, dict)
        self.assertNotIn("name", profile)
        self.assertNotIn("fund_type", profile)
        self.assertEqual(profile.get("isin"), SAMPLE_ISIN)

    def test_build_dossier_includes_mismatch_rows_only(self) -> None:
        dossier = build_dossier(self.check_dir)
        mismatches = dossier["source_comparison_mismatches"]
        self.assertIsInstance(mismatches, list)
        self.assertEqual(len(mismatches), 2)
        self.assertTrue(all(row["match"] == "mismatch" for row in mismatches))

    def test_largest_index_gaps_limited_to_eight(self) -> None:
        dossier = build_dossier(self.check_dir)
        gaps = dossier["largest_index_gaps_months"]
        self.assertIsInstance(gaps, list)
        self.assertEqual(len(gaps), 8)
        self.assertIn("gap_vs_index_bp", gaps[0])

    def test_user_prompt_contains_dossier_json(self) -> None:
        dossier = build_dossier(self.check_dir)
        prompt = build_user_prompt(dossier)
        self.assertIn("Return only JSON", prompt)
        self.assertIn(SAMPLE_ISIN, prompt)
        roundtrip = json.loads(dossier_json(dossier))
        self.assertAlmostEqual(
            roundtrip["regression"]["statistics"]["beta"], 0.927, places=3
        )


if __name__ == "__main__":
    unittest.main()
