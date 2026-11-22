import unittest

from helpers.funds_functions.funds_pipeline_conclusion import (
    academic_closing_paragraphs,
    attrition_figure_html,
    attrition_table,
    composition_figure_html,
    contingency_table,
    reclassification_figure_html,
    verification_table,
)


class FundsPipelineConclusionTests(unittest.TestCase):
    def test_tables_and_prose(self):
        stages = [("Loaded", 100), ("Selected", 80), ("Final", 50)]
        counts = {
            "loaded": 100,
            "selected": 80,
            "final": 50,
            "confirmed": 40,
            "reclassified": 5,
            "drop_other": 3,
            "cusip_filled": 2,
            "yahoo_filled": 4,
        }
        matrix = {
            "active_mf": 20,
            "passive_mf": 10,
            "active_etf": 12,
            "passive_etf": 8,
        }
        attrition = attrition_table(stages)
        self.assertEqual(list(attrition["Funds"]), [100, 80, 50])
        contingency = contingency_table(matrix, total=50)
        self.assertIn("Mutual fund", contingency.columns)
        verification = verification_table(counts)
        self.assertEqual(len(verification), 5)
        self.assertIn("Figure 1", attrition_figure_html(stages))
        self.assertIn("Figure 2", composition_figure_html(matrix, total=50))
        self.assertIn("Figure 3", reclassification_figure_html(counts))
        prose = academic_closing_paragraphs(
            {
                "counts": counts,
                "matrix": matrix,
                "excel_export": "output-data/v2-funds-normalized.xlsx",
            }
        )
        self.assertIn("Purpose and contribution", prose)
        self.assertIn("50", prose)


if __name__ == "__main__":
    unittest.main()
