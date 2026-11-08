"""Yahoo daily total-return levels (fund ticker and S&P 500 TR)."""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def yahoo_daily_levels(
    fund_timeseries: pd.DataFrame,
    selected: pd.Series,
    selected_fund: str,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Close, distributions, and reinvested total-return level for the fund ticker."""
    ticker = selected["market_identifier"]
    if pd.isna(ticker):
        raise KeyError(
            f"{selected_fund} has no market identifier in the OpenFIGI cache"
        )

    start = fund_timeseries["Date"].min() - pd.Timedelta(days=10)
    end = fund_timeseries["Date"].max() + pd.Timedelta(days=5)
    daily = yf.Ticker(str(ticker)).history(
        start=start,
        end=end,
        interval="1d",
        auto_adjust=False,
        repair=False,
    )
    daily.index = daily.index.tz_localize(None)
    distribution = daily["Dividends"].fillna(0)
    if "Capital Gains" in daily.columns:
        distribution = distribution + daily["Capital Gains"].fillna(0)
    close = daily["Close"].astype(float)
    daily_return = (close + distribution) / close.shift(1)
    daily_return.iloc[0] = 1.0
    yahoo_level = close.iloc[0] * daily_return.cumprod()
    return close, distribution, yahoo_level


def fetch_sp500_tr_close(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    """Daily ^SP500TR close between start and end (end exclusive per yfinance)."""
    sp_daily = yf.Ticker("^SP500TR").history(
        start=start,
        end=end + pd.Timedelta(days=1),
        interval="1d",
        auto_adjust=False,
        repair=False,
    )
    sp_daily.index = sp_daily.index.tz_localize(None)
    return sp_daily["Close"].astype(float)
