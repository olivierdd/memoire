"""Shared checks and repair steps for load-series-v2 marimo notebook."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from helpers.timeseries_functions.check_timeseries_consistency import (
    DEFAULT_DATE_GAP_DAYS,
    DEFAULT_INDEX_GAP,
    DEFAULT_LEVEL_JUMP,
    DEFAULT_REVERSAL_BAND,
    DEFAULT_SCALE_FACTOR,
    DEFAULT_SCALE_WINDOW_DAILY,
    DEFAULT_SPIKE_RETURN,
    _flag_scale_at,
    locate_series_issues,
)
def daily_consistency_controls() -> dict[str, Any]:
    """Thresholds for daily TR % checks vs S&P 500 TR %."""
    return {
        "spike_return": DEFAULT_SPIKE_RETURN,
        "reversal_band": DEFAULT_REVERSAL_BAND,
        "scale_factor": DEFAULT_SCALE_FACTOR,
        "scale_window": DEFAULT_SCALE_WINDOW_DAILY,
        "level_jump": DEFAULT_LEVEL_JUMP,
        "index_gap": DEFAULT_INDEX_GAP,
        "date_gap_days": DEFAULT_DATE_GAP_DAYS,
    }


def _daily_frame(column_id: int, index_id: int, observations: pd.DataFrame) -> pd.DataFrame | None:
    series = observations[column_id].dropna()
    if len(series) < 2:
        return None
    window = observations.loc[series.index[0] : series.index[-1]]
    dates = pd.to_datetime(window.index)
    fund = window[column_id]
    market = window[index_id]
    if isinstance(fund, pd.DataFrame):
        fund = fund.iloc[:, 0]
    if isinstance(market, pd.DataFrame):
        market = market.iloc[:, 0]
    return pd.DataFrame(
        {
            "Period": dates.strftime("%b %Y"),
            "Date": dates,
            "fund": fund.to_numpy(),
            "S&P 500 TR": market.to_numpy(),
        }
    )


def _index_return_column(catalog: pd.DataFrame) -> int:
    is_return = catalog["note"].astype("string").str.startswith("Daily simple return")
    row = catalog.loc[is_return & catalog["header"].eq("S&P 500 TR %")].iloc[0]
    return int(row.column)


def spx_exchange_holiday_dates(
    market_level: pd.Series,
    *,
    level_tolerance: float = 1e-6,
) -> pd.DatetimeIndex:
    """Dates where the S&P 500 TR level equals the prior session close."""
    previous_close = market_level.shift(1)
    return market_level.index[
        market_level.notna()
        & previous_close.notna()
        & (market_level - previous_close).abs().le(level_tolerance)
    ]


def exchange_holidays_from_panel(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    level_tolerance: float = 1e-6,
) -> pd.DatetimeIndex:
    """S&P-flat exchange holidays on the loaded daily panel."""
    market = catalog.loc[
        catalog["header"].eq("S&P 500 TR")
        & catalog["note"].astype("string").str.startswith("Total return index")
    ]
    if market.empty:
        return pd.DatetimeIndex([])
    market_level = observations[int(market.iloc[0].column)]
    return spx_exchange_holiday_dates(market_level, level_tolerance=level_tolerance)


def nyse_holidays_on_panel_weekdays(
    panel_index: pd.DatetimeIndex,
) -> pd.DatetimeIndex:
    """Official NYSE holidays among weekdays present in the panel index."""
    import exchange_calendars as xcals

    if len(panel_index) == 0:
        return pd.DatetimeIndex([])
    start = pd.Timestamp(panel_index.min()).normalize()
    end = pd.Timestamp(panel_index.max()).normalize()
    sessions = xcals.get_calendar("XNYS").sessions_in_range(start, end)
    weekdays = panel_index[panel_index.dayofweek < 5]
    return pd.DatetimeIndex(weekdays.difference(sessions)).sort_values()


def holiday_calendar_diagnostic(
    holiday_dates: pd.DatetimeIndex,
    panel_index: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare S&P-flat holidays with official NYSE holidays on panel weekdays.

    Returns ``(holiday_table, nyse_only)``. ``holiday_table`` has one row per
    date in ``holiday_dates`` with an ``nyse_holiday`` flag. ``nyse_only`` lists
    NYSE weekday holidays in the panel that are not in ``holiday_dates``.
    """
    nyse = nyse_holidays_on_panel_weekdays(panel_index)
    nyse_set = {pd.Timestamp(d).normalize() for d in nyse}
    rows = []
    for date in pd.DatetimeIndex(holiday_dates).sort_values():
        stamp = pd.Timestamp(date).normalize()
        rows.append(
            {
                "date": stamp,
                "weekday": stamp.day_name(),
                "nyse_holiday": stamp in nyse_set,
            }
        )
    holiday_table = pd.DataFrame(rows)
    if holiday_table.empty:
        holiday_table = pd.DataFrame(columns=["date", "weekday", "nyse_holiday"])
    holiday_set = {pd.Timestamp(d).normalize() for d in holiday_dates}
    only = sorted(nyse_set - holiday_set)
    nyse_only = pd.DataFrame(
        {
            "date": only,
            "weekday": [pd.Timestamp(d).day_name() for d in only],
        }
    )
    return holiday_table, nyse_only


def non_zero_holiday_returns(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    holiday_dates: pd.DatetimeIndex,
    *,
    return_tolerance: float = 1e-10,
) -> pd.DataFrame:
    """Pre-treatment daily returns that are non-zero on an S&P-flat holiday."""
    is_return = catalog["note"].astype("string").str.startswith("Daily simple return")
    holidays = pd.DatetimeIndex(holiday_dates)
    rows: list[dict[str, Any]] = []
    for row in catalog.loc[is_return].itertuples(index=False):
        series = observations[int(row.column)]
        values = series.reindex(holidays)
        mask = values.notna() & (values.abs() > return_tolerance)
        for date, value in values.loc[mask].items():
            rows.append(
                {
                    "id": row.id,
                    "header": row.header,
                    "category": row.category,
                    "date": pd.Timestamp(date).normalize(),
                    "return": float(value),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["id", "header", "category", "date", "return"])
    return frame.sort_values(["header", "date"]).reset_index(drop=True)


def _series_display_name(catalog: pd.DataFrame, series_id: str) -> str:
    names = catalog.loc[catalog["id"].eq(series_id), "name"].astype("string")
    if names.empty:
        return series_id
    name = str(names.iloc[0])
    for marker in (" - TOT RETURN", " - PRICE", " - Tot Return", " - Price"):
        if marker in name:
            return name.split(marker)[0].strip()
    return name.strip()


def _holiday_move_booked_on_holiday(
    observations: pd.DataFrame,
    level_col: int,
    return_col: int,
    dates: list[pd.Timestamp],
    *,
    return_tolerance: float,
) -> bool:
    """True if each flagged holiday moves vs the prior close, then stays flat next."""
    if not dates:
        return False
    level = observations[level_col]
    returns = observations[return_col]
    for date in dates:
        if date not in observations.index:
            return False
        position = observations.index.get_loc(date)
        try:
            position = int(position)
        except (TypeError, ValueError):
            return False
        if position <= 0 or position + 1 >= len(observations.index):
            return False
        prev = observations.index[position - 1]
        nxt = observations.index[position + 1]
        prev_level = level.loc[prev]
        holiday_level = level.loc[date]
        next_level = level.loc[nxt]
        next_return = returns.loc[nxt]
        if pd.isna(prev_level) or pd.isna(holiday_level) or pd.isna(next_level):
            return False
        if abs(float(holiday_level) - float(prev_level)) <= 1e-6:
            return False
        if abs(float(next_level) - float(holiday_level)) > 1e-6:
            return False
        if pd.isna(next_return) or abs(float(next_return)) > return_tolerance:
            return False
    return True


def non_zero_holiday_case_review(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    holiday_dates: pd.DatetimeIndex,
    correction_log: pd.DataFrame,
    *,
    return_tolerance: float = 1e-10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Summarise identifiers with non-zero holiday returns and classify the pattern.

    Returns ``(case_summary, detail)``. ``detail`` is ``non_zero_holiday_returns``
    enriched with an ``nyse_holiday`` flag. Every flagged date is checked against
    the official NYSE list; the finding states whether the print looks like a
    source artifact rather than a misclassified trading day.
    """
    detail = non_zero_holiday_returns(
        catalog,
        observations,
        holiday_dates,
        return_tolerance=return_tolerance,
    )
    holiday_table, _ = holiday_calendar_diagnostic(holiday_dates, observations.index)
    nyse_by_date = {
        pd.Timestamp(row.date).normalize(): bool(row.nyse_holiday)
        for row in holiday_table.itertuples(index=False)
    }
    if detail.empty:
        empty_summary = pd.DataFrame(
            columns=[
                "id",
                "name",
                "category",
                "holiday_dates",
                "all_nyse",
                "max_cells_changed",
                "finding",
            ]
        )
        return empty_summary, detail.assign(nyse_holiday=pd.Series(dtype=bool))

    detail = detail.copy()
    detail["nyse_holiday"] = detail["date"].map(
        lambda d: nyse_by_date.get(pd.Timestamp(d).normalize(), False)
    )
    rows: list[dict[str, Any]] = []
    for series_id, group in detail.groupby("id", sort=True):
        dates = sorted({pd.Timestamp(d).normalize() for d in group["date"]})
        category = group["category"].iloc[0]
        abs_returns = group["return"].abs()
        max_cells = 0
        if not correction_log.empty and "id" in correction_log.columns:
            id_log = correction_log.loc[correction_log["id"].eq(series_id)]
            if not id_log.empty:
                max_cells = int(id_log["cells_changed"].max())
        finding = (
            "Non-zero holiday print on confirmed NYSE holidays; "
            "next-session return restated under the holiday treatment."
        )
        if float(abs_returns.max()) < 1e-3:
            finding = (
                "Negligible holiday tick (rounding / noise) on a confirmed "
                "NYSE holiday."
            )
        else:
            for level_suffix, return_suffix, reset_level in (
                ("Price", "Price %", 10.0),
                ("TR", "TR %", None),
            ):
                level_header = f"{series_id} {level_suffix}"
                return_header = f"{series_id} {return_suffix}"
                level_rows = catalog.loc[catalog["header"].eq(level_header)]
                return_rows = catalog.loc[catalog["header"].eq(return_header)]
                if level_rows.empty or return_rows.empty:
                    continue
                level_col = int(level_rows.iloc[0]["column"])
                return_col = int(return_rows.iloc[0]["column"])
                holiday_levels = observations.loc[
                    observations.index.isin(dates), level_col
                ].dropna()
                if (
                    reset_level is not None
                    and len(holiday_levels)
                    and holiday_levels.nunique() == 1
                    and abs(float(holiday_levels.iloc[0]) - reset_level) <= 1e-9
                ):
                    finding = (
                        f"{level_suffix} level reset to {reset_level:.2f} on "
                        "holidays (source placeholder), then rebound on the "
                        "next session."
                    )
                    break
                if _holiday_move_booked_on_holiday(
                    observations,
                    level_col,
                    return_col,
                    dates,
                    return_tolerance=return_tolerance,
                ):
                    finding = (
                        "Level moves on the holiday and is unchanged on the "
                        "next session (move booked on the holiday row)."
                    )
                    break
        rows.append(
            {
                "id": series_id,
                "name": _series_display_name(catalog, str(series_id)),
                "category": category,
                "holiday_dates": len(dates),
                "all_nyse": bool(group["nyse_holiday"].all()),
                "max_cells_changed": max_cells,
                "finding": finding,
            }
        )
    summary = pd.DataFrame(rows).sort_values(
        ["max_cells_changed", "id"], ascending=[False, True]
    ).reset_index(drop=True)
    return summary, detail.sort_values(["header", "date"]).reset_index(drop=True)


def summarize_tr_consistency(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    flags: Iterable[str] | None = None,
    exchange_holidays: pd.DatetimeIndex | None = None,
    use_scale: bool = True,
) -> tuple[dict[str, Any], pd.DataFrame, dict[int, Any]]:
    """Score each fund TR % series vs S&P 500 TR %; return controls, summary, checks.

    Pass ``flags`` to compute only the named checks (and prerequisites). ``None``
    runs every check. Unrequested flag columns stay at zero / False in the summary.

    When ``use_scale`` is false, scale is not run and level_jump / spikes do not
    apply post-scale-shift suppression.
    """
    controls = daily_consistency_controls()
    index_id = _index_return_column(catalog)
    if exchange_holidays is None:
        exchange_holidays = exchange_holidays_from_panel(catalog, observations)
    is_return = catalog["note"].astype("string").str.startswith("Daily simple return")
    levels = catalog.loc[~is_return].copy()
    level_by_header = {str(row.header): row for row in levels.itertuples(index=False)}

    checks: dict[int, Any] = {}
    rows: list[dict[str, Any]] = []
    for return_row in catalog.loc[is_return].itertuples(index=False):
        if int(return_row.column) == index_id:
            continue
        level = level_by_header.get(str(return_row.header).removesuffix(" %"))
        if level is None or not str(level.note).startswith("Total return index"):
            continue
        series_days = _daily_frame(int(return_row.column), index_id, observations)
        record: dict[str, Any] = {
            "column": int(return_row.column),
            "id": return_row.id,
            "header": return_row.header,
            "category": return_row.category,
            "kind": None if level is None else level.note,
            "days": 0,
            "gaps": 0,
            "spikes": 0,
            "level_jumps": 0,
            "scale_shift": False,
            "far_from_index": 0,
        }
        if series_days is not None:
            series_check = locate_series_issues(
                str(return_row.header),
                "fund",
                fund_timeseries=series_days,
                index_column="S&P 500 TR",
                flags=flags,
                exchange_holidays=exchange_holidays,
                use_scale=use_scale,
                **controls,
            )
            checks[int(return_row.column)] = series_check
            checked = series_check.months
            record["days"] = int(checked["return"].notna().sum())
            record["gaps"] = int(checked["gap"].sum())
            record["spikes"] = int(checked["spike"].sum())
            record["level_jumps"] = int(checked["level_jump"].sum())
            record["scale_shift"] = series_check.scale_at is not None
            record["far_from_index"] = int(checked["wide"].sum())
        rows.append(record)

    issue_summary = pd.DataFrame(rows)
    issue_summary["issues"] = (
        issue_summary["gaps"]
        + issue_summary["spikes"]
        + issue_summary["level_jumps"]
        + issue_summary["scale_shift"].astype(int)
        + issue_summary["far_from_index"]
    )
    issue_summary = issue_summary.sort_values(
        ["issues", "header"], ascending=[False, True]
    ).reset_index(drop=True)
    return controls, issue_summary, checks


def flag_summary_table(issue_summary: pd.DataFrame, flag: str) -> pd.DataFrame:
    """Subset series with at least one instance of ``flag``."""
    column_map = {
        "gap": "gaps",
        "gaps": "gaps",
        "scale": "scale_shift",
        "scale_shift": "scale_shift",
        "level_jump": "level_jumps",
        "level_jumps": "level_jumps",
        "spike": "spikes",
        "spikes": "spikes",
        "wide": "far_from_index",
        "far_from_index": "far_from_index",
    }
    col = column_map[flag]
    if col == "scale_shift":
        mask = issue_summary[col].astype(bool)
    else:
        mask = issue_summary[col].gt(0)
    return issue_summary.loc[mask].reset_index(drop=True)


# Identifiers removed from the thesis S&P 500 sample after the far-from-index
# screen (§8). Kept as data (not dropped as data errors): the official Lipper
# benchmark is not S&P 500 TR, so the S&P 500 comparison is the wrong test.
THESIS_SAMPLE_DROPS: tuple[dict[str, str], ...] = (
    {
        "isin": "US46090A7054",
        "ticker": "PHDG",
        "name": "Invesco S&P 500 Downside Hedged ETF",
        "fund_type": "Alternatives",
        "benchmark_ticker": ".SPVQDTR",
        "benchmark_name": "S&P 500 Dynamic VEQTOR Index",
        "reason": (
            "Official Lipper benchmark is the S&P 500 Dynamic VEQTOR Index "
            "(.SPVQDTR), not S&P 500 TR (.SPXTR). The fund is an alternatives "
            "strategy that allocates between equity, implied volatility and "
            "cash; large gaps versus S&P 500 TR are expected by design. "
            "Removing it is a sample-selection correction, not a data repair."
        ),
    },
)


def thesis_sample_drop_isins() -> frozenset[str]:
    """ISIN set for :data:`THESIS_SAMPLE_DROPS`."""
    return frozenset(str(row["isin"]).strip() for row in THESIS_SAMPLE_DROPS)


def drop_identifiers_from_panel(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    isins: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Remove all series of the given identifiers from catalog and panel.

    Returns ``(catalog, observations, drop_log)``. ``drop_log`` has one row per
    removed identifier (even if it was already absent). Columns that do not
    belong to a dropped identifier are left unchanged and keep their order.
    """
    targets = {
        str(isin).strip()
        for isin in (thesis_sample_drop_isins() if isins is None else isins)
        if str(isin).strip()
    }
    id_text = catalog["id"].astype("string").str.strip()
    drop_mask = id_text.isin(targets)
    kept_catalog = catalog.loc[~drop_mask].copy().reset_index(drop=True)
    drop_columns = [
        int(column)
        for column in catalog.loc[drop_mask, "column"].tolist()
        if int(column) in observations.columns
    ]
    kept_observations = observations.drop(columns=drop_columns, errors="ignore")

    meta_by_isin = {str(row["isin"]).strip(): row for row in THESIS_SAMPLE_DROPS}
    rows: list[dict[str, Any]] = []
    for isin in sorted(targets):
        meta = meta_by_isin.get(isin, {})
        n_series = int((drop_mask & id_text.eq(isin)).sum()) if len(catalog) else 0
        rows.append(
            {
                "isin": isin,
                "ticker": meta.get("ticker", ""),
                "name": meta.get("name", ""),
                "fund_type": meta.get("fund_type", ""),
                "benchmark_ticker": meta.get("benchmark_ticker", ""),
                "benchmark_name": meta.get("benchmark_name", ""),
                "series_removed": n_series,
                "present": n_series > 0,
                "reason": meta.get("reason", ""),
            }
        )
    drop_log = pd.DataFrame(rows)
    return kept_catalog, kept_observations, drop_log


def drop_isins_from_funds_frame(
    frame: pd.DataFrame,
    isins: Iterable[str] | None = None,
    *,
    isin_column: str = "ISIN",
) -> pd.DataFrame:
    """Drop rows whose ISIN is in the thesis sample-drop list."""
    targets = {
        str(isin).strip()
        for isin in (thesis_sample_drop_isins() if isins is None else isins)
        if str(isin).strip()
    }
    if not targets or isin_column not in frame.columns:
        return frame
    keep = ~frame[isin_column].astype("string").str.strip().isin(targets)
    return frame.loc[keep].copy().reset_index(drop=True)


def _values_match(left: float, right: float, tolerance: float) -> bool:
    left_missing = left != left
    right_missing = right != right
    if left_missing and right_missing:
        return True
    if left_missing or right_missing:
        return False
    return abs(left - right) <= tolerance


def carry_holiday_placeholders(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    """Blank level and daily return on S&P-flat exchange holidays; fix next session %."""
    level_tolerance = 1e-6
    return_tolerance = 1e-10
    nan = float("nan")
    market = catalog.loc[
        catalog["header"].eq("S&P 500 TR")
        & catalog["note"].astype("string").str.startswith("Total return index")
    ].iloc[0]
    market_level = observations[int(market.column)]
    holiday_dates = spx_exchange_holiday_dates(
        market_level, level_tolerance=level_tolerance
    )
    holiday_positions = observations.index.get_indexer(holiday_dates)

    return_ids = {
        row.header: int(row.column)
        for row in catalog.loc[
            catalog["note"].astype("string").str.startswith("Daily simple return")
        ].itertuples(index=False)
    }
    level_notes = ("Price, daily", "Total return index, daily", "Price index, daily")
    corrected_observations = observations.copy()
    correction_rows: list[dict[str, Any]] = []
    for level_row in catalog.loc[catalog["note"].astype("string").isin(level_notes)].itertuples(
        index=False
    ):
        return_id = return_ids.get(f"{level_row.header} %")
        if return_id is None:
            continue
        level_id = int(level_row.column)
        level_values = corrected_observations[level_id].to_numpy(dtype="float64", copy=True)
        return_values = corrected_observations[return_id].to_numpy(dtype="float64", copy=True)
        original_level = level_values.copy()
        original_return = return_values.copy()
        holidays_fixed = 0
        for position in holiday_positions:
            if position <= 0:
                continue
            prior_close = level_values[position - 1]
            if prior_close != prior_close:
                continue
            level_values[position] = nan
            return_values[position] = nan
            holidays_fixed += 1
            following = position + 1
            if (
                following < len(level_values)
                and level_values[following] == level_values[following]
                and prior_close != 0
            ):
                return_values[following] = level_values[following] / prior_close - 1.0
        if holidays_fixed == 0:
            continue
        corrected_observations[level_id] = level_values
        corrected_observations[return_id] = return_values
        cells_changed = 0
        for before, after in zip(original_level, level_values, strict=True):
            if not _values_match(before, after, level_tolerance):
                cells_changed += 1
        for before, after in zip(original_return, return_values, strict=True):
            if not _values_match(before, after, return_tolerance):
                cells_changed += 1
        correction_rows.append(
            {
                "id": level_row.id,
                "header": level_row.header,
                "category": level_row.category,
                "kind": level_row.note,
                "holidays_fixed": holidays_fixed,
                "cells_changed": cells_changed,
            }
        )

    correction_log = pd.DataFrame(correction_rows)
    if correction_log.empty:
        correction_log = pd.DataFrame(
            columns=["id", "header", "category", "kind", "holidays_fixed", "cells_changed"]
        )
    else:
        correction_log = correction_log.sort_values(
            ["cells_changed", "header"], ascending=[False, True]
        ).reset_index(drop=True)
    return corrected_observations, correction_log, holiday_dates


def lasting_breaks(
    observations: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    level_jump: float = DEFAULT_LEVEL_JUMP,
) -> tuple[list[dict[str, Any]], pd.Series]:
    """Scan fund Price % and TR % for sticky level breaks vs S&P 500 TR %.

    A day is a lasting break when ``|r| ≥ level_jump``, ``|r − S&P| ≥ level_jump/2``,
    and the compounded follow-through ``s`` over the next sessions satisfies
    ``s / r ≥ 1/2`` (same sign as the break-day return, and at least half of it
    remains). No scale-shift suppression here — that filter is applied only when
    building the TR Result set (see ``tr_result_breaks``).
    """
    index_id = _index_return_column(catalog)
    market_return = observations[index_id]
    is_return = catalog["note"].astype("string").str.startswith("Daily simple return")
    gap_floor = level_jump / 2.0
    found: list[dict[str, Any]] = []
    for return_row in catalog.loc[is_return].itertuples(index=False):
        header = str(return_row.header)
        if header.endswith("Price %"):
            side = "Price"
        elif header.endswith("TR %"):
            side = "TR"
        else:
            continue
        returns = observations[int(return_row.column)]
        gap = (returns - market_return).abs()
        candidates = returns.index[
            returns.notna()
            & market_return.notna()
            & returns.abs().ge(level_jump)
            & gap.ge(gap_floor)
        ]
        values = returns.to_numpy(dtype="float64")
        for day in candidates:
            position = observations.index.get_loc(day)
            follow = [value for value in values[position : position + 4] if value == value]
            if len(follow) < 2:
                continue
            stayed = 1.0
            for value in follow:
                stayed *= 1.0 + value
            stayed -= 1.0
            jump = float(values[position])
            # Same sign as the break-day return, and at least half of it remains.
            if stayed / jump < 0.5:
                continue
            found.append(
                {
                    "isin": str(return_row.id),
                    "date": pd.Timestamp(day),
                    "side": side,
                    "stored_return": jump,
                }
            )
    return found, market_return


def _tr_scale_cut_dates(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    scale_factor: float,
    scale_window: int,
) -> dict[str, pd.Timestamp]:
    """ISIN → first date of the new scale regime (exclusive for pre-split flags)."""
    index_id = _index_return_column(catalog)
    is_return = catalog["note"].astype("string").str.startswith("Daily simple return")
    levels = catalog.loc[~is_return]
    level_by_header = {str(row.header): row for row in levels.itertuples(index=False)}
    cuts: dict[str, pd.Timestamp] = {}
    for return_row in catalog.loc[is_return].itertuples(index=False):
        header = str(return_row.header)
        if not header.endswith("TR %"):
            continue
        level = level_by_header.get(header.removesuffix(" %"))
        if level is None or not str(level.note).startswith("Total return index"):
            continue
        series_days = _daily_frame(int(return_row.column), index_id, observations)
        if series_days is None:
            continue
        scale_at = _flag_scale_at(
            series_days["fund"].abs(),
            scale_window,
            scale_factor,
        )
        if scale_at is None:
            continue
        cuts[str(return_row.id)] = pd.Timestamp(series_days["Date"].iloc[scale_at])
    return cuts


def tr_result_breaks(
    breaks: list[dict[str, Any]],
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    use_scale: bool = True,
    scale_factor: float = DEFAULT_SCALE_FACTOR,
    scale_window: int = DEFAULT_SCALE_WINDOW_DAILY,
) -> list[dict[str, Any]]:
    """TR-side lasting breaks for Result; optionally drop days on/after a scale split."""
    tr_breaks = [item for item in breaks if item["side"] == "TR"]
    if not use_scale or not tr_breaks:
        return tr_breaks
    cuts = _tr_scale_cut_dates(
        catalog,
        observations,
        scale_factor=scale_factor,
        scale_window=scale_window,
    )
    if not cuts:
        return tr_breaks
    kept: list[dict[str, Any]] = []
    for item in tr_breaks:
        cut = cuts.get(str(item["isin"]))
        if cut is not None and pd.Timestamp(item["date"]) >= cut:
            continue
        kept.append(item)
    return kept


def issue_summary_from_tr_breaks(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    tr_breaks: list[dict[str, Any]],
) -> pd.DataFrame:
    """Build a TR % issue_summary with ``level_jumps`` counts (other flags zero)."""
    index_id = _index_return_column(catalog)
    is_return = catalog["note"].astype("string").str.startswith("Daily simple return")
    levels = catalog.loc[~is_return]
    level_by_header = {str(row.header): row for row in levels.itertuples(index=False)}
    jump_counts: dict[str, int] = {}
    for item in tr_breaks:
        key = str(item["isin"])
        jump_counts[key] = jump_counts.get(key, 0) + 1

    rows: list[dict[str, Any]] = []
    for return_row in catalog.loc[is_return].itertuples(index=False):
        if int(return_row.column) == index_id:
            continue
        level = level_by_header.get(str(return_row.header).removesuffix(" %"))
        if level is None or not str(level.note).startswith("Total return index"):
            continue
        series_days = _daily_frame(int(return_row.column), index_id, observations)
        isin = str(return_row.id)
        level_jumps = int(jump_counts.get(isin, 0))
        rows.append(
            {
                "column": int(return_row.column),
                "id": return_row.id,
                "header": return_row.header,
                "category": return_row.category,
                "kind": None if level is None else level.note,
                "days": 0 if series_days is None else int(series_days["fund"].notna().sum()),
                "gaps": 0,
                "spikes": 0,
                "level_jumps": level_jumps,
                "scale_shift": False,
                "far_from_index": 0,
                "issues": level_jumps,
            }
        )
    issue_summary = pd.DataFrame(rows)
    if issue_summary.empty:
        return issue_summary
    return issue_summary.sort_values(
        ["issues", "header"], ascending=[False, True]
    ).reset_index(drop=True)


def summarize_level_jumps(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    use_scale: bool = True,
) -> tuple[dict[str, Any], pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    """One lasting-break scan; Result = TR hits (+ optional scale gate).

    Returns ``(controls, issue_summary, all_breaks, result_breaks)`` where
    ``all_breaks`` covers Price % and TR % (for Decision rule matching) and
    ``result_breaks`` is the TR-only Result set.
    """
    controls = daily_consistency_controls()
    all_breaks, _market = lasting_breaks(
        observations, catalog, level_jump=float(controls["level_jump"])
    )
    result_breaks = tr_result_breaks(
        all_breaks,
        catalog,
        observations,
        use_scale=use_scale,
        scale_factor=float(controls["scale_factor"]),
        scale_window=int(controls["scale_window"]),
    )
    issue_summary = issue_summary_from_tr_breaks(catalog, observations, result_breaks)
    return controls, issue_summary, all_breaks, result_breaks


def rescale_level_breaks(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    breaks: list[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply curated corporate-action rules to lasting breaks (Decision).

    Detection is not done here when ``breaks`` is passed — pass the shared
    ``lasting_breaks`` scan from ``summarize_level_jumps``. Rules in
    ``level_actions`` / ``kept_distributions`` fire only when the matching
    ISIN/date/side is still present in ``breaks``.
    """

    def fund_label(catalog_frame: pd.DataFrame, isin: str) -> str:
        names = catalog_frame.loc[catalog_frame["id"].eq(isin), "name"].astype("string")
        label = str(names.iloc[0]) if len(names) else isin
        for suffix in (" - TOT RETURN IND", " - PRICE", " - TOTAL NET ASSETS"):
            if label.endswith(suffix):
                return label[: -len(suffix)]
        return label

    def column_id(catalog_frame: pd.DataFrame, header: str) -> int | None:
        match = catalog_frame.loc[catalog_frame["header"].eq(header), "column"]
        if match.empty:
            return None
        return int(match.iloc[0])

    def changed_cells(before, after, tolerance: float) -> int:
        count = 0
        for left, right in zip(before, after, strict=True):
            left_missing = left != left
            right_missing = right != right
            if left_missing and right_missing:
                continue
            if left_missing or right_missing or abs(left - right) > tolerance:
                count += 1
        return count

    def scale_series(
        frame: pd.DataFrame,
        catalog_frame: pd.DataFrame,
        isin: str,
        side: str,
        day: str,
        factor: float,
        mode: str,
    ) -> tuple[int, float | None, float | None]:
        level_id = column_id(catalog_frame, f"{isin} {side}")
        return_id = column_id(catalog_frame, f"{isin} {side} %")
        if level_id is None or return_id is None:
            return 0, None, None
        levels = frame[level_id].to_numpy(dtype="float64", copy=True)
        returns = frame[return_id].to_numpy(dtype="float64", copy=True)
        original_levels = levels.copy()
        original_returns = returns.copy()
        position = frame.index.get_loc(pd.Timestamp(day))
        if mode == "history":
            levels[:position] *= factor
        else:
            levels[position:] *= factor
        previous = levels[position - 1]
        current = levels[position]
        if previous == previous and current == current and previous != 0:
            returns[position] = current / previous - 1.0
        frame[level_id] = levels
        frame[return_id] = returns
        edited = changed_cells(original_levels, levels, 1e-8) + changed_cells(
            original_returns, returns, 1e-12
        )
        return edited, float(original_returns[position]), float(returns[position])

    def history_factor(
        frame: pd.DataFrame, catalog_frame: pd.DataFrame, isin: str, day: str, market_return: pd.Series
    ) -> float:
        level_id = column_id(catalog_frame, f"{isin} Price")
        levels = frame[level_id]
        position = frame.index.get_loc(pd.Timestamp(day))
        previous = float(levels.iloc[position - 1])
        current = float(levels.iloc[position])
        session = float(market_return.iloc[position])
        return current / (previous * (1.0 + session))

    def forward_factor(
        frame: pd.DataFrame,
        catalog_frame: pd.DataFrame,
        isin: str,
        day: str,
        market_return: pd.Series,
        anchor: str,
    ) -> float:
        price_id = column_id(catalog_frame, f"{isin} Price")
        tr_id = column_id(catalog_frame, f"{isin} TR")
        position = frame.index.get_loc(pd.Timestamp(day))
        tr_level = frame[tr_id]
        if anchor == "price":
            price_level = frame[price_id]
            carried = float(tr_level.iloc[position - 1]) / float(price_level.iloc[position - 1])
            target = float(price_level.iloc[position]) * carried
        else:
            target = float(tr_level.iloc[position - 1]) * (1.0 + float(market_return.iloc[position]))
        return target / float(tr_level.iloc[position])

    # Corporate-action rescales for funds that still use Datastream/Lipper
    # Price+TR. Yahoo-replaced ISINs (see YAHOO_TR_REPLACEMENTS) are
    # intentionally absent: Step 1 already swapped those series, so Datastream
    # split/rebase factors must not be applied. Residual breaks on Yahoo funds
    # surface as Decision "not adjusted" rows instead.
    level_actions = [
        {
            "isin": "US1888501012",
            "date": "2025-05-12",
            "sides": ("Price", "TR"),
            "mode": "history",
            "factor": 1 / 100,
            "why": (
                "The fund carried out a 10-for-1 split effective 12 May 2025. "
                "The published pre-split NAV on 9 May 2025 was $139.46, so a "
                "correctly adjusted history should print near $13.95. The "
                "vendor prints 1,394.60, ten times the published NAV. The "
                "history was multiplied by 10 when it should have been divided "
                "by 10, a total error of 10² = 100 (case 2 in §5.2). Pre-break "
                "price and TR levels are therefore divided by 100. "
                "Sources: Clipper Fund (2025), “Clipper Fund Share Split”, "
                "https://clipperfund.com/share-split (accessed 24 November "
                "2026), which states the 10:1 ratio, record date 9 May 2025, "
                "effective date 12 May 2025, and the worked example with NAV "
                "$139.46 before the split; Clipper Fund (2025), IRS Form 8937, "
                "Report of Organizational Actions Affecting Basis of "
                "Securities, "
                "https://clipperfund.com/documents/Clipper_8937_signed-may.pdf "
                "(accessed 24 November 2026)."
            ),
        },
    ]
    kept_distributions = [
        {
            "isin": "US00791R7807",
            "date": "2025-12-18",
            "sides": ("Price",),
            "why": (
                "On 18 December 2025 the price falls from 18.75 to 3.76 "
                "(about 80% of the cum-distribution NAV), while the TR index "
                "stays near 246. The drop is the ex-distribution NAV after a "
                "long-term capital-gain distribution of $15.1441 per share "
                "(about 81% of the $18.75 cum-NAV). Adding the distribution "
                "back gives a total return of about +0.8% on the day, "
                "(3.76 + 15.1441)/18.75 − 1, which matches the continuous TR "
                "series. This is not a level error. "
                "Sources: The Advisors’ Inner Circle Fund II (2025), Annual "
                "Financials and Other Information, Vontobel U.S. Equity Fund, "
                "as of 31 December 2025, Financial Highlights (Y Shares: net "
                "realized-gain distribution of $15.14 per share in the period "
                "ended 31 December 2025) and Notice to Shareholders "
                "(distributions for that period designated 98.01% long-term "
                "capital gain), "
                "https://am.vontobel.com/en/document/"
                "b2cce270-c3c5-4949-a54b-96322f3a63a4/"
                "Annual-Report_20251231_EN_Vontobel-U.S.-Equity-Fund.pdf "
                "(accessed 24 November 2026); the four-decimal cash amount "
                "$15.1441 on ex-date 18 December 2025 is the LT capital-gains "
                "distribution reported by S&P Global Market Intelligence via "
                "Stock Analysis, "
                "https://stockanalysis.com/quote/mutf/VNUYX/dividend/ "
                "(accessed 24 November 2026)."
            ),
        },
        {
            "isin": "US3624014086",
            "date": "2026-10-28",
            "sides": ("Price",),
            "why": (
                "A prospectus supplement dated 14 October 2026 announces the "
                "Board’s approval of a Plan of Liquidation, with liquidation "
                "on or around 18 December 2026. On 28 October 2026 the price "
                "falls from 14.51 to 6.10 and stays there, while the TR series "
                "does not fall. That date matches the fund’s published Class I "
                "distribution (record 28 October 2026, total $8.44 per share, "
                "reinvestment price $6.10). The drop is therefore a "
                "distribution during the wind-down, not a level error. As a "
                "spot check, the vendor level on 25 April 2025 matches a "
                "published NAV of $12.92. "
                "Sources: Gabelli SRI Fund, Inc. (2026), Supplement dated "
                "14 October 2026 to the Statutory Prospectus, Summary "
                "Prospectus and SAI dated 30 April 2026, "
                "https://gabelli.com/wp-content/uploads/2026/10/SRI-Prospectus.pdf "
                "(accessed 24 November 2026); Gabelli Funds (2026), Mutual "
                "Funds Distributions (SRIDX), "
                "https://gabelli.com/funds/open-ends/distributions/ "
                "(accessed 24 November 2026)."
            ),
        },
    ]

    def describe_factor(factor: float, when: str) -> str:
        if factor >= 1:
            rounded = round(factor)
            if abs(factor - rounded) < 1e-6:
                return f"× {rounded:.0f} {when}"
            return f"× {factor:.4f} {when}"
        inverse = 1.0 / factor
        rounded = round(inverse)
        if abs(inverse - rounded) < 1e-4:
            return f"÷ {rounded:.0f} {when}"
        if inverse >= 100:
            return f"÷ {inverse:,.1f} {when}"
        return f"÷ {inverse:.4f} {when}"

    if breaks is None:
        breaks, market_return = lasting_breaks(observations, catalog)
    else:
        market_return = observations[_index_return_column(catalog)]
    break_keys = {(item["isin"], item["date"].strftime("%Y-%m-%d"), item["side"]) for item in breaks}
    stored_returns = {
        (item["isin"], item["date"].strftime("%Y-%m-%d"), item["side"]): item["stored_return"]
        for item in breaks
    }
    adjusted_observations = observations.copy()
    action_rows: list[dict[str, Any]] = []
    for action in level_actions:
        mode = action["mode"]
        pending = [
            side for side in action["sides"] if (action["isin"], action["date"], side) in break_keys
        ]
        for side in action["sides"]:
            if side in pending:
                continue
            action_rows.append(
                {
                    "isin": action["isin"],
                    "fund": fund_label(catalog, action["isin"]),
                    "date": action["date"],
                    "series": side,
                    "decision": "already rescaled",
                    "detected": False,
                    "adjustment": "left unchanged",
                    "return_before": None,
                    "return_after": None,
                    "cells": 0,
                    "why": action["why"],
                }
            )
        if not pending:
            continue
        if "factor" in action:
            factor = action["factor"]
        elif mode == "history":
            factor = history_factor(
                adjusted_observations, catalog, action["isin"], action["date"], market_return
            )
        else:
            factor = forward_factor(
                adjusted_observations,
                catalog,
                action["isin"],
                action["date"],
                market_return,
                action["anchor"],
            )
        when = "from the break forward" if mode == "forward" else "before the break"
        adjustment = describe_factor(factor, when)
        for side in pending:
            edited, return_before, return_after = scale_series(
                adjusted_observations,
                catalog,
                action["isin"],
                side,
                action["date"],
                factor,
                mode,
            )
            action_rows.append(
                {
                    "isin": action["isin"],
                    "fund": fund_label(catalog, action["isin"]),
                    "date": action["date"],
                    "series": side,
                    "decision": "rescaled",
                    "detected": True,
                    "adjustment": adjustment,
                    "return_before": return_before,
                    "return_after": return_after,
                    "cells": edited,
                    "why": action["why"],
                }
            )
    for action in kept_distributions:
        for side in action["sides"]:
            key = (action["isin"], action["date"], side)
            # Only record when a lasting Price break is still detected — silent
            # otherwise so Decision can stay aligned with Result.
            if key not in break_keys:
                continue
            action_rows.append(
                {
                    "isin": action["isin"],
                    "fund": fund_label(catalog, action["isin"]),
                    "date": action["date"],
                    "series": side,
                    "decision": "kept",
                    "detected": True,
                    "adjustment": "price left unchanged",
                    "return_before": stored_returns.get(key),
                    "return_after": stored_returns.get(key),
                    "cells": 0,
                    "why": action["why"],
                }
            )
    covered = {
        (action["isin"], action["date"], side)
        for action in [*level_actions, *kept_distributions]
        for side in action["sides"]
    }
    for item in breaks:
        key = (item["isin"], item["date"].strftime("%Y-%m-%d"), item["side"])
        if key in covered:
            continue
        action_rows.append(
            {
                "isin": item["isin"],
                "fund": fund_label(catalog, item["isin"]),
                "date": key[1],
                "series": item["side"],
                "decision": "not adjusted",
                "detected": True,
                "adjustment": "",
                "return_before": item["stored_return"],
                "return_after": item["stored_return"],
                "cells": 0,
                "why": "Level break with no corporate-action rule.",
            }
        )

    action_log = pd.DataFrame(action_rows)
    if action_log.empty:
        action_log = pd.DataFrame(
            columns=[
                "isin",
                "fund",
                "date",
                "series",
                "decision",
                "detected",
                "adjustment",
                "return_before",
                "return_after",
                "cells",
                "why",
            ]
        )
    return adjusted_observations, action_log


# Curated distribution-day repairs apply only when the print still looks
# defective after upstream steps (Yahoo replace, rebuild, …). A correct
# ex-distribution day has Price ≠ TR but TR ≈ market; those must not be
# overwritten with an S&P proxy (the Magellan / Yahoo case).
DISTRIBUTION_REPAIR_MIN_PRICE_TR_DISAGREEMENT = 0.01
DISTRIBUTION_REPAIR_MIN_MARKET_RESIDUAL = 0.01


def _format_return_pct(value: float | None, digits: int = 2) -> str:
    if value is None or value != value:
        return "—"
    return f"{100.0 * float(value):+.{digits}f}%"


def _distribution_outcome_note(
    *,
    decision: str,
    adjustment: str,
    mode: str | None,
    return_before: float | None,
    return_after: float | None,
    price_return: float | None,
    market_return: float | None,
    next_return_after: float | None = None,
) -> str:
    """Build the Decision note from the actual outcome, not the curated intent."""
    tr_before = _format_return_pct(return_before)
    tr_after = _format_return_pct(return_after)
    price = _format_return_pct(price_return)
    market = _format_return_pct(market_return)
    if decision == "skipped — already clean":
        return (
            f"Already clean on the current panel "
            f"(TR {tr_before}, price {price}, S&P {market}); left unchanged."
        )
    if decision == "kept":
        return (
            f"Retained as a genuine move "
            f"(TR {tr_before}, price {price}, S&P {market})."
        )
    if adjustment == "already matches":
        proxy = "S&P return" if mode == "forward" else "price return"
        return (
            f"Already matches the {proxy} on the current panel "
            f"(TR {tr_before}); left unchanged."
        )
    if mode == "forward":
        return (
            f"Forward repair: TR {tr_before} → {tr_after} "
            f"(S&P {market}); later levels rescaled."
        )
    next_txt = (
        f"; next return {_format_return_pct(next_return_after)}"
        if next_return_after is not None and next_return_after == next_return_after
        else ""
    )
    return (
        f"One-day repair: TR {tr_before} → {tr_after} "
        f"(price {price}){next_txt}."
    )


def repair_distribution_day_tr(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Repair documented distribution-day total-return spikes.

    Each curated day is rewritten only when both gates hold on the current
    panel: ``|TR% − Price%|`` and ``|TR% − S&P 500 TR %|`` are at least
    ``DISTRIBUTION_REPAIR_MIN_*`` (1% by default). Otherwise the day is logged
    as ``skipped — already clean`` and left unchanged.

    The Decision log keeps the curated raw defect in ``defect`` and builds
    ``outcome`` (also exposed as ``why``) from the actual decision, using the
    current panel values in ``return_before``, ``price_return`` and
    ``market_return``.
    """

    def column_id(header: str) -> int | None:
        match = catalog.loc[catalog["header"].eq(header), "column"]
        return None if match.empty else int(match.iloc[0])

    def fund_label(isin: str) -> str:
        names = catalog.loc[catalog["id"].eq(isin), "name"].astype("string")
        label = str(names.iloc[0]) if len(names) else isin
        for suffix in (" - TOT RETURN IND", " - PRICE", " - TOTAL NET ASSETS"):
            if label.endswith(suffix):
                return label[: -len(suffix)]
        return label

    def changed_cells(before, after, tolerance: float) -> int:
        count = 0
        for left, right in zip(before, after, strict=True):
            left_missing = left != left
            right_missing = right != right
            if left_missing and right_missing:
                continue
            if left_missing or right_missing or abs(left - right) > tolerance:
                count += 1
        return count

    def still_defective(tr_return: float, price_return: float, market_return: float) -> bool:
        if any(value != value for value in (tr_return, price_return, market_return)):
            return False
        disagreement = abs(tr_return - price_return)
        residual = abs(tr_return - market_return)
        return (
            disagreement >= DISTRIBUTION_REPAIR_MIN_PRICE_TR_DISAGREEMENT
            and residual >= DISTRIBUTION_REPAIR_MIN_MARKET_RESIDUAL
        )

    def log_row(
        *,
        isin: str,
        day: str,
        decision: str,
        adjustment: str,
        mode: str | None,
        defect: str,
        return_before: float | None,
        return_after: float | None,
        price_return: float | None,
        market_return: float | None,
        next_return_before: float | None = None,
        next_return_after: float | None = None,
        cells: int = 0,
    ) -> dict[str, Any]:
        outcome = _distribution_outcome_note(
            decision=decision,
            adjustment=adjustment,
            mode=mode,
            return_before=return_before,
            return_after=return_after,
            price_return=price_return,
            market_return=market_return,
            next_return_after=next_return_after,
        )
        return {
            "isin": isin,
            "fund": fund_label(isin),
            "date": day,
            "decision": decision,
            "adjustment": adjustment,
            "mode": mode,
            "defect": defect,
            "outcome": outcome,
            # Compatibility alias: older notebook/prose used ``why`` for the note.
            "why": outcome,
            "return_before": return_before,
            "return_after": return_after,
            "price_return": price_return,
            "market_return": market_return,
            "next_return_before": next_return_before,
            "next_return_after": next_return_after,
            "cells": cells,
        }

    market_id = column_id("S&P 500 TR %")
    # Curated repairs: (isin, day, mode, defect). ``defect`` documents the raw /
    # pre-upstream print only; it must not state the Decision outcome.
    repairs = [
        (
            "US3161841008",
            "2015-12-04",
            "forward",
            "Distribution $0.392. Raw Lipper print: price −2.1%, TR +36%.",
        ),
        (
            "US3161841008",
            "2016-12-02",
            "forward",
            "Distribution $0.186. Raw Lipper print: price −2.1%, TR +18%.",
        ),
        (
            "US3161841008",
            "2017-05-12",
            "forward",
            "Distribution $0.555. Raw Lipper print: price −5.5%, TR +50%.",
        ),
        (
            "US3161841008",
            "2018-05-11",
            "forward",
            "Distribution $0.507. Raw Lipper print: price −4.5%, TR +39%.",
        ),
        (
            "US78472P1093",
            "2019-12-20",
            "forward",
            "S&P 500 index fund. Raw Lipper print: price −4.1%, TR +24% "
            "(S&P +0.5%).",
        ),
        (
            "US85749T7569",
            "2019-12-20",
            "forward",
            "S&P 500 index portfolio. Raw Lipper print: price −1.8%, TR +45% "
            "(S&P +0.5%).",
        ),
        (
            "US38141W6205",
            "2021-12-14",
            "forward",
            "Partial distribution add-back. Raw Lipper print: price −22%, "
            "TR −14%.",
        ),
        (
            "US38141W6205",
            "2024-12-12",
            "forward",
            "Partial distribution add-back. Raw Lipper print: price −14%, "
            "TR −12%.",
        ),
        (
            "US63872T4893",
            "2021-12-23",
            "forward",
            "Raw Lipper print: price −27%, TR −13% (S&P +0.6%).",
        ),
        (
            "US92646A2520",
            "2024-12-13",
            "one-day",
            "S&P 500 index fund. Capital-gain distribution $4.094 "
            "(≈15.57% of NAV), ex-date 2024-12-13 / pay date 2024-12-16 "
            "(Victory 2024 distribution notice). Raw print: ex-date TR +15.57% "
            "with flat price; pay-date price and TR both ≈ −13%.",
        ),
        (
            "US0263933063",
            "2025-12-01",
            "one-day",
            "Raw print: TR +14.6% with price −0.77%; reverses the next day "
            "while later levels stay correct.",
        ),
    ]
    # Retention evidence only (genuine moves). Panel-absent ISINs are omitted.
    kept_spikes = [
        (
            "US46090A7054",
            "2020-03-16",
            "Price and TR both rise 11.5% while the S&P falls 12% "
            "(hedge payoff).",
        ),
        (
            "US00777X6452",
            "2020-03-18",
            "Price and TR both fall 10.9% in the March 2020 crash; "
            "no next-day reversal.",
        ),
        (
            "US62827L4923",
            "2026-02-02",
            "Price and TR both rise ≈12% after a 9% fall; the new level stays.",
        ),
        (
            "US15136Y4070",
            "2018-01-02",
            "Price and TR both rise ≈14.5%; the new level stays.",
        ),
        (
            "US77926Y8232",
            "2026-10-22",
            "Price and TR both fall ≈10% against an S&P decline of 1.2%.",
        ),
        (
            "US77926Y8232",
            "2026-10-30",
            "Price and TR both fall ≈12% against an S&P decline of 1.8%; "
            "last observation in the file.",
        ),
    ]

    repaired = observations.copy()
    if market_id is None:
        raise ValueError("Spike repair requires an S&P 500 TR % column")
    market = repaired[market_id]
    rows: list[dict[str, Any]] = []

    def day_position(day: str) -> int | None:
        matches = repaired.index.get_indexer([pd.Timestamp(day)])
        if int(matches[0]) < 0:
            return None
        return int(matches[0])

    for isin, day, mode, defect in repairs:
        level_id = column_id(f"{isin} TR")
        return_id = column_id(f"{isin} TR %")
        price_return_id = column_id(f"{isin} Price %")
        position = day_position(day)
        if (
            level_id is None
            or return_id is None
            or price_return_id is None
            or position is None
            or position <= 0
        ):
            continue
        levels = repaired[level_id].to_numpy(dtype="float64", copy=True)
        returns = repaired[return_id].to_numpy(dtype="float64", copy=True)
        original_levels = levels.copy()
        original_returns = returns.copy()
        previous = levels[position - 1]
        current = levels[position]
        tr_return = float(original_returns[position])
        price_return = float(repaired[price_return_id].iloc[position])
        market_return = float(market.iloc[position])
        if not still_defective(tr_return, price_return, market_return):
            rows.append(
                log_row(
                    isin=isin,
                    day=day,
                    decision="skipped — already clean",
                    adjustment="left unchanged (TR≈market or Price≈TR)",
                    mode=mode,
                    defect=defect,
                    return_before=tr_return,
                    return_after=tr_return,
                    price_return=price_return,
                    market_return=market_return,
                )
            )
            continue
        target = float(market_return if mode == "forward" else price_return)
        if (
            previous == previous
            and current == current
            and previous != 0
            and abs(current / previous - 1.0 - target) <= 1e-8
        ):
            next_return = (
                float(original_returns[position + 1])
                if position + 1 < len(original_returns)
                else None
            )
            rows.append(
                log_row(
                    isin=isin,
                    day=day,
                    decision="repaired",
                    adjustment="already matches",
                    mode=mode,
                    defect=defect,
                    return_before=float(original_returns[position]),
                    return_after=float(original_returns[position]),
                    price_return=price_return,
                    market_return=market_return,
                    next_return_before=next_return,
                    next_return_after=next_return,
                )
            )
            continue
        if mode == "forward":
            levels[position:] *= (previous * (1.0 + target)) / levels[position]
            returns[position] = levels[position] / previous - 1.0
            adjustment = "total return set to the S&P return; later levels rescaled"
        else:
            levels[position] = previous * (1.0 + target)
            returns[position] = target
            following = position + 1
            if (
                following < len(levels)
                and levels[following] == levels[following]
                and levels[position] != 0
            ):
                returns[following] = levels[following] / levels[position] - 1.0
            adjustment = (
                "spike-day level replaced with the price return; "
                "next return recomputed"
            )
        repaired[level_id] = levels
        repaired[return_id] = returns
        next_before = (
            float(original_returns[position + 1])
            if position + 1 < len(original_returns)
            else None
        )
        next_after = (
            float(returns[position + 1])
            if position + 1 < len(returns)
            else None
        )
        rows.append(
            log_row(
                isin=isin,
                day=day,
                decision="repaired",
                adjustment=adjustment,
                mode=mode,
                defect=defect,
                return_before=float(original_returns[position]),
                return_after=float(returns[position]),
                price_return=price_return,
                market_return=market_return,
                next_return_before=next_before,
                next_return_after=next_after,
                cells=changed_cells(original_levels, levels, 1e-8)
                + changed_cells(original_returns, returns, 1e-12),
            )
        )
    for isin, day, evidence in kept_spikes:
        return_id = column_id(f"{isin} TR %")
        price_return_id = column_id(f"{isin} Price %")
        position = day_position(day)
        if return_id is None or position is None:
            continue
        stored = float(repaired[return_id].iloc[position])
        price_return = (
            float(repaired[price_return_id].iloc[position])
            if price_return_id is not None
            else float("nan")
        )
        market_return = float(market.iloc[position])
        rows.append(
            log_row(
                isin=isin,
                day=day,
                decision="kept",
                adjustment="left unchanged",
                mode=None,
                defect=evidence,
                return_before=stored,
                return_after=stored,
                price_return=price_return,
                market_return=market_return,
            )
        )
    distribution_log = pd.DataFrame(rows)
    return repaired, distribution_log