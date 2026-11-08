from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.load_lipper_timeseries import find_sp_cache
from helpers.timeseries_functions.load_workbook import find_workbook

INDEX_COLUMN = "S&P 500 TR"
INDEX_SOURCE_COLUMN = "Index source"
TBILL_3M_COLUMN = "US T-Bill 3M"
_CACHE_SOURCE = "Lipper cache"
_YAHOO_SOURCE = "Yahoo ^SP500TR (shifted window)"
_WORKBOOK_RELATIVE = Path("input-data-alix/clean")
_WORKBOOK_FILENAME = "CLEAN_RECOLTE DONNEES-EXCEL.xlsx"
_META_LABELS = {"name", "category", "fee (%/year)", "Note", "Date"}
_INDEX_DATE_COLUMN = "Index Date"


def _lipper_tbill_3m_by_period() -> pd.Series:
    """3M T-Bill series from the Timeseries sheet, keyed by Lipper month label."""
    workbook = find_workbook(_WORKBOOK_RELATIVE, _WORKBOOK_FILENAME)
    timeseries = pd.read_excel(
        workbook,
        sheet_name="Timeseries",
        engine="openpyxl",
    )
    if TBILL_3M_COLUMN not in timeseries.columns:
        raise KeyError(
            f"Column {TBILL_3M_COLUMN!r} not found on the Timeseries sheet"
        )
    tbill = (
        timeseries.loc[~timeseries["id"].isin(_META_LABELS), ["id", TBILL_3M_COLUMN]]
        .assign(month_start=lambda frame: pd.to_datetime(frame["id"]))
        .assign(Period=lambda frame: frame["month_start"].dt.strftime("%b %Y"))
    )
    return pd.to_numeric(tbill.set_index("Period")[TBILL_3M_COLUMN], errors="coerce")


def _window_uses_cache(row: pd.Series, previous: pd.Series) -> bool:
    return (
        pd.Timestamp(row["Date"]) == pd.Timestamp(row[_INDEX_DATE_COLUMN])
        and pd.Timestamp(previous["Date"]) == pd.Timestamp(previous[_INDEX_DATE_COLUMN])
    )


def load_index_timeseries(
    fund_timeseries: pd.DataFrame,
    cache_relative: Path,
    *,
    sp500_close: pd.Series | None = None,
) -> pd.DataFrame:
    """Append S&P 500 TR and Lipper US T-Bill 3M on the resolved observation dates."""
    sp_levels = pd.read_json(find_sp_cache(cache_relative))
    sp_levels["Date"] = pd.to_datetime(sp_levels["Date"])
    sp_levels = sp_levels.sort_values("Date")
    level = sp_levels.set_index("Date")["S&P 500 TR (Lipper)"]
    sp_return = level / level.shift(1) - 1

    fund_timeseries = fund_timeseries.copy()
    if _INDEX_DATE_COLUMN not in fund_timeseries.columns:
        fund_timeseries[INDEX_COLUMN] = fund_timeseries["Date"].map(sp_return)
        fund_timeseries[INDEX_SOURCE_COLUMN] = _CACHE_SOURCE
        fund_timeseries[TBILL_3M_COLUMN] = fund_timeseries["Period"].map(
            _lipper_tbill_3m_by_period()
        )
        unmatched = fund_timeseries.loc[
            ~fund_timeseries["Date"].isin(level.index), "Date"
        ]
        if not unmatched.empty:
            raise ValueError(
                "No S&P 500 TR level on: "
                + ", ".join(unmatched.dt.strftime("%Y-%m-%d"))
            )
        front = ["Period", "Date", "Time", INDEX_COLUMN, INDEX_SOURCE_COLUMN, TBILL_3M_COLUMN]
        fund_columns = [
            column for column in fund_timeseries.columns if column not in front
        ]
        return fund_timeseries[front + fund_columns]

    index_returns: list[float | None] = [None]
    sources: list[str | None] = [None]

    for i in range(1, len(fund_timeseries)):
        row = fund_timeseries.iloc[i]
        previous = fund_timeseries.iloc[i - 1]
        if _window_uses_cache(row, previous):
            end = pd.Timestamp(row["Date"])
            index_returns.append(float(sp_return.loc[end]))
            sources.append(_CACHE_SOURCE)
        else:
            if sp500_close is None:
                raise ValueError(
                    "sp500_close is required when observation windows differ from index dates"
                )
            start = pd.Timestamp(previous["Date"])
            end = pd.Timestamp(row["Date"])
            if start not in sp500_close.index or end not in sp500_close.index:
                index_returns.append(float("nan"))
            else:
                index_returns.append(
                    float(sp500_close.loc[end] / sp500_close.loc[start] - 1)
                )
            sources.append(_YAHOO_SOURCE)

    fund_timeseries[INDEX_COLUMN] = index_returns
    fund_timeseries[INDEX_SOURCE_COLUMN] = sources
    fund_timeseries[TBILL_3M_COLUMN] = fund_timeseries["Period"].map(
        _lipper_tbill_3m_by_period()
    )

    cache_rows = fund_timeseries.loc[
        fund_timeseries[INDEX_SOURCE_COLUMN].eq(_CACHE_SOURCE), "Date"
    ]
    unmatched = cache_rows.loc[~cache_rows.isin(level.index)]
    if not unmatched.empty:
        raise ValueError(
            "No S&P 500 TR level on: "
            + ", ".join(unmatched.dt.strftime("%Y-%m-%d"))
        )

    front = [
        "Period",
        "Date",
        "Time",
        INDEX_COLUMN,
        INDEX_SOURCE_COLUMN,
        TBILL_3M_COLUMN,
    ]
    if _INDEX_DATE_COLUMN in fund_timeseries.columns:
        front.insert(3, _INDEX_DATE_COLUMN)
        front.insert(4, "Date shift (sessions)")
    fund_columns = [column for column in fund_timeseries.columns if column not in front]
    fund_timeseries = fund_timeseries[front + fund_columns]

    print(
        f"Added {INDEX_COLUMN} return and {TBILL_3M_COLUMN} "
        f"on {len(fund_timeseries)} dates"
    )

    return fund_timeseries
