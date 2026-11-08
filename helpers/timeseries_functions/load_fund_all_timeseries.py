from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from helpers.timeseries_functions.load_financedatabase_timeseries import (
    load_financedatabase_timeseries,
)
from helpers.timeseries_functions.load_index_timeseries import (
    INDEX_COLUMN,
    load_index_timeseries,
)
from helpers.timeseries_functions.load_lipper_timeseries import load_lipper_timeseries
from helpers.timeseries_functions.load_yahoo_timeseries import load_yahoo_timeseries
from helpers.timeseries_functions.resolve_fund_observation_dates import (
    resolve_fund_observation_dates,
    shifted_months_summary,
)
from helpers.timeseries_functions.yahoo_daily_levels import (
    fetch_sp500_tr_close,
    yahoo_daily_levels,
)

__all__ = ["INDEX_COLUMN", "FundTimeseriesContext", "load_fund_all_timeseries"]


@dataclass(frozen=True)
class FundTimeseriesContext:
    """Daily Yahoo prices fetched once per fund load."""

    close: pd.Series
    distribution: pd.Series
    yahoo_level: pd.Series
    sp500_close: pd.Series
    shifted_months: dict[str, Any]


def load_fund_all_timeseries(
    timeseries_df: pd.DataFrame,
    funds: pd.DataFrame,
    selected_fund: str,
    sp_cache_relative: Path,
    *,
    match_tolerance: float = 1e-4,
    max_shift_sessions: int = 6,
) -> tuple[pd.DataFrame, pd.Series, FundTimeseriesContext]:
    """Load Lipper, Yahoo, FinanceDatabase, and S&P 500 TR on shared observation dates."""
    fund_timeseries, selected = load_lipper_timeseries(
        timeseries_df,
        funds,
        selected_fund,
        sp_cache_relative,
    )
    lipper_column = f"{selected_fund} (Lipper)"
    close, distribution, yahoo_level = yahoo_daily_levels(
        fund_timeseries,
        selected,
        selected_fund,
    )
    fund_timeseries = resolve_fund_observation_dates(
        fund_timeseries,
        lipper_column,
        yahoo_level,
        match_tolerance=match_tolerance,
        max_shift_sessions=max_shift_sessions,
    )
    shifted_months = shifted_months_summary(fund_timeseries)

    fund_timeseries = load_yahoo_timeseries(
        fund_timeseries,
        selected,
        selected_fund,
        yahoo_level=yahoo_level,
    )
    fund_timeseries = load_financedatabase_timeseries(
        fund_timeseries,
        selected,
        selected_fund,
    )
    sp_start = fund_timeseries["Date"].min() - pd.Timedelta(days=10)
    sp_end = fund_timeseries["Date"].max() + pd.Timedelta(days=5)
    sp500_close = fetch_sp500_tr_close(sp_start, sp_end)
    fund_timeseries = load_index_timeseries(
        fund_timeseries,
        sp_cache_relative,
        sp500_close=sp500_close,
    )
    context = FundTimeseriesContext(
        close=close,
        distribution=distribution,
        yahoo_level=yahoo_level,
        sp500_close=sp500_close,
        shifted_months=shifted_months,
    )
    return fund_timeseries, selected, context
