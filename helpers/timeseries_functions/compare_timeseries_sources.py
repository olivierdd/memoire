import pandas as pd
import yfinance as yf

from helpers.timeseries_functions.yahoo_daily_levels import yahoo_daily_levels

DEFAULT_MASTER_TIMESERIES = "Lipper"
DEFAULT_COMPARISON_TIMESERIES = "Yahoo"
DEFAULT_MATCH_TOLERANCE = 1e-4


def source_columns_for(selected_fund: str) -> dict[str, str]:
    return {
        "Lipper": f"{selected_fund} (Lipper)",
        "Yahoo": f"{selected_fund} (Yahoo)",
        "FinanceDatabase": f"{selected_fund} (FinanceDatabase)",
    }


def _print_mismatch_report(
    *,
    report: pd.DataFrame,
    fund_timeseries: pd.DataFrame,
    selected: pd.Series,
    selected_fund: str,
    master_timeseries: str,
    comparison_timeseries: str,
    master_column: str,
    comparison_column: str,
    lipper_column: str,
    yahoo_level: pd.Series | None = None,
    close: pd.Series | None = None,
    distribution: pd.Series | None = None,
) -> None:
    if yahoo_level is None or close is None or distribution is None:
        close, distribution, yahoo_level = yahoo_daily_levels(
            fund_timeseries,
            selected,
            selected_fund,
        )

    sp_daily = yf.Ticker("^SP500TR").history(
        start=close.index.min(),
        end=close.index.max() + pd.Timedelta(days=1),
        interval="1d",
        auto_adjust=False,
        repair=False,
    )
    sp_daily.index = sp_daily.index.tz_localize(None)
    sp_close = sp_daily["Close"].astype(float).reindex(close.index)
    observation_dates = pd.DatetimeIndex(fund_timeseries["Date"])

    def carried_forward(date):
        """S&P return missing from a repeated NAV, or None."""
        date = pd.Timestamp(date)
        if date not in close.index:
            return None
        loc = close.index.get_loc(date)
        if not isinstance(loc, int) or loc == 0:
            return None
        previous = close.index[loc - 1]
        same_close = abs(float(close.loc[date]) - float(close.loc[previous])) <= 1e-4
        if not same_close or float(distribution.loc[date]) != 0:
            return None
        market = sp_close.loc[date] / sp_close.loc[previous] - 1
        if pd.isna(market):
            return None
        missed_dollars = abs(float(market) * float(close.loc[previous]))
        if missed_dollars < 0.01:
            return None
        return float(market)

    def stale_comment(end):
        end = pd.Timestamp(end)
        position = observation_dates.get_loc(end)
        if not isinstance(position, int) or position == 0:
            return "not a stale NAV"
        start = observation_dates[position - 1]
        if start not in yahoo_level.index or end not in yahoo_level.index:
            return "not a stale NAV"
        yahoo_return = float(yahoo_level.loc[end] / yahoo_level.loc[start] - 1)
        lipper_return = fund_timeseries.loc[
            fund_timeseries["Date"].eq(end), lipper_column
        ].iloc[0]
        if pd.isna(lipper_return):
            return "not a stale NAV"
        lipper_return = float(lipper_return)
        original = abs(lipper_return - yahoo_return)

        def reconciled(market_move, stale_on_end):
            if stale_on_end:
                corrected = (1 + yahoo_return) * (1 + market_move) - 1
            else:
                corrected = (1 + yahoo_return) / (1 + market_move) - 1
            remaining = abs(corrected - lipper_return)
            return remaining <= 1e-3 and remaining < original / 2

        notes = []
        for boundary, market_move, stale_on_end in (
            (end, carried_forward(end), True),
            (start, carried_forward(start), False),
        ):
            if market_move is None:
                continue
            if reconciled(market_move, stale_on_end):
                notes.append(f"stale NAV on {boundary:%Y-%m-%d}")
            else:
                notes.append(
                    f"stale NAV on {boundary:%Y-%m-%d} does not explain the gap"
                )
        if not notes:
            return "not a stale NAV"
        return ", ".join(notes)

    print("Mismatch dates:")
    for _, row in report.iterrows():
        master_value = row[master_column]
        comparison_value = row[comparison_column]
        master_text = "missing" if pd.isna(master_value) else f"{master_value:.6f}"
        comparison_text = (
            "missing" if pd.isna(comparison_value) else f"{comparison_value:.6f}"
        )
        if pd.isna(master_value) or pd.isna(comparison_value):
            difference = "missing"
        else:
            difference = f"{(master_value - comparison_value) * 1e4:+.1f} bp"
        stale = stale_comment(row["Date"])
        print(
            f"    {row['Date']:%Y-%m-%d}  "
            f"{master_timeseries} {master_text}  "
            f"{comparison_timeseries} {comparison_text}  "
            f"{difference}  {stale}"
        )


def compare_timeseries_sources(
    fund_timeseries: pd.DataFrame,
    selected_fund: str,
    selected: pd.Series,
    *,
    master_timeseries: str = DEFAULT_MASTER_TIMESERIES,
    comparison_timeseries: str = DEFAULT_COMPARISON_TIMESERIES,
    match_tolerance: float = DEFAULT_MATCH_TOLERANCE,
    yahoo_level: pd.Series | None = None,
    close: pd.Series | None = None,
    distribution: pd.Series | None = None,
) -> tuple[pd.DataFrame, str, str, pd.Series, pd.Series]:
    """Compare two return sources and print match statistics."""
    source_columns = source_columns_for(selected_fund)
    unknown = {master_timeseries, comparison_timeseries} - source_columns.keys()
    if unknown:
        raise KeyError(f"Unknown timeseries: {', '.join(sorted(unknown))}")

    master_column = source_columns[master_timeseries]
    comparison_column = source_columns[comparison_timeseries]
    compared = fund_timeseries[
        ["Period", "Date", master_column, comparison_column]
    ].copy()
    master = compared[master_column]
    other = compared[comparison_column]
    gap = (master - other).abs()

    both_missing = master.isna() & other.isna()
    one_missing = master.isna() ^ other.isna()
    perfect = both_missing | gap.eq(0)
    acceptable = ~perfect & ~one_missing & gap.le(match_tolerance)
    mismatch = ~(perfect | acceptable)

    print(f"Master: {master_timeseries}")
    print(f"Comparison: {comparison_timeseries}")
    print(f"Perfect matches (zero tolerance): {int(perfect.sum())} of {len(compared)}")
    print(
        f"Acceptable matches (within {match_tolerance:.4f}): "
        f"{int(acceptable.sum())} of {len(compared)}"
    )
    print(f"Mismatches: {int(mismatch.sum())} of {len(compared)}")

    if mismatch.any():
        report = compared.loc[
            mismatch, ["Period", "Date", master_column, comparison_column]
        ].copy()
        lipper_yahoo = {"Lipper", "Yahoo"}
        if lipper_yahoo <= {master_timeseries, comparison_timeseries}:
            _print_mismatch_report(
                report=report,
                fund_timeseries=fund_timeseries,
                selected=selected,
                selected_fund=selected_fund,
                master_timeseries=master_timeseries,
                comparison_timeseries=comparison_timeseries,
                master_column=master_column,
                comparison_column=comparison_column,
                lipper_column=source_columns["Lipper"],
                yahoo_level=yahoo_level,
                close=close,
                distribution=distribution,
            )
        else:
            print("Mismatch dates:")
            for _, row in report.iterrows():
                master_value = row[master_column]
                comparison_value = row[comparison_column]
                master_text = (
                    "missing" if pd.isna(master_value) else f"{master_value:.6f}"
                )
                comparison_text = (
                    "missing"
                    if pd.isna(comparison_value)
                    else f"{comparison_value:.6f}"
                )
                if pd.isna(master_value) or pd.isna(comparison_value):
                    difference = "missing"
                else:
                    difference = f"{(master_value - comparison_value) * 1e4:+.1f} bp"
                print(
                    f"    {row['Date']:%Y-%m-%d}  "
                    f"{master_timeseries} {master_text}  "
                    f"{comparison_timeseries} {comparison_text}  "
                    f"{difference}"
                )

    return compared, master_column, comparison_column, gap, mismatch
