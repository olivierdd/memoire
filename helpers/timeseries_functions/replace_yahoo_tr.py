"""Replace Datastream/Lipper TR and Price columns with Yahoo at series load."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from helpers.funds_functions.map_yahoo_timeseries import (
    align_yahoo_levels_to_index,
    levels_and_returns_with_holiday_na,
    spx_flat_holiday_mask,
)
from helpers.timeseries_functions.yahoo_tr_freeze import (
    fetch_yahoo_price_levels_prefer_freeze,
    fetch_yahoo_total_return_levels_prefer_freeze,
    yahoo_tr_freeze_download_date,
)

# Curated offline list: Lipper/Datastream series with persistent level breaks
# whose Yahoo Price+TR showed no lasting break under the rule later formalised
# in §5.3 and matched Lipper 3Y/5Y/10Y performance. CFIMX (US1888501012) is
# intentionally omitted — Yahoo still shows a level jump there. The map is
# fixed at load time; Step 1 does not re-run the Step 5 screen.
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

SOURCE_LIPPER = "Lipper"
SOURCE_YAHOO = "Yahoo"

FUND_CATEGORIES: frozenset[str] = frozenset(
    {"Active MF", "Active ETF", "Passive MF", "Passive ETF", "To Check MF"}
)


def _column_id(catalog: pd.DataFrame, header: str) -> int | None:
    match = catalog.loc[catalog["header"].eq(header), "column"]
    if match.empty:
        return None
    return int(match.iloc[0])


def _ensure_source_column(catalog: pd.DataFrame) -> pd.DataFrame:
    """Keep fund-type ``category`` intact; track origin in ``source``."""
    out = catalog.copy()
    if "source" not in out.columns:
        out["source"] = SOURCE_LIPPER
    else:
        out["source"] = out["source"].fillna(SOURCE_LIPPER).astype("string")
    return out


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


def lipper_fund_sample_end(catalog: pd.DataFrame) -> pd.Timestamp | None:
    """Modal last date of Lipper fund total-return *level* series.

    Datastream fund extracts typically stop on the last trading day of the
    latest completed month. That date is the common sample end for every
    series in the working panel (funds, indices and the risk-free rate).
    Yahoo-replaced funds are excluded so a longer Yahoo history cannot pull
    the endpoint forward.
    """
    header = catalog["header"].astype("string")
    category = catalog["category"].astype("string")
    mask = category.isin(FUND_CATEGORIES) & header.str.endswith(" TR")
    if "source" in catalog.columns:
        mask = mask & catalog["source"].fillna(SOURCE_LIPPER).ne(SOURCE_YAHOO)
    if "id" in catalog.columns:
        mask = mask & ~catalog["id"].astype("string").isin(YAHOO_TR_REPLACE_ISINS)
    lasts = pd.to_datetime(catalog.loc[mask, "last_date"], errors="coerce").dropna()
    if lasts.empty:
        return None
    return pd.Timestamp(lasts.mode().iloc[0]).normalize()


def truncate_panel_to_sample_end(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    end_date: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp | None]:
    """Drop observation rows after the common fund sample end.

    When ``end_date`` is omitted, it is taken from
    :func:`lipper_fund_sample_end`. Rows with a missing date index are kept.
    Catalog coverage columns are refreshed. If no endpoint can be determined,
    the inputs are returned unchanged.
    """
    endpoint = (
        pd.Timestamp(end_date).normalize()
        if end_date is not None
        else lipper_fund_sample_end(catalog)
    )
    if endpoint is None or pd.isna(endpoint):
        return catalog, observations, None

    index = pd.to_datetime(observations.index, errors="coerce")
    keep = index.isna() | (index <= endpoint)
    if bool(keep.all()):
        refreshed = _refresh_coverage(catalog, observations)
        return refreshed, observations, endpoint

    truncated = observations.loc[keep].copy()
    refreshed = _refresh_coverage(catalog, truncated)
    return refreshed, truncated, endpoint


def _write_level_pair(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    level_id: int,
    return_id: int,
    aligned: pd.Series,
    level_note: str,
    holiday_mask: pd.Series | None = None,
) -> pd.Series:
    """Write Yahoo levels and session returns; keep category, set source=Yahoo."""
    filled, returns = levels_and_returns_with_holiday_na(aligned, holiday_mask)
    observations[level_id] = filled
    observations[return_id] = returns
    level_mask = catalog["column"].eq(level_id)
    return_mask = catalog["column"].eq(return_id)
    catalog.loc[level_mask, "source"] = SOURCE_YAHOO
    catalog.loc[return_mask, "source"] = SOURCE_YAHOO
    catalog.loc[level_mask, "note"] = level_note
    catalog.loc[return_mask, "note"] = "Daily simple return = P(t)/P(t-1) - 1"
    return filled


def replace_datastream_tr_with_yahoo(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    replacements: dict[str, str] | None = None,
    fetch_tr_levels: Callable[
        [str], pd.Series | None
    ] = fetch_yahoo_total_return_levels_prefer_freeze,
    fetch_price_levels: Callable[
        [str], pd.Series | None
    ] = fetch_yahoo_price_levels_prefer_freeze,
    # Backward-compatible alias used by older tests/callers.
    fetch_levels: Callable[[str], pd.Series | None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Overwrite main TR/Price columns (and %) with Yahoo for configured ISINs.

    - ``{ISIN} TR`` / ``{ISIN} TR %`` ← distribution-adjusted Close (``auto_adjust=True``)
    - ``{ISIN} Price`` / ``{ISIN} Price %`` ← split-adjusted Close (``auto_adjust=False``)

    Levels are read from the frozen extract in ``cache/yahoo-tr-replacements/``
    when present (see ``yahoo_tr_freeze``); otherwise a live Yahoo download is
    used. Fund-type ``category`` (Active MF, Passive MF, …) is preserved. Origin
    is recorded in ``source`` (``Lipper`` by default, ``Yahoo`` after
    replacement). Headers stay the primary Datastream names so later steps
    still treat them as the fund's main series. Dates without a Yahoo print
    stay blank. S&P-flat exchange holidays are left NA (level and %) and the
    next session’s return is recomputed; step 2 also normalises the full panel
    on the market calendar.

    Returns ``(catalog, observations, replacement_log)``.
    """
    mapping = dict(replacements if replacements is not None else YAHOO_TR_REPLACEMENTS)
    tr_fetch = fetch_levels if fetch_levels is not None else fetch_tr_levels
    updated_catalog = _ensure_source_column(catalog)
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
            level_note="Total return index, daily",
            holiday_mask=holiday_mask,
        )
        price_filled = _write_level_pair(
            updated_catalog,
            updated_observations,
            level_id=price_id,
            return_id=price_ret_id,
            aligned=price_aligned,
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
