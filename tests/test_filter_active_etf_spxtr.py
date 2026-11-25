import unittest

import pandas as pd

from helpers.funds_functions.filter_active_etf_spxtr import (
    REASON_DROP_ASSET,
    REASON_DROP_NO_MANDATE,
    REASON_DROP_PRODUCT,
    REASON_KEEP_OBJECTIVE,
    REASON_KEEP_SPXTR,
    REASON_OUT_OF_SCOPE,
    evaluate_active_etf_row,
    filter_active_etf_spxtr,
)


def _row(**kwargs) -> pd.Series:
    base = {
        "Name": "Example Fund",
        "ISIN": "US0000000001",
        "fund_type": "Active",
        "fund_wrapper": "ETF",
        "Fund Type": "Equity",
        "Benchmark Ticker": ".SPXTR",
    }
    base.update(kwargs)
    return pd.Series(base)


class FilterActiveEtfSpxtrTests(unittest.TestCase):
    def test_passive_etf_is_out_of_scope(self):
        decision = evaluate_active_etf_row(
            _row(fund_type="Passive", Name="Vanguard S&P 500 ETF")
        )
        self.assertTrue(decision["keep"])
        self.assertEqual(decision["reason"], REASON_OUT_OF_SCOPE)

    def test_active_mutual_fund_is_out_of_scope(self):
        decision = evaluate_active_etf_row(
            _row(fund_wrapper="mutual fund", Name="Active Large Cap")
        )
        self.assertTrue(decision["keep"])
        self.assertEqual(decision["reason"], REASON_OUT_OF_SCOPE)

    def test_nite_kept_on_spxtr(self):
        decision = evaluate_active_etf_row(
            _row(Name="The Nightview Fund", ISIN="US14064D4850")
        )
        self.assertTrue(decision["keep"])
        self.assertEqual(decision["reason"], REASON_KEEP_SPXTR)

    def test_buffer_dropped_when_not_equity(self):
        decision = evaluate_active_etf_row(
            _row(
                Name="Innovator U.S. Equity Power Buffer ETF - January",
                **{"Fund Type": "Alternatives"},
            )
        )
        self.assertFalse(decision["keep"])
        self.assertEqual(decision["reason"], REASON_DROP_ASSET)

    def test_inx_buffer_dropped(self):
        decision = evaluate_active_etf_row(
            _row(
                Name="AllianzIM U.S. Large Cap Buffer10 Apr ETF",
                **{"Fund Type": "Alternatives", "Benchmark Ticker": ".INX"},
            )
        )
        self.assertFalse(decision["keep"])
        self.assertEqual(decision["reason"], REASON_DROP_ASSET)

    def test_blank_bench_kept_with_outperform_objective(self):
        decision = evaluate_active_etf_row(
            _row(
                Name="Trenchless Fund ETF",
                ISIN="US00777X5462",
                **{"Benchmark Ticker": None},
            ),
            objectives={
                "US00777X5462": (
                    "The Fund seeks capital appreciation by investing in "
                    "securities that have an above-average probability of "
                    "outperforming the S&P 500 Index over all time horizons."
                )
            },
        )
        self.assertTrue(decision["keep"])
        self.assertEqual(decision["reason"], REASON_KEEP_OBJECTIVE)

    def test_blank_bench_without_mandate_dropped(self):
        decision = evaluate_active_etf_row(
            _row(
                Name="The Rebuild America ETF",
                ISIN="US00777X3970",
                **{"Benchmark Ticker": None},
            ),
            objectives={
                "US00777X3970": (
                    "Invests in infrastructure securities and aims to provide "
                    "better risk-adjusted returns compared to investing solely "
                    "in the securities of companies that comprise U.S. "
                    "large-capitalization indices, such as the S&P 500 Index."
                )
            },
        )
        self.assertFalse(decision["keep"])
        self.assertEqual(decision["reason"], REASON_DROP_NO_MANDATE)

    def test_wrong_lipper_bench_dropped(self):
        decision = evaluate_active_etf_row(
            _row(
                Name="Some Active Equity ETF",
                **{"Benchmark Ticker": ".SPVQDTR"},
            )
        )
        self.assertFalse(decision["keep"])
        self.assertIn(".SPVQDTR", str(decision["reason"]))

    def test_cape_strategy_dropped_despite_spxtr(self):
        decision = evaluate_active_etf_row(
            _row(Name="DoubleLine Shiller CAPE U.S. Equities ETF"),
            objectives={
                "US0000000001": (
                    "Seeks total return which exceeds the total return of the "
                    "S&P 500 Index by exposure to the Shiller Barclays CAPE US "
                    "Sector TR Index."
                )
            },
        )
        self.assertFalse(decision["keep"])
        self.assertEqual(decision["reason"], REASON_DROP_PRODUCT)

    def test_options_income_name_dropped_on_equity(self):
        decision = evaluate_active_etf_row(
            _row(Name="Defiance S&P 500 Enhanced Options Income ETF")
        )
        self.assertFalse(decision["keep"])
        self.assertEqual(decision["reason"], REASON_DROP_PRODUCT)

    def test_filter_frame_keeps_passive_and_drops_buffers(self):
        frame = pd.DataFrame(
            [
                {
                    "Name": "Passive SPY",
                    "ISIN": "US1",
                    "fund_type": "Passive",
                    "fund_wrapper": "ETF",
                    "Fund Type": "Equity",
                    "Benchmark Ticker": ".SPXTR",
                },
                {
                    "Name": "Allianz Buffer ETF",
                    "ISIN": "US2",
                    "fund_type": "Active",
                    "fund_wrapper": "ETF",
                    "Fund Type": "Alternatives",
                    "Benchmark Ticker": ".INX",
                },
                {
                    "Name": "Gotham Enhanced 500 ETF",
                    "ISIN": "US8863648353",
                    "fund_type": "Active",
                    "fund_wrapper": "ETF",
                    "Fund Type": "Equity",
                    "Benchmark Ticker": ".SPXTR",
                },
            ]
        )
        kept, dropped, review = filter_active_etf_spxtr(frame, objectives={})
        self.assertEqual(set(kept["ISIN"]), {"US1", "US8863648353"})
        self.assertEqual(dropped["ISIN"].tolist(), ["US2"])
        self.assertEqual(len(review), 3)
