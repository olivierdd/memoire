import unittest

import pandas as pd

from helpers.timeseries_functions.series_v2_pipeline import (
    drop_identifiers_from_panel,
    drop_isins_from_funds_frame,
    lasting_breaks,
    repair_distribution_day_tr,
    rescale_level_breaks,
    summarize_level_jumps,
    thesis_sample_drop_isins,
    tr_result_breaks,
)


def _magellan_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "column": [10, 11, 20, 21, 22],
            "id": [
                "S&PCOMP",
                "S&PCOMP",
                "US3161841008",
                "US3161841008",
                "US3161841008",
            ],
            "name": [
                "S&P 500 - TOT RETURN IND",
                "S&P 500 - TOT RETURN IND",
                "Fund A - TOT RETURN IND",
                "Fund A - TOT RETURN IND",
                "Fund A - PRICE",
            ],
            "header": [
                "S&P 500 TR",
                "S&P 500 TR %",
                "US3161841008 TR",
                "US3161841008 TR %",
                "US3161841008 Price %",
            ],
        }
    )


class RepairDistributionDayTrTests(unittest.TestCase):
    def test_kept_spikes_list_excludes_panel_absent_isins(self):
        # kept_spikes is pruned to ISINs on the working panel; absent funds
        # (e.g. former US66538H5919) must not appear in the Decision log.
        catalog = _magellan_catalog()
        dates = pd.to_datetime(["2015-12-03", "2015-12-04", "2015-12-07"])
        observations = pd.DataFrame(
            {
                10: [100.0, 100.5, 101.0],
                11: [0.0, 0.005, 0.005],
                20: [100.0, 136.0, 136.7],
                21: [0.0, 0.36, 0.005],
                22: [0.0, -0.021, 0.005],
            },
            index=pd.Index(dates, name="date"),
        )

        repaired, log = repair_distribution_day_tr(catalog, observations)

        self.assertFalse(log.empty)
        self.assertTrue((log["isin"] != "US66538H5919").all())
        self.assertIn("US3161841008", set(log["isin"]))
        self.assertEqual(list(repaired.columns), list(observations.columns))
        magellan = log.loc[log["isin"].eq("US3161841008")].iloc[0]
        self.assertEqual(magellan["decision"], "repaired")
        self.assertAlmostEqual(float(repaired.loc[dates[1], 21]), 0.005, places=8)
        self.assertIn("+36%", str(magellan["defect"]))
        self.assertIn("Forward repair", str(magellan["outcome"]))
        self.assertNotIn("is set to the S&P return", str(magellan["defect"]))
        self.assertEqual(str(magellan["why"]), str(magellan["outcome"]))
        self.assertAlmostEqual(float(magellan["price_return"]), -0.021, places=8)
        self.assertAlmostEqual(float(magellan["market_return"]), 0.005, places=8)

    def test_skips_already_clean_ex_distribution_day(self):
        # Yahoo-style Magellan day: Price falls on the distribution, TR ≈ S&P.
        # Must not overwrite with an S&P proxy / forward rescale.
        catalog = _magellan_catalog()
        dates = pd.to_datetime(["2015-12-03", "2015-12-04", "2015-12-07"])
        observations = pd.DataFrame(
            {
                10: [100.0, 102.053, 102.5],
                11: [0.0, 0.020534, 0.004],
                20: [100.0, 102.156, 102.6],
                21: [0.0, 0.021560, 0.004],
                22: [0.0, -0.021118, 0.004],
            },
            index=pd.Index(dates, name="date"),
        )

        repaired, log = repair_distribution_day_tr(catalog, observations)

        magellan = log.loc[log["isin"].eq("US3161841008")].iloc[0]
        self.assertEqual(magellan["decision"], "skipped — already clean")
        self.assertEqual(int(magellan["cells"]), 0)
        self.assertIn("+36%", str(magellan["defect"]))
        self.assertIn("Already clean", str(magellan["outcome"]))
        self.assertNotIn("Forward repair", str(magellan["outcome"]))
        self.assertNotIn("set to the S&P return", str(magellan["outcome"]))
        self.assertEqual(str(magellan["why"]), str(magellan["outcome"]))
        pd.testing.assert_series_equal(repaired[20], observations[20], check_names=False)
        pd.testing.assert_series_equal(repaired[21], observations[21], check_names=False)

    def test_repairs_when_price_tr_disagree_and_far_from_market(self):
        catalog = pd.DataFrame(
            {
                "column": [11, 30, 31, 32],
                "id": ["S&PCOMP", "US78472P1093", "US78472P1093", "US78472P1093"],
                "name": ["S&P 500", "Fund B", "Fund B", "Fund B"],
                "header": [
                    "S&P 500 TR %",
                    "US78472P1093 TR",
                    "US78472P1093 TR %",
                    "US78472P1093 Price %",
                ],
            }
        )
        dates = pd.to_datetime(["2019-12-19", "2019-12-20", "2019-12-23"])
        observations = pd.DataFrame(
            {
                11: [0.0, 0.005, 0.001],
                30: [100.0, 104.8485, 105.0],
                31: [0.0, 0.048485, 0.001],
                32: [0.0, -0.0407, 0.001],
            },
            index=pd.Index(dates, name="date"),
        )

        repaired, log = repair_distribution_day_tr(catalog, observations)

        row = log.loc[log["isin"].eq("US78472P1093")].iloc[0]
        self.assertEqual(row["decision"], "repaired")
        self.assertIn("S&P return", str(row["adjustment"]))
        self.assertIn("+24%", str(row["defect"]))
        self.assertIn("+4.85%", str(row["outcome"]))
        self.assertIn("Forward repair", str(row["outcome"]))
        self.assertAlmostEqual(float(row["return_before"]), 0.048485, places=6)
        self.assertAlmostEqual(float(row["price_return"]), -0.0407, places=6)
        self.assertAlmostEqual(float(repaired.loc[dates[1], 31]), 0.005, places=8)

    def test_one_day_repair_victory_ex_distribution_spike(self):
        # Victory MUXAX 2024-12-13: TR +15.57% with flat price, then both fall
        # ≈13% on the pay date. One-day repair replaces the ex-date print with
        # the price return and recomputes the next return so later levels stay.
        catalog = pd.DataFrame(
            {
                "column": [11, 40, 41, 42],
                "id": [
                    "S&PCOMP",
                    "US92646A2520",
                    "US92646A2520",
                    "US92646A2520",
                ],
                "name": [
                    "S&P 500",
                    "Victory S&P 500 Index Fund;A - TOT RETURN IND",
                    "Victory S&P 500 Index Fund;A - TOT RETURN IND",
                    "Victory S&P 500 Index Fund;A - PRICE",
                ],
                "header": [
                    "S&P 500 TR %",
                    "US92646A2520 TR",
                    "US92646A2520 TR %",
                    "US92646A2520 Price %",
                ],
            }
        )
        dates = pd.to_datetime(["2024-12-12", "2024-12-13", "2024-12-16"])
        observations = pd.DataFrame(
            {
                11: [0.0, 0.000099, 0.003933],
                40: [24.153055, 27.913427, 24.257771],
                41: [0.0, 0.155689, -0.130964],
                42: [0.0, 0.0, -0.130964],
            },
            index=pd.Index(dates, name="date"),
        )

        repaired, log = repair_distribution_day_tr(catalog, observations)

        row = log.loc[log["isin"].eq("US92646A2520")].iloc[0]
        self.assertEqual(row["decision"], "repaired")
        self.assertIn("price return", str(row["adjustment"]))
        self.assertIn("15.57%", str(row["defect"]))
        self.assertIn("One-day repair", str(row["outcome"]))
        self.assertNotIn("Only the ex-date total-return print is replaced", str(row["defect"]))
        self.assertAlmostEqual(float(repaired.loc[dates[1], 41]), 0.0, places=8)
        self.assertAlmostEqual(
            float(repaired.loc[dates[1], 40]),
            float(observations.loc[dates[0], 40]),
            places=6,
        )
        # Later level preserved; next return absorbs the two-day path.
        self.assertAlmostEqual(
            float(repaired.loc[dates[2], 40]),
            float(observations.loc[dates[2], 40]),
            places=6,
        )
        expected_next = (1.0 + 0.155689) * (1.0 - 0.130964) - 1.0
        self.assertAlmostEqual(
            float(repaired.loc[dates[2], 41]), expected_next, places=6
        )

    def test_skips_repair_when_date_absent(self):
        catalog = pd.DataFrame(
            {
                "column": [11],
                "id": ["S&PCOMP"],
                "name": ["S&P 500"],
                "header": ["S&P 500 TR %"],
            }
        )
        observations = pd.DataFrame(
            {11: [0.01, 0.02]},
            index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
        )

        repaired, log = repair_distribution_day_tr(catalog, observations)

        self.assertTrue(log.empty)
        pd.testing.assert_frame_equal(repaired, observations)


def _level_jump_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "column": [10, 11, 20, 21, 22, 23],
            "id": [
                "S&PCOMP",
                "S&PCOMP",
                "US1888501012",
                "US1888501012",
                "US1888501012",
                "US1888501012",
            ],
            "name": [
                "S&P 500 - TOT RETURN IND",
                "S&P 500 - TOT RETURN IND",
                "Clipper - TOT RETURN IND",
                "Clipper - TOT RETURN IND",
                "Clipper - PRICE",
                "Clipper - PRICE",
            ],
            "header": [
                "S&P 500 TR",
                "S&P 500 TR %",
                "US1888501012 TR",
                "US1888501012 TR %",
                "US1888501012 Price",
                "US1888501012 Price %",
            ],
            "category": ["Index"] * 2 + ["Active MF"] * 4,
            "note": [
                "Total return index",
                "Daily simple return (%)",
                "Total return index",
                "Daily simple return (%)",
                "Price level",
                "Daily simple return (%)",
            ],
        }
    )


class LastingBreaksAndLevelJumpSummaryTests(unittest.TestCase):
    def test_lasting_breaks_flags_sticky_price_and_tr(self):
        catalog = _level_jump_catalog()
        dates = pd.to_datetime(
            ["2025-05-09", "2025-05-12", "2025-05-13", "2025-05-14"]
        )
        # Sticky −90% on Price and TR vs flat S&P — should flag both sides.
        observations = pd.DataFrame(
            {
                10: [100.0, 100.0, 100.5, 101.0],
                11: [0.0, 0.0, 0.005, 0.005],
                20: [1000.0, 100.0, 100.5, 101.0],
                21: [0.0, -0.90, 0.005, 0.005],
                22: [1000.0, 100.0, 100.5, 101.0],
                23: [0.0, -0.90, 0.005, 0.005],
            },
            index=pd.Index(dates, name="date"),
        )

        breaks, _ = lasting_breaks(observations, catalog)
        sides = {(b["isin"], b["side"], b["date"].strftime("%Y-%m-%d")) for b in breaks}
        self.assertIn(("US1888501012", "TR", "2025-05-12"), sides)
        self.assertIn(("US1888501012", "Price", "2025-05-12"), sides)

    def test_lasting_breaks_rejects_full_reversal_spike(self):
        # +60% then −37.5% restores the level (s ≈ 0); must not flag.
        catalog = _level_jump_catalog()
        dates = pd.to_datetime(
            ["2025-05-09", "2025-05-12", "2025-05-13", "2025-05-14"]
        )
        observations = pd.DataFrame(
            {
                10: [100.0, 100.0, 100.5, 101.0],
                11: [0.0, 0.0, 0.005, 0.005],
                20: [100.0, 160.0, 100.0, 101.0],
                21: [0.0, 0.60, -0.375, 0.01],
                22: [100.0, 160.0, 100.0, 101.0],
                23: [0.0, 0.60, -0.375, 0.01],
            },
            index=pd.Index(dates, name="date"),
        )
        breaks, _ = lasting_breaks(observations, catalog)
        self.assertEqual(breaks, [])

    def test_lasting_breaks_rejects_overshooting_reversal(self):
        # +60% then −70% compounds to ≈ −52%: large |s| but opposite sign.
        # An absolute-value persistence test would flag the +60% day; the
        # signed ratio s/r ≥ 1/2 must not. (The −70% day may still flag on
        # its own if that down-move then sticks — that is a separate event.)
        catalog = _level_jump_catalog()
        dates = pd.to_datetime(
            ["2025-05-09", "2025-05-12", "2025-05-13", "2025-05-14"]
        )
        observations = pd.DataFrame(
            {
                10: [100.0, 100.0, 100.5, 101.0],
                11: [0.0, 0.0, 0.005, 0.005],
                20: [100.0, 160.0, 48.0, 48.5],
                21: [0.0, 0.60, -0.70, 0.01],
                22: [100.0, 160.0, 48.0, 48.5],
                23: [0.0, 0.60, -0.70, 0.01],
            },
            index=pd.Index(dates, name="date"),
        )
        breaks, _ = lasting_breaks(observations, catalog)
        up_days = [
            b for b in breaks if b["date"].strftime("%Y-%m-%d") == "2025-05-12"
        ]
        self.assertEqual(up_days, [])

    def test_result_is_tr_only_and_decision_uses_full_scan(self):
        catalog = _level_jump_catalog()
        dates = pd.to_datetime(
            ["2025-05-09", "2025-05-12", "2025-05-13", "2025-05-14"]
        )
        observations = pd.DataFrame(
            {
                10: [100.0, 100.0, 100.5, 101.0],
                11: [0.0, 0.0, 0.005, 0.005],
                20: [1000.0, 100.0, 100.5, 101.0],
                21: [0.0, -0.90, 0.005, 0.005],
                22: [1000.0, 100.0, 100.5, 101.0],
                23: [0.0, -0.90, 0.005, 0.005],
            },
            index=pd.Index(dates, name="date"),
        )

        controls, issue_summary, all_breaks, result_breaks = summarize_level_jumps(
            catalog, observations, use_scale=False
        )
        self.assertEqual(controls["level_jump"], 0.50)
        self.assertTrue(all(b["side"] == "TR" for b in result_breaks))
        self.assertEqual(len(result_breaks), 1)
        self.assertEqual(len(all_breaks), 2)
        flagged = issue_summary.loc[issue_summary["level_jumps"].gt(0)]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(str(flagged.iloc[0]["id"]), "US1888501012")

        adjusted, log = rescale_level_breaks(catalog, observations, breaks=all_breaks)
        rescaled = log.loc[log["decision"].eq("rescaled")]
        self.assertGreaterEqual(len(rescaled), 1)
        self.assertTrue(set(rescaled["series"]).issubset({"Price", "TR"}))
        # History ÷100 before the break: prior TR level should shrink.
        self.assertAlmostEqual(float(adjusted.loc[dates[0], 20]), 10.0, places=6)

    def test_tr_result_breaks_scale_gate_drops_post_split_days(self):
        # Synthetic: TR |r| median jumps 5× after mid-point; a sticky jump after
        # the split must leave Result when use_scale=True.
        catalog = _level_jump_catalog()
        n = 300
        dates = pd.bdate_range("2020-01-02", periods=n)
        market = pd.Series(0.001, index=dates)
        fund = pd.Series(0.001, index=dates)
        fund.iloc[150:] = 0.01  # 10× typical |r| after day 150
        # Sticky −60% well after the scale change
        jump_i = 200
        fund.iloc[jump_i] = -0.60
        fund.iloc[jump_i + 1] = 0.01
        fund.iloc[jump_i + 2] = 0.01
        level = (1.0 + fund).cumprod() * 100.0
        market_level = (1.0 + market).cumprod() * 100.0
        price_ret = fund.copy()
        price_level = level.copy()
        observations = pd.DataFrame(
            {
                10: market_level.to_numpy(),
                11: market.to_numpy(),
                20: level.to_numpy(),
                21: fund.to_numpy(),
                22: price_level.to_numpy(),
                23: price_ret.to_numpy(),
            },
            index=dates,
        )
        breaks, _ = lasting_breaks(observations, catalog)
        self.assertTrue(any(b["side"] == "TR" and b["date"] == dates[jump_i] for b in breaks))

        gated = tr_result_breaks(
            breaks, catalog, observations, use_scale=True, scale_window=60, scale_factor=5
        )
        ungated = tr_result_breaks(breaks, catalog, observations, use_scale=False)
        self.assertTrue(any(b["date"] == dates[jump_i] for b in ungated if b["side"] == "TR"))
        self.assertFalse(any(b["date"] == dates[jump_i] for b in gated))


class ThesisSampleDropTests(unittest.TestCase):
    def test_phdg_is_on_the_drop_list(self):
        self.assertIn("US46090A7054", thesis_sample_drop_isins())

    def test_drop_identifiers_removes_all_series_for_isin(self):
        catalog = pd.DataFrame(
            {
                "column": [1, 2, 3, 4, 5],
                "id": [
                    "S&PCOMP",
                    "US46090A7054",
                    "US46090A7054",
                    "US1111111111",
                    "US1111111111",
                ],
                "header": [
                    "S&P 500 TR %",
                    "US46090A7054 TR",
                    "US46090A7054 TR %",
                    "US1111111111 TR",
                    "US1111111111 TR %",
                ],
            }
        )
        dates = pd.to_datetime(["2020-01-02", "2020-01-03"])
        observations = pd.DataFrame(
            {
                1: [0.01, 0.02],
                2: [100.0, 101.0],
                3: [0.01, 0.01],
                4: [100.0, 102.0],
                5: [0.02, 0.02],
            },
            index=dates,
        )

        kept_catalog, kept_obs, log = drop_identifiers_from_panel(
            catalog, observations
        )

        self.assertEqual(list(kept_catalog["id"]), ["S&PCOMP", "US1111111111", "US1111111111"])
        self.assertEqual(list(kept_obs.columns), [1, 4, 5])
        self.assertEqual(len(log), 1)
        self.assertEqual(str(log.iloc[0]["isin"]), "US46090A7054")
        self.assertTrue(bool(log.iloc[0]["present"]))
        self.assertEqual(int(log.iloc[0]["series_removed"]), 2)
        self.assertEqual(str(log.iloc[0]["ticker"]), "PHDG")

    def test_drop_isins_from_funds_frame(self):
        funds = pd.DataFrame(
            {
                "Name": ["Keep", "Drop PHDG"],
                "ISIN": ["US1111111111", "US46090A7054"],
            }
        )
        cleaned = drop_isins_from_funds_frame(funds)
        self.assertEqual(list(cleaned["ISIN"]), ["US1111111111"])


if __name__ == "__main__":
    unittest.main()
