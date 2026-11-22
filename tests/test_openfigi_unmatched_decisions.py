import unittest

import pandas as pd

from helpers.funds_functions.openfigi_unmatched_decisions import (
    DROP_ISINS,
    IDENTITY_QUALITY_CAVEAT,
    KEEP_ISIN,
    apply_openfigi_unmatched_decisions,
    unmatched_review_frame,
)


class OpenfigiUnmatchedDecisionsTests(unittest.TestCase):
    def test_review_lists_seven_funds_with_six_drops(self):
        review = unmatched_review_frame()
        self.assertEqual(len(review), 7)
        self.assertEqual((review["Decision"] == "Drop").sum(), 6)
        self.assertEqual(
            review.loc[review["ISIN"].eq(KEEP_ISIN), "Decision"].tolist(),
            ["Keep (caveat)"],
        )
        self.assertEqual(set(review.loc[review["Decision"].eq("Drop"), "ISIN"]), DROP_ISINS)

    def test_apply_drops_closed_funds_and_flags_john_hancock(self):
        funds = pd.DataFrame(
            {
                "Name": [
                    "Keep matched",
                    "Johnson Disciplined Large-Cap Fund",
                    "John Hancock US Sector Rotation Fund;NAV",
                    "Fifth Third Dividend Growth Fund;A",
                ],
                "ISIN": [
                    "US0000000001",
                    "US4791648656",
                    KEEP_ISIN,
                    "US3167865654",
                ],
                "isin_found": [True, False, False, False],
            }
        )
        kept, decision_log = apply_openfigi_unmatched_decisions(funds)
        self.assertEqual(len(kept), 2)
        self.assertEqual(
            set(kept["ISIN"].astype(str)),
            {"US0000000001", KEEP_ISIN},
        )
        flagged = kept.loc[kept["ISIN"].eq(KEEP_ISIN), "openfigi_identity_quality"]
        self.assertEqual(flagged.tolist(), [IDENTITY_QUALITY_CAVEAT])
        other = kept.loc[kept["ISIN"].eq("US0000000001"), "openfigi_identity_quality"]
        self.assertTrue(bool(other.isna().all()) or other.tolist() == [pd.NA])
        self.assertTrue(decision_log["present_in_selection"].loc[
            decision_log["ISIN"].isin(["US4791648656", KEEP_ISIN, "US3167865654"])
        ].all())

    def test_apply_requires_isin_column(self):
        with self.assertRaises(KeyError):
            apply_openfigi_unmatched_decisions(pd.DataFrame({"Name": ["x"]}))


if __name__ == "__main__":
    unittest.main()
