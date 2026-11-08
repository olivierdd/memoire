import pandas as pd

from helpers.timeseries_functions.yahoo_daily_levels import yahoo_daily_levels


def load_yahoo_timeseries(
    fund_timeseries: pd.DataFrame,
    selected: pd.Series,
    selected_fund: str,
    *,
    yahoo_level: pd.Series | None = None,
) -> pd.DataFrame:
    """Append monthly total returns from Yahoo on the Lipper observation dates."""
    yahoo_column = f"{selected_fund} (Yahoo)"

    if yahoo_level is None:
        _, _, yahoo_level = yahoo_daily_levels(
            fund_timeseries,
            selected,
            selected_fund,
        )

    nav = fund_timeseries["Date"].map(yahoo_level)
    fund_timeseries = fund_timeseries.copy()
    fund_timeseries[yahoo_column] = nav / nav.shift(1) - 1

    priced = int(nav.notna().sum())
    ticker = selected["market_identifier"]
    print(
        f"Loaded Yahoo total return for {ticker} "
        f"({priced} of {len(nav)} observation dates)"
    )

    return fund_timeseries
