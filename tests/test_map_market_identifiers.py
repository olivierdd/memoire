import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from helpers.funds_functions.map_market_identifiers import (
    apply_cusip_market_identifiers,
    apply_market_identifiers,
    cusip_ticker_from_job,
    load_isin_cache,
    map_cusip_market_identifiers,
    map_market_identifiers,
    refresh_cusip_cache,
    refresh_isin_cache,
    resolve_cache_path,
    ticker_from_job,
)


class TickerFromJobTests(unittest.TestCase):
    def test_returns_first_ticker(self):
        job = {"data": [{"ticker": "ABC"}, {"ticker": "XYZ"}]}
        self.assertEqual(ticker_from_job(job), "ABC")

    def test_empty_data_returns_none(self):
        self.assertIsNone(ticker_from_job({}))
        self.assertIsNone(ticker_from_job({"data": []}))


class ApplyMarketIdentifiersTests(unittest.TestCase):
    def test_maps_isin_to_market_columns(self):
        funds = pd.DataFrame({"ISIN": ["US1111111111", "US2222222222", pd.NA]})
        cache = {"US1111111111": "AAA", "US2222222222": None, "_nulls_are_final": True}

        enriched = apply_market_identifiers(funds, cache)

        self.assertEqual(enriched["market_identifier"].tolist(), ["AAA", None, None])
        self.assertEqual(enriched["market_ticker"].tolist(), ["AAA", None, None])


class ResolveCachePathTests(unittest.TestCase):
    def test_prefers_project_cache_over_notebooks_copy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "helpers").mkdir()
            main_cache = root / "cache" / "cache-isin-openfigi.json"
            main_cache.parent.mkdir(parents=True)
            main_cache.write_text('{"US1111111111": "MAIN"}\n')
            notebooks = root / "notebooks" / "cache"
            notebooks.mkdir(parents=True)
            (notebooks / "cache-isin-openfigi.json").write_text("{}\n")

            with patch(
                "helpers.funds_functions.map_market_identifiers.Path.cwd",
                return_value=root / "notebooks",
            ):
                found = resolve_cache_path(
                    Path("cache") / "cache-isin-openfigi.json"
                )

        self.assertEqual(found, main_cache.resolve())


class MapMarketIdentifiersTests(unittest.TestCase):
    def test_uses_cache_without_calling_openfigi(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_file = root / "cache" / "cache-isin-openfigi.json"
            cache_file.parent.mkdir(parents=True)
            cache_file.write_text(
                json.dumps(
                    {"US1111111111": "ZZZ", "_nulls_are_final": True},
                    indent=2,
                )
                + "\n"
            )
            helpers = root / "helpers"
            helpers.mkdir()
            funds = pd.DataFrame({"ISIN": ["US1111111111"]})

            with patch(
                "helpers.funds_functions.map_market_identifiers._code_root",
                return_value=root,
            ):
                with patch(
                    "helpers.funds_functions.map_market_identifiers.post_mapping"
                ) as post:
                    enriched = map_market_identifiers(funds, cache_path=cache_file)

            post.assert_not_called()
            self.assertEqual(enriched["market_identifier"].iloc[0], "ZZZ")

    def test_refresh_fetches_pending_isins(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache.json"
            funds = pd.DataFrame({"ISIN": ["US3333333333"]})
            isins = ["US3333333333"]

            with patch(
                "helpers.funds_functions.map_market_identifiers.post_mapping",
                return_value=[{"data": [{"ticker": "NEW"}]}],
            ) as post:
                cache = refresh_isin_cache(isins, cache_path=cache_file, pause_seconds=0)

            post.assert_called_once_with(["US3333333333"])
            self.assertEqual(cache["US3333333333"], "NEW")
            self.assertTrue(cache["_nulls_are_final"])
            self.assertEqual(load_isin_cache(cache_file)["US3333333333"], "NEW")


def _as_cells(series: pd.Series) -> list:
    return [None if pd.isna(value) else value for value in series.tolist()]


class CusipTickerFromJobTests(unittest.TestCase):
    def test_prefers_us_listing(self):
        job = {
            "data": [
                {"ticker": "ABC", "exchCode": "LN"},
                {"ticker": "ABCUS", "exchCode": "US"},
            ]
        }
        self.assertEqual(cusip_ticker_from_job(job), "ABCUS")

    def test_unknown_identifier_returns_none(self):
        self.assertIsNone(cusip_ticker_from_job({"warning": "No identifier found."}))


class MapCusipMarketIdentifiersTests(unittest.TestCase):
    def test_inserts_openfigi_market_id_after_cusip(self):
        funds = pd.DataFrame(
            {
                "Name": ["Known", "Unknown", "Blank"],
                "CUSIP": ["349903179", "000000000", None],
                "ISIN": ["US3499031793", "US0000000000", "US1111111111"],
            }
        )
        cache = {
            "349903179": {"ticker": "AUXFX", "name": "AUXIER FOCUS FUND-INV"},
            "000000000": None,
            "_nulls_are_final": True,
        }

        enriched = apply_cusip_market_identifiers(funds, cache)

        self.assertEqual(
            list(enriched.columns[:5]),
            ["Name", "CUSIP", "openfigi_market_id", "openfigi_name", "openfigi_cusip_ok"],
        )
        self.assertEqual(_as_cells(enriched["openfigi_market_id"]), ["AUXFX", None, None])
        self.assertEqual(
            _as_cells(enriched["openfigi_name"]), ["AUXIER FOCUS FUND-INV", None, None]
        )
        self.assertEqual(enriched["openfigi_cusip_ok"].tolist(), [True, False, False])

    def test_replaces_a_different_stored_openfigi_value(self):
        funds = pd.DataFrame(
            {
                "Name": ["Auxier Focus Fund;Investor"],
                "CUSIP": ["349903179"],
                "openfigi_market_id": ["OTHER"],
                "openfigi_name": ["OTHER FUND"],
            }
        )
        cache = {"349903179": {"ticker": "AUXFX", "name": "AUXIER FOCUS FUND-INV"}}

        output = io.StringIO()
        with redirect_stdout(output):
            enriched = apply_cusip_market_identifiers(funds, cache)

        self.assertEqual(enriched["openfigi_market_id"].tolist(), ["AUXFX"])
        self.assertEqual(enriched["openfigi_name"].tolist(), ["AUXIER FOCUS FUND-INV"])
        alert = output.getvalue()
        self.assertIn("CUSIP openfigi_market_id", alert)
        self.assertIn("OTHER -> AUXFX", alert)
        self.assertIn("CUSIP openfigi_name", alert)
        self.assertIn("OTHER FUND -> AUXIER FOCUS FUND-INV", alert)

    def test_keeps_a_stored_value_when_the_lookup_returns_nothing(self):
        funds = pd.DataFrame(
            {
                "Name": ["Known"],
                "CUSIP": ["000000000"],
                "openfigi_market_id": ["AUXFX"],
                "openfigi_name": ["AUXIER FOCUS FUND-INV"],
            }
        )

        output = io.StringIO()
        with redirect_stdout(output):
            enriched = apply_cusip_market_identifiers(funds, {"000000000": None})

        self.assertEqual(enriched["openfigi_market_id"].tolist(), ["AUXFX"])
        self.assertEqual(enriched["openfigi_name"].tolist(), ["AUXIER FOCUS FUND-INV"])
        self.assertEqual(enriched["openfigi_cusip_ok"].tolist(), [False])
        self.assertEqual(output.getvalue(), "")

    def test_refresh_requests_id_cusip_and_skips_cached(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-cusip-openfigi.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "349903179": {"ticker": "AUXFX", "name": "AUXIER FOCUS FUND-INV"},
                        "_nulls_are_final": True,
                    }
                )
                + "\n"
            )
            funds = pd.DataFrame({"CUSIP": ["349903179", "74253Q788", "not-a-cusip", None]})

            with patch(
                "helpers.funds_functions.map_market_identifiers.post_mapping",
                return_value=[
                    {
                        "data": [
                            {
                                "ticker": "PLFIX",
                                "name": "PRINCIPAL L/C S&P 500-IS",
                                "exchCode": "US",
                            }
                        ]
                    }
                ],
            ) as post:
                enriched = map_cusip_market_identifiers(
                    funds, cache_path=cache_file, pause_seconds=0
                )

            post.assert_called_once_with(["74253Q788"], "ID_CUSIP")
            self.assertEqual(
                _as_cells(enriched["openfigi_market_id"]), ["AUXFX", "PLFIX", None, None]
            )
            self.assertEqual(
                _as_cells(enriched["openfigi_name"]),
                ["AUXIER FOCUS FUND-INV", "PRINCIPAL L/C S&P 500-IS", None, None],
            )
            self.assertEqual(enriched["openfigi_cusip_ok"].tolist(), [True, True, False, False])
            stored = load_isin_cache(cache_file)
            self.assertEqual(
                stored["74253Q788"],
                {"ticker": "PLFIX", "name": "PRINCIPAL L/C S&P 500-IS"},
            )
            self.assertTrue(stored["_nulls_are_final"])

    def test_refreshes_ticker_only_cache_entries_to_collect_the_name(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache-cusip-openfigi.json"
            cache_file.write_text(json.dumps({"349903179": "AUXFX"}) + "\n")

            with patch(
                "helpers.funds_functions.map_market_identifiers.post_mapping",
                return_value=[
                    {
                        "data": [
                            {
                                "ticker": "AUXFX",
                                "name": "AUXIER FOCUS FUND-INV",
                                "exchCode": "US",
                            }
                        ]
                    }
                ],
            ) as post:
                cache = refresh_cusip_cache(
                    ["349903179"], cache_path=cache_file, pause_seconds=0
                )

            post.assert_called_once_with(["349903179"], "ID_CUSIP")
            self.assertEqual(
                cache["349903179"],
                {"ticker": "AUXFX", "name": "AUXIER FOCUS FUND-INV"},
            )

    def test_unknown_cusip_is_cached_as_a_miss(self):
        with TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "cache.json"
            with patch(
                "helpers.funds_functions.map_market_identifiers.post_mapping",
                return_value=[{"warning": "No identifier found."}],
            ):
                cache = refresh_cusip_cache(
                    ["000000000"], cache_path=cache_file, pause_seconds=0
                )

            self.assertIsNone(cache["000000000"])
            self.assertTrue(cache["_nulls_are_final"])


if __name__ == "__main__":
    unittest.main()
