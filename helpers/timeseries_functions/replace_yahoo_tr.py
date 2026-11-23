"""Replace Datastream/Lipper TR and Price columns with Yahoo at series load."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from helpers.funds_functions.map_yahoo_timeseries import (
    align_yahoo_levels_to_index,
    fetch_yahoo_price_levels,
    fetch_yahoo_total_return_levels,
    levels_and_returns_with_holiday_na,
    spx_flat_holiday_mask,
)

# Lipper/Datastream level-jump cases where Yahoo is clean under the same
# daily consistency checks. CFIMX (US1888501012) is intentionally omitted —
# Yahoo still shows a level jump there.
YAHOO_TR_REPLACEMENTS: dict[str, str] = {
    "US00774Q8740": "GQEPX",
    "US2562191062": "DODGX",
    "US2571321007": "DSEFX",
    "US3161841008": "FMAGX",
    "US78472P1093": "SVSPX",
    "US8085098551": "SWPPX",
    "US85749T7569": "SSEYX",
}

YAHOO_TR_REPLACE_ISINS: frozenset[str] = frozenset(YAHOO_TR_REPLACEMENTS)


def _column_id(catalog: pd.DataFrame, header: str) -> int | None:
    match = catalog.loc[catalog["header"].eq(header), "column"]
    if match.empty:
        return None
    return int(match.iloc[0])


def _refresh_coverage(catalog: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    """Recompute observations / first_date / last_date for all catalog columns."""
    out = catalog.copy()
    counts: list[int] = []
    first_dates: list[pd.Timestamp] = []
    last_dates: list[pd.Timestamp] = []
    for col in out["column"]:
        column_id = int(col)
        if column_id not in observations.columns:
            counts.append(0)
            first_dates.append(pd.NaT)
            last_dates.append(pd.NaT)
            continue
        series = observations[column_id]
        usable = series.dropna()
        counts.append(int(len(usable)))
        if usable.empty:
            first_dates.append(pd.NaT)
            last_dates.append(pd.NaT)
        else:
            first_dates.append(pd.Timestamp(usable.index[0]))
            last_dates.append(pd.Timestamp(usable.index[-1]))
    out["observations"] = counts
    out["first_date"] = first_dates
    out["last_date"] = last_dates
    return out


def _write_level_pair(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    level_id: int,
    return_id: int,
    aligned: pd.Series,
    category: str,
    level_note: str,
    holiday_mask: pd.Series | None = None,
) -> pd.Series:
    """Write Yahoo levels and session returns (holidays NA when mask provided)."""
    filled, returns = levels_and_returns_with_holiday_na(aligned, holiday_mask)
    observations[level_id] = filled
    observations[return_id] = returns
    level_mask = catalog["column"].eq(level_id)
    return_mask = catalog["column"].eq(return_id)
    catalog.loc[level_mask, "category"] = category
    catalog.loc[return_mask, "category"] = category
    catalog.loc[level_mask, "note"] = level_note
    catalog.loc[return_mask, "note"] = "Daily simple return = P(t)/P(t-1) - 1"
    return filled


def replace_datastream_tr_with_yahoo(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    replacements: dict[str, str] | None = None,
    fetch_tr_levels: Callable[[str], pd.Series | None] = fetch_yahoo_total_return_levels,
    fetch_price_levels: Callable[[str], pd.Series | None] = fetch_yahoo_price_levels,
    # Backward-compatible alias used by older tests/callers.
    fetch_levels: Callable[[str], pd.Series | None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Overwrite main TR/Price columns (and %) with Yahoo for configured ISINs.

    - ``{ISIN} TR`` / ``{ISIN} TR %`` ← adjusted Close (``auto_adjust=True``)
    - ``{ISIN} Price`` / ``{ISIN} Price %`` ← unadjusted Close (``auto_adjust=False``)

    Headers stay the primary Datastream names so later steps still treat them as
    the fund's main series.     Dates without a Yahoo print stay blank. S&P-flat exchange holidays are
    left NA (level and %) and the next session’s return is recomputed; step 2
    also normalises the full panel on the market calendar.

    Returns ``(catalog, observations, replacement_log)``.
    """
    mapping = dict(replacements if replacements is not None else YAHOO_TR_REPLACEMENTS)
    tr_fetch = fetch_levels if fetch_levels is not None else fetch_tr_levels
    updated_catalog = catalog.copy()
    updated_observations = observations.copy()
    rows: list[dict[str, Any]] = []

    spx_id = _column_id(updated_catalog, "S&P 500 TR")
    holiday_mask: pd.Series | None = None
    if spx_id is not None and spx_id in updated_observations.columns:
        holiday_mask = spx_flat_holiday_mask(updated_observations[spx_id])

    for isin, ticker in mapping.items():
        tr_id = _column_id(updated_catalog, f"{isin} TR")
        tr_ret_id = _column_id(updated_catalog, f"{isin} TR %")
        price_id = _column_id(updated_catalog, f"{isin} Price")
        price_ret_id = _column_id(updated_catalog, f"{isin} Price %")
        row: dict[str, Any] = {
            "isin": isin,
            "ticker": ticker,
            "status": "replaced",
            "tr_days_filled": 0,
            "tr_days_blank": 0,
            "price_days_filled": 0,
            "price_days_blank": 0,
            "tr_column": tr_id,
            "tr_return_column": tr_ret_id,
            "price_column": price_id,
            "price_return_column": price_ret_id,
        }

        if tr_id is None or tr_ret_id is None:
            row["status"] = "missing TR columns"
            rows.append(row)
            continue
        if price_id is None or price_ret_id is None:
            row["status"] = "missing Price columns"
            rows.append(row)
            continue

        tr_levels = tr_fetch(ticker)
        price_levels = fetch_price_levels(ticker)
        if tr_levels is None or tr_levels.empty:
            row["status"] = "yahoo TR empty"
            row["tr_days_blank"] = int(len(updated_observations))
            rows.append(row)
            continue
        if price_levels is None or price_levels.empty:
            row["status"] = "yahoo Price empty"
            row["price_days_blank"] = int(len(updated_observations))
            rows.append(row)
            continue

        tr_aligned = align_yahoo_levels_to_index(tr_levels, updated_observations.index)
        price_aligned = align_yahoo_levels_to_index(
            price_levels, updated_observations.index
        )
        tr_filled = _write_level_pair(
            updated_catalog,
            updated_observations,
            level_id=tr_id,
            return_id=tr_ret_id,
            aligned=tr_aligned,
            category="Yahoo TR",
            level_note="Total return index, daily",
            holiday_mask=holiday_mask,
        )
        price_filled = _write_level_pair(
            updated_catalog,
            updated_observations,
            level_id=price_id,
            return_id=price_ret_id,
            aligned=price_aligned,
            category="Yahoo Price",
            level_note="Price, daily",
            holiday_mask=holiday_mask,
        )

        row["tr_days_filled"] = int(tr_filled.notna().sum())
        row["tr_days_blank"] = int(tr_filled.isna().sum())
        row["price_days_filled"] = int(price_filled.notna().sum())
        row["price_days_blank"] = int(price_filled.isna().sum())
        rows.append(row)

    updated_catalog = _refresh_coverage(updated_catalog, updated_observations)
    log = pd.DataFrame(rows)
    if log.empty:
        log = pd.DataFrame(
            columns=[
                "isin",
                "ticker",
                "status",
                "tr_days_filled",
                "tr_days_blank",
                "price_days_filled",
                "price_days_blank",
                "tr_column",
                "tr_return_column",
                "price_column",
                "price_return_column",
            ]
        )
    else:
        log = log.sort_values(["status", "isin"]).reset_index(drop=True)
    return updated_catalog, updated_observations, log
