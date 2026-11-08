import os

import financedatabase as fd
import pandas as pd
from dotenv import find_dotenv, load_dotenv
from financedatabase.frame_model import FinanceFrame


def _fetch_fd_nav(
    fund_frame: FinanceFrame,
    api_key: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    source: str,
) -> pd.Series:
    toolkit = fund_frame.to_toolkit(
        api_key=api_key,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        benchmark_ticker=None,
        enforce_source=source,
        progress_bar=False,
        rounding=None,
    )
    prices = toolkit.get_historical_data(
        enforce_source=source,
        show_columns=["Adj Close"],
        include_dividends=False,
        fill_nan=False,
    )
    if prices is None or (hasattr(prices, "empty") and prices.empty):
        return pd.Series(dtype=float)
    if isinstance(prices, pd.DataFrame):
        if isinstance(prices.columns, pd.MultiIndex):
            prices = prices["Adj Close"]
            if isinstance(prices, pd.DataFrame):
                prices = prices.iloc[:, 0]
        elif "Adj Close" in prices.columns:
            prices = prices["Adj Close"]
        else:
            prices = prices.squeeze()
    index = (
        prices.index.to_timestamp()
        if hasattr(prices.index, "to_timestamp")
        else pd.to_datetime(prices.index)
    )
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    return pd.Series(prices.to_numpy(), index=index, name="Adj Close")


def load_financedatabase_timeseries(
    fund_timeseries: pd.DataFrame,
    selected: pd.Series,
    selected_fund: str,
) -> pd.DataFrame:
    """Append monthly total returns from FinanceDatabase on the Lipper observation dates."""
    # FinanceDatabase catalogues the fund; prices come via FinanceToolkit.
    # Prefer FMP, then YahooFinance. Adj Close is the dividend-adjusted NAV,
    # so the monthly change is a total return on the same observation dates.
    load_dotenv(find_dotenv(usecwd=True))
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise RuntimeError("FMP_API_KEY is missing from .env")

    ticker = selected["market_identifier"]
    if pd.isna(ticker):
        raise KeyError(
            f"{selected_fund} has no market identifier in the OpenFIGI cache"
        )

    catalogue = fd.Funds().select()
    catalogue.index = catalogue.index.astype(str)
    if str(ticker) not in catalogue.index:
        raise KeyError(f"{ticker} is not in the FinanceDatabase funds catalogue")
    fund_frame = FinanceFrame(catalogue.loc[[str(ticker)]])

    fd_column = f"{selected_fund} (FinanceDatabase)"
    start = fund_timeseries["Date"].min() - pd.Timedelta(days=10)
    end = fund_timeseries["Date"].max() + pd.Timedelta(days=5)

    fd_source = "FinancialModelingPrep"
    fd_nav = _fetch_fd_nav(fund_frame, api_key, start, end, fd_source)
    if fd_nav.dropna().empty:
        fd_source = "YahooFinance"
        fd_nav = _fetch_fd_nav(fund_frame, api_key, start, end, fd_source)
        print(
            f"FMP returned no history for {ticker}; "
            f"using {fd_source} via FinanceToolkit instead."
        )
    else:
        print(f"FinanceDatabase prices loaded from {fd_source}.")

    nav = fund_timeseries["Date"].map(fd_nav)
    fund_timeseries = fund_timeseries.copy()
    fund_timeseries[fd_column] = nav / nav.shift(1) - 1
    priced = int(nav.notna().sum())
    print(
        f"Loaded FinanceDatabase total return for {ticker} "
        f"({priced} of {len(nav)} observation dates)"
    )

    return fund_timeseries
