import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from helpers.timeseries_functions.yahoo_fund_risk_stats import (
    fetch_yahoo_risk_stats,
    load_yahoo_risk_stats_cache,
    parse_fund_performance_payload,
    refresh_yahoo_risk_stats_cache,
    save_yahoo_risk_stats_cache,
    yahoo_alpha_beta_comparison,
    yahoo_vs_lipper_summary,
)

SAMPLE_PAYLOAD = {
    "quoteSummary": {
        "result": [
            {
                "fundPerformance": {
                    "riskOverviewStatistics": {
                        "riskStatistics": [
                            {
                                "year": "3y",
                                "alpha": {"raw": -6.19, "fmt": "-6.19"},
                                "beta": {"raw": 1.3, "fmt": "1.3"},
                                "rSquared": {"raw": 77.14, "fmt": "77.14"},
                            },
                            {
                                "year": "5y",
                                "alpha": {"raw": -4.56},
                                "beta": {"raw": 1.19},
                                "rSquared": {"raw": 80.55},
                            },
                        ]
                    }
                }
            }
        ]
    }
}


class ParseFundPerformanceTests(unittest.TestCase):
    def test_parse_extracts_horizons(self):
        record = parse_fund_performance_payload(SAMPLE_PAYLOAD, ticker="JACNX")
        self.assertEqual(record["symbol"], "JACNX")
        self.assertAlmostEqual(record["horizons"]["3y"]["alpha"], -6.19)
        self.assertAlmostEqual(record["horizons"]["3y"]["beta"], 1.3)
        self.assertAlmostEqual(record["horizons"]["5y"]["beta"], 1.19)
        self.assertNotIn("error", record)

    def test_parse_empty_result(self):
        record = parse_fund_performance_payload({"quoteSummary": {"result": []}})
        self.assertEqual(record["horizons"], {})
        self.assertEqual(record["error"], "no_result")


class CacheTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "risk.json"
            payload = {"ABC": parse_fund_performance_payload(SAMPLE_PAYLOAD, ticker="ABC")}
            save_yahoo_risk_stats_cache(payload, path)
            loaded = load_yahoo_risk_stats_cache(path)
            self.assertIn("ABC", loaded)
            self.assertAlmostEqual(loaded["ABC"]["horizons"]["3y"]["beta"], 1.3)

    @patch("helpers.timeseries_functions.yahoo_fund_risk_stats.fetch_yahoo_risk_stats")
    def test_refresh_skips_cached_success(self, mock_fetch: MagicMock):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "risk.json"
            cached = parse_fund_performance_payload(SAMPLE_PAYLOAD, ticker="HIT")
            save_yahoo_risk_stats_cache({"HIT": cached}, path)
            mock_fetch.return_value = parse_fund_performance_payload(
                SAMPLE_PAYLOAD, ticker="NEW"
            )
            refresh_yahoo_risk_stats_cache(["HIT", "NEW"], path, pause_seconds=0)
            mock_fetch.assert_called_once()
            self.assertEqual(mock_fetch.call_args[0][0], "NEW")


class ComparisonTests(unittest.TestCase):
    def test_yahoo_closer_than_lipper_summary(self):
        comparison = pd.DataFrame(
            [
                {
                    "status": "ok",
                    "horizon": "3y",
                    "isin": "US1",
                    "name": "Fund A",
                    "alpha_pct_per_month": -0.5,
                    "beta": 1.3,
                    "lipper_alpha_pct_per_month": 0.2,
                    "lipper_beta": 0.8,
                    "delta_alpha_pp_per_month": -0.7,
                    "delta_beta": 0.5,
                },
                {
                    "status": "ok",
                    "horizon": "3y",
                    "isin": "US2",
                    "name": "Fund B",
                    "alpha_pct_per_month": 0.1,
                    "beta": 1.0,
                    "lipper_alpha_pct_per_month": 0.12,
                    "lipper_beta": 0.98,
                    "delta_alpha_pp_per_month": -0.02,
                    "delta_beta": 0.02,
                },
            ]
        )
        funds = pd.DataFrame(
            {
                "ISIN": ["US1", "US2"],
                "openfigi_market_id": ["AAA", "BBB"],
            }
        )
        cache = {
            "AAA": {
                "horizons": {
                    "3y": {"alpha": -5.8, "beta": 1.28, "r_squared": 77.0},
                }
            },
            "BBB": {
                "horizons": {
                    "3y": {"alpha": 1.1, "beta": 1.01, "r_squared": 90.0},
                }
            },
        }
        frame = yahoo_alpha_beta_comparison(comparison, funds, cache)
        self.assertEqual(len(frame), 2)
        self.assertTrue(bool(frame.loc[frame["isin"].eq("US1"), "yahoo_closer_alpha"].iloc[0]))
        self.assertTrue(bool(frame.loc[frame["isin"].eq("US1"), "yahoo_agrees_beta"].iloc[0]))
        summary = yahoo_vs_lipper_summary(frame)
        row = summary.loc[summary["horizon"].eq("3y")].iloc[0]
        self.assertEqual(row["n_with_yahoo"], 2)
        self.assertGreaterEqual(row["share_yahoo_closer_alpha"], 0.5)


class FetchTests(unittest.TestCase):
    @patch("helpers.timeseries_functions.yahoo_fund_risk_stats.YfData")
    def test_fetch_wraps_parse(self, mock_yf_cls: MagicMock):
        instance = MagicMock()
        instance.get_raw_json.return_value = SAMPLE_PAYLOAD
        mock_yf_cls.return_value = instance
        record = fetch_yahoo_risk_stats("JACNX", yf_data=instance)
        self.assertAlmostEqual(record["horizons"]["3y"]["alpha"], -6.19)


if __name__ == "__main__":
    unittest.main()
