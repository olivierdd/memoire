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


def summarize_tr_consistency(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    flags: Iterable[str] | None = None,
    exchange_holidays: pd.DatetimeIndex | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, dict[int, Any]]:
    """Score each fund TR % series vs S&P 500 TR %; return controls, summary, checks.

    Pass ``flags`` to compute only the named checks (and prerequisites). ``None``
    runs every check. Unrequested flag columns stay at zero / False in the summary.
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


def rescale_level_breaks(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Detect lasting level breaks and apply hardcoded corporate-action rescales."""

    def lasting_breaks(source: pd.DataFrame, catalog_frame: pd.DataFrame) -> tuple[list[dict], pd.Series]:
        is_return = catalog_frame["note"].astype("string").str.startswith("Daily simple return")
        index_id = int(
            catalog_frame.loc[is_return & catalog_frame["header"].eq("S&P 500 TR %"), "column"].iloc[0]
        )
        market_return = source[index_id]
        found: list[dict[str, Any]] = []
        for return_row in catalog_frame.loc[is_return].itertuples(index=False):
            header = str(return_row.header)
            if header.endswith("Price %"):
                side = "Price"
            elif header.endswith("TR %"):
                side = "TR"
            else:
                continue
            returns = source[int(return_row.column)]
            gap = (returns - market_return).abs()
            candidates = returns.index[
                returns.notna()
                & market_return.notna()
                & returns.abs().ge(0.50)
                & gap.ge(0.25)
            ]
            values = returns.to_numpy(dtype="float64")
            for day in candidates:
                position = source.index.get_loc(day)
                follow = [value for value in values[position : position + 4] if value == value]
                if len(follow) < 2:
                    continue
                stayed = 1.0
                for value in follow:
                    stayed *= 1.0 + value
                stayed -= 1.0
                jump = float(values[position])
                if abs(stayed) < abs(jump) / 2:
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
    # surface as Detector B "not adjusted" rows instead.
    level_actions = [
        {
            "isin": "US1888501012",
            "date": "2025-05-12",
            "sides": ("Price", "TR"),
            "mode": "history",
            "factor": 1 / 100,
            "why": (
                "Clipper Fund (CFIMX): 10-for-1 split effective 12 May 2025. "
                "The 9 May print is 1,394.60, exactly 10× the fund's published "
                "$139.46, so history is divided by 10² = 100."
            ),
        },
    ]
    kept_distributions = [
        {
            "isin": "US00791R7807",
            "date": "2025-12-18",
            "sides": ("Price",),
            "why": (
                "Vontobel US Equity (VNUYX): long-term capital gain of "
                "$15.1441 on 18 Dec 2025. The price falls from 18.75 to 3.76 "
                "and the total return stays near 246, so the price is the "
                "ex-distribution NAV and is not rescaled."
            ),
        },
        {
            "isin": "US3624014086",
            "date": "2026-10-28",
            "sides": ("Price",),
            "why": (
                "Gabelli SRI (SRIDX): the price falls from 14.51 to 6.10 and "
                "stays there. That level matches the fund's published NAV, "
                "and the 25 Apr 2025 price matches the published $12.92. The "
                "total return does not fall. Liquidation was announced on "
                "14 Oct 2026."
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

    breaks, market_return = lasting_breaks(observations, catalog)
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


def repair_distribution_day_tr(
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Repair documented distribution-day total-return spikes.

    Each curated day is rewritten only when both gates hold on the current
    panel: ``|TR% − Price%|`` and ``|TR% − S&P 500 TR %|`` are at least
    ``DISTRIBUTION_REPAIR_MIN_*`` (1% by default). Otherwise the day is logged
    as ``skipped — already clean`` and left unchanged.
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

    market_id = column_id("S&P 500 TR %")
    repairs = [
        ("US3161841008", "2015-12-04", "forward", "Distributions of $0.392. The price falls 2.1% and the total return jumps +36%. The repaired return is the S&P return."),
        ("US3161841008", "2016-12-02", "forward", "Distributions of $0.186. The price falls 2.1% and the total return jumps +18%."),
        ("US3161841008", "2017-05-12", "forward", "Distributions of $0.555. The price falls 5.5% and the total return jumps +50%."),
        ("US3161841008", "2018-05-11", "forward", "Distributions of $0.507. The price falls 4.5% and the total return jumps +39%."),
        ("US78472P1093", "2019-12-20", "forward", "S&P index fund. The price falls 4.1% and the total return jumps +24% on a day the S&P rose 0.5%."),
        ("US85749T7569", "2019-12-20", "forward", "S&P index portfolio. The price falls 1.8% and the total return jumps +45% on a day the S&P rose 0.5%."),
        ("US38141W6205", "2021-12-14", "forward", "The price falls 22% and the total return only 14%, so the distribution was partly omitted. The day's total return is set to the S&P return."),
        ("US38141W6205", "2024-12-12", "forward", "The price falls 14% and the total return 12%. Same partial distribution add-back."),
        ("US63872T4893", "2021-12-23", "forward", "The price falls 27% and the total return 13% while the S&P rose 0.6%."),
        ("US0263933063", "2025-12-01", "one-day", "The total return jumps +14.6% and reverses the next day. The price does not jump. Only that total-return print is replaced."),
    ]
    # Only ISINs still on the working panel. Panel-absent funds (e.g. former
    # US66538H5919) are omitted rather than silently skipped at runtime.
    kept_spikes = [
        ("US46090A7054", "2020-03-16", "Price and total return both rise 11.5% while the S&P falls 12%. The hedge paid off."),
        ("US00777X6452", "2020-03-18", "Price and total return both fall 10.9% in the March 2020 crash. The next day does not restore a different path."),
        ("US62827L4923", "2026-02-02", "Price and total return both rise 12% after a 9% drop, and the new level stays."),
        ("US15136Y4070", "2018-01-02", "Price and total return both rise 14.5%, and the new level stays."),
        ("US77926Y8232", "2026-10-22", "Price and total return both fall 10% against an S&P decline of 1.2%."),
        ("US77926Y8232", "2026-10-30", "Price and total return both fall 12% against an S&P decline of 1.8%. This is the last print in the file."),
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

    for isin, day, mode, why in repairs:
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
                {
                    "isin": isin,
                    "fund": fund_label(isin),
                    "date": day,
                    "decision": "skipped — already clean",
                    "adjustment": "left unchanged (TR≈market or Price≈TR)",
                    "return_before": tr_return,
                    "return_after": tr_return,
                    "next_return_before": None,
                    "next_return_after": None,
                    "cells": 0,
                    "why": why,
                }
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
                {
                    "isin": isin,
                    "fund": fund_label(isin),
                    "date": day,
                    "decision": "repaired",
                    "adjustment": "already matches",
                    "return_before": float(original_returns[position]),
                    "return_after": float(original_returns[position]),
                    "next_return_before": next_return,
                    "next_return_after": next_return,
                    "cells": 0,
                    "why": why,
                }
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
            adjustment = "spike-day level replaced with the price return; next return recomputed"
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
            {
                "isin": isin,
                "fund": fund_label(isin),
                "date": day,
                "decision": "repaired",
                "adjustment": adjustment,
                "return_before": float(original_returns[position]),
                "return_after": float(returns[position]),
                "next_return_before": next_before,
                "next_return_after": next_after,
                "cells": changed_cells(original_levels, levels, 1e-8)
                + changed_cells(original_returns, returns, 1e-12),
                "why": why,
            }
        )
    for isin, day, why in kept_spikes:
        return_id = column_id(f"{isin} TR %")
        position = day_position(day)
        if return_id is None or position is None:
            continue
        stored = float(repaired[return_id].iloc[position])
        rows.append(
            {
                "isin": isin,
                "fund": fund_label(isin),
                "date": day,
                "decision": "kept",
                "adjustment": "left unchanged",
                "return_before": stored,
                "return_after": stored,
                "next_return_before": None,
                "next_return_after": None,
                "cells": 0,
                "why": why,
            }
        )
    distribution_log = pd.DataFrame(rows)
    return repaired, distribution_log