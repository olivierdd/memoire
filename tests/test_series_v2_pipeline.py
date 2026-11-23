import unittest

import pandas as pd

from helpers.timeseries_functions.series_v2_pipeline import repair_distribution_day_tr


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
                32: [0.0, 0.0, 0.001],
            },
            index=pd.Index(dates, name="date"),
        )

        repaired, log = repair_distribution_day_tr(catalog, observations)

        row = log.loc[log["isin"].eq("US78472P1093")].iloc[0]
        self.assertEqual(row["decision"], "repaired")
        self.assertIn("S&P return", str(row["adjustment"]))
        self.assertAlmostEqual(float(repaired.loc[dates[1], 31]), 0.005, places=8)

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


if __name__ == "__main__":
    unittest.main()
