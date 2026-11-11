"""Why a fund's compounded total return differs from Lipper's published performance."""

from __future__ import annotations

import numpy as np
import pandas as pd

from helpers.timeseries_functions.regress_daily_to_benchmark import (
    DEFAULT_HORIZON_MONTHS,
    SPX_BENCH_HEADER,
    _parse_lipper_number,
    horizon_total_return_pct,
)

# A stored daily return that differs from the level change by more than this
# (1 bp) is a break between the return column and the total-return index.
RETURN_LEVEL_BREAK = 1e-4
# Log-excess versus the S&P, summed over Decembers.
QUIET_DECEMBER_LOG = 0.01
LARGE_DECEMBER_LOG = 0.02


def horizon_anchors(daily: pd.DataFrame) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """Last S&P 500 TR print on or before each anniversary, and the series end."""
    level = pd.to_numeric(daily["S&P 500 TR"], errors="coerce").dropna()
    if level.empty:
        return {}
    end = level.index[-1]
    anchors: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for horizon, months in DEFAULT_HORIZON_MONTHS.items():
        years = months // 12
        cut = end - pd.DateOffset(years=years)
        start = level.loc[level.index <= cut]
        if start.empty:
            continue
        anchors[horizon] = (start.index[-1], end)
    return anchors


def total_return_level_identity(
    daily: pd.DataFrame,
    isins: pd.Series | list[str],
) -> pd.DataFrame:
    """Compounded daily return against the change in the total-return level.

    A difference here would mean the return column and the level column disagree,
    or that sessions are missing. Lipper is not involved.
    """
    anchors = horizon_anchors(daily)
    index_return = pd.to_numeric(daily[SPX_BENCH_HEADER], errors="coerce")
    rows: list[dict] = []
    for raw_isin in isins:
        isin = str(raw_isin).strip()
        level_col = f"{isin} TR"
        return_col = f"{isin} TR %"
        if level_col not in daily.columns or return_col not in daily.columns:
            continue
        level = pd.to_numeric(daily[level_col], errors="coerce")
        returns = pd.to_numeric(daily[return_col], errors="coerce")
        implied = level.pct_change()
        for horizon, (start, end) in anchors.items():
            in_window = (daily.index > start) & (daily.index <= end)
            window_returns = returns.loc[in_window].dropna()
            compound = (
                horizon_total_return_pct(window_returns.to_numpy(dtype=float))
                if len(window_returns)
                else float("nan")
            )
            start_level = level.get(start, np.nan)
            end_level = level.get(end, np.nan)
            if pd.notna(start_level) and pd.notna(end_level) and start_level != 0:
                level_pct = float((end_level / start_level - 1.0) * 100.0)
            else:
                level_pct = float("nan")
            index_in_window = index_return.loc[in_window]
            fund_in_window = returns.loc[in_window]
            n_missing = int((index_in_window.notna() & fund_in_window.isna()).sum())
            breaks = (returns - implied).abs().loc[in_window]
            n_breaks = int((breaks > RETURN_LEVEL_BREAK).sum())
            rows.append(
                {
                    "isin": isin,
                    "horizon": horizon,
                    "level_pct": level_pct,
                    "compound_pct": compound,
                    "abs_diff_pp": (
                        abs(compound - level_pct)
                        if pd.notna(compound) and pd.notna(level_pct)
                        else float("nan")
                    ),
                    "n_missing": n_missing,
                    "n_breaks": n_breaks,
                }
            )
    return pd.DataFrame(rows)


def _parsed_expense(funds: pd.DataFrame) -> pd.Series:
    if "Total Expense Ratio" not in funds.columns or "ISIN" not in funds.columns:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(
        {
            "isin": funds["ISIN"].astype(str).str.strip(),
            "expense": funds["Total Expense Ratio"].map(_parse_lipper_number),
        }
    )
    return frame.drop_duplicates("isin").set_index("isin")["expense"]


def return_gap_attribution(
    monthly: pd.DataFrame,
    comparable: pd.DataFrame,
    funds: pd.DataFrame | None = None,
    *,
    index_header: str = SPX_BENCH_HEADER,
) -> pd.DataFrame:
    """Split each fund's active return into Decembers and the other months.

    ``comparable`` is the full-window total-return comparison. December is where
    a missed distribution shows up as a lag versus the S&P.
    """
    if index_header not in monthly.columns:
        raise KeyError(f"Monthly panel has no {index_header!r} column")
    expense = _parsed_expense(funds) if funds is not None else pd.Series(dtype=float)
    rows: list[dict] = []
    for record in comparable.itertuples(index=False):
        start = getattr(record, "window_start", None)
        end = getattr(record, "window_end", None)
        if start is None or end is None or (isinstance(start, float) and np.isnan(start)):
            continue
        fund_col = f"{record.isin} TR %"
        if fund_col not in monthly.columns:
            continue
        window = monthly.loc[str(start) : str(end), [fund_col, index_header]]
        aligned = window.rename(columns={fund_col: "fund", index_header: "index"}).dropna()
        if aligned.empty:
            continue
        log_excess = np.log1p(aligned["fund"]) - np.log1p(aligned["index"])
        finite = np.isfinite(log_excess)
        log_excess = log_excess.loc[finite]
        aligned = aligned.loc[finite]
        december = aligned.index.month == 12
        active = aligned["fund"] - aligned["index"]
        worst_at = active.abs().idxmax()
        rows.append(
            {
                "isin": record.isin,
                "name": record.name,
                "horizon": record.horizon,
                "gap_pp": record.delta_total_return_pct,
                "expense": expense.get(str(record.isin).strip(), np.nan),
                "december_log_excess": float(log_excess.loc[december].sum()) if december.any() else 0.0,
                "other_log_excess": float(log_excess.loc[~december].sum()),
                "worst_month": str(worst_at),
                "worst_active": float(active.loc[worst_at]),
                "worst_is_december": bool(getattr(worst_at, "month", None) == 12 or str(worst_at).endswith("-12")),
            }
        )
    return pd.DataFrame(rows)


def _correlation(left: pd.Series, right: pd.Series) -> float:
    pair = pd.concat([left, right], axis=1).dropna()
    if len(pair) < 3:
        return float("nan")
    return float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))


def return_gap_cause_summary(
    attribution: pd.DataFrame,
    *,
    quiet_log: float = QUIET_DECEMBER_LOG,
    large_log: float = LARGE_DECEMBER_LOG,
) -> pd.DataFrame:
    """One row per horizon: how the Lipper gap lines up with December."""
    rows: list[dict] = []
    if attribution.empty:
        return pd.DataFrame(rows)
    for horizon in DEFAULT_HORIZON_MONTHS:
        part = attribution.loc[attribution["horizon"].eq(horizon)]
        if part.empty:
            continue
        quiet = part.loc[part["december_log_excess"].abs() < quiet_log, "gap_pp"]
        large = part.loc[part["december_log_excess"] < -large_log, "gap_pp"]
        corr_dec = _correlation(part["gap_pp"], part["december_log_excess"])
        rows.append(
            {
                "horizon": horizon,
                "funds": int(len(part)),
                "corr_gap_december": corr_dec,
                "r_squared_december": (
                    float(corr_dec**2) if pd.notna(corr_dec) else float("nan")
                ),
                "median_gap_quiet_december": float(quiet.median()) if len(quiet) else float("nan"),
                "n_quiet_december": int(len(quiet)),
                "median_gap_large_december": float(large.median()) if len(large) else float("nan"),
                "n_large_december": int(len(large)),
                "corr_gap_expense": _correlation(part["gap_pp"], part["expense"]),
                "median_december_log_excess": float(part["december_log_excess"].median()),
                "median_other_log_excess": float(part["other_log_excess"].median()),
            }
        )
    return pd.DataFrame(rows)
