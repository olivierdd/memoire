"""Rebuild fund total-return percent from Datastream NAV and cash distributions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf
from curl_cffi.requests.exceptions import HTTPError
from yfinance.exceptions import YFException, YFRateLimitError

from helpers.funds_functions.map_yahoo_static import (
    MAX_ATTEMPTS,
    PAUSE_SECONDS,
    RATE_LIMIT_SLEEP_SECONDS,
    _code_root,
)
from helpers.timeseries_functions.regress_daily_to_benchmark import (
    DEFAULT_HORIZON_MONTHS,
    LIPPER_AS_OF,
    _lipper_metric,
    _lipper_performance_column,
    compound_daily_to_monthly,
    horizon_total_return_pct,
)

DEFAULT_DISTRIBUTIONS_CACHE = Path("cache") / "yahoo-distributions.json"
DEFAULT_FMP_CACHE = Path("cache") / "cache-financedatabase.json"
LIPPER_CLOSE_PP = 0.5
# Longest available horizon wins; fall back when history / Lipper is missing.
LIPPER_TEST_HORIZONS: tuple[str, ...] = ("10y", "5y", "3y")
SESSION_ALIGN_MAX_DAYS = 4
INDEX_NAME_PATTERN = r"S&P 500|500 Index|Index Fund"


def _resolve_fmp_cache_path(cache_path: Path | None = None) -> Path:
    relative = DEFAULT_FMP_CACHE if cache_path is None else Path(cache_path)
    if relative.is_absolute():
        return relative.resolve()
    return (_code_root() / relative).resolve()

__all__ = [
    "DEFAULT_DISTRIBUTIONS_CACHE",
    "LIPPER_CLOSE_PP",
    "LIPPER_TEST_HORIZONS",
    "RebuildFundResult",
    "align_events_to_sessions",
    "cash_events_from_fmp",
    "detect_missed_distribution_days",
    "fetch_yahoo_cash_events",
    "horizon_gaps_vs_lipper",
    "lipper_gate_should_adopt",
    "lipper_gate_should_adopt_only_if_pass",
    "lipper_test_status",
    "load_distributions_cache",
    "primary_lipper_horizon",
    "rebuild_fund_tr",
    "rebuild_tr_panel",
    "recompute_tr_level",
    "resolve_distributions_cache_path",
    "save_distributions_cache",
    "summarize_rebuild_gate_transparency",
    "total_return_percent_from_price",
]


def resolve_distributions_cache_path(cache_path: Path | None = None) -> Path:
    relative = DEFAULT_DISTRIBUTIONS_CACHE if cache_path is None else Path(cache_path)
    if relative.is_absolute():
        return relative.resolve()
    return (_code_root() / relative).resolve()


def load_distributions_cache(cache_path: Path | None = None) -> dict[str, Any]:
    path = resolve_distributions_cache_path(cache_path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def save_distributions_cache(cache: dict[str, Any], cache_path: Path | None = None) -> Path:
    path = resolve_distributions_cache_path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True))
    return path


def fetch_yahoo_cash_events(
    ticker: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    cache: dict[str, Any] | None = None,
    cache_path: Path | None = None,
    pause_seconds: float = PAUSE_SECONDS,
) -> pd.DataFrame:
    """Daily close and cash distributions (not adj close). Uses an optional JSON cache."""
    key = str(ticker).strip().upper()
    working = cache if cache is not None else load_distributions_cache(cache_path)
    cached = working.get(key)
    if isinstance(cached, dict) and cached.get("events") is not None:
        events = cached["events"]
        index = pd.to_datetime([row["date"] for row in events])
        frame = pd.DataFrame(events, index=index)
        return frame.loc[(index >= start.normalize()) & (index <= end.normalize())]

    for attempt in range(MAX_ATTEMPTS):
        try:
            history = yf.Ticker(key).history(
                start=start - pd.Timedelta(days=5),
                end=end + pd.Timedelta(days=5),
                interval="1d",
                auto_adjust=False,
                repair=False,
            )
            break
        except YFRateLimitError:
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)
        except HTTPError as error:
            status = getattr(error.response, "status_code", None)
            if status == 429:
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            history = pd.DataFrame()
            break
        except YFException:
            history = pd.DataFrame()
            break
    else:
        history = pd.DataFrame()

    if history.empty:
        working[key] = {"events": [], "source": "yahoo"}
        save_distributions_cache(working, cache_path)
        return pd.DataFrame(columns=["Close", "Dividends", "Capital Gains", "distribution"])

    history.index = history.index.tz_localize(None).normalize()
    dividends = history["Dividends"].fillna(0.0) if "Dividends" in history.columns else 0.0
    capital = (
        history["Capital Gains"].fillna(0.0) if "Capital Gains" in history.columns else 0.0
    )
    distribution = dividends + capital
    frame = pd.DataFrame(
        {
            "Close": history["Close"].astype(float),
            "Dividends": dividends,
            "Capital Gains": capital,
            "distribution": distribution.astype(float),
        }
    )
    events = []
    for stamp, row in frame.iterrows():
        if float(row["distribution"]) == 0.0 and pd.isna(row["Close"]):
            continue
        events.append(
            {
                "date": stamp.date().isoformat(),
                "Close": None if pd.isna(row["Close"]) else float(row["Close"]),
                "Dividends": float(row["Dividends"]),
                "Capital Gains": float(row["Capital Gains"]),
                "distribution": float(row["distribution"]),
            }
        )
    working[key] = {"events": events, "source": "yahoo"}
    save_distributions_cache(working, cache_path)
    time.sleep(pause_seconds)
    return frame.loc[(frame.index >= start.normalize()) & (frame.index <= end.normalize())]


def cash_events_from_fmp(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    fmp_cache: dict[str, Any] | None = None,
) -> pd.Series:
    """Per-session distribution from the on-disk FMP dividend cache (JSON only)."""
    if fmp_cache is None:
        path = _resolve_fmp_cache_path()
        if not path.is_file():
            return pd.Series(dtype=float)
        cache = json.loads(path.read_text())
    else:
        cache = fmp_cache
    row = cache.get(str(symbol).strip().upper()) or cache.get(str(symbol))
    if not isinstance(row, dict):
        return pd.Series(dtype=float)
    fmp = row.get("fmp")
    if not isinstance(fmp, dict):
        return pd.Series(dtype=float)
    dividends = fmp.get("dividends") or []
    amounts: dict[pd.Timestamp, float] = {}
    for item in dividends:
        if not isinstance(item, dict):
            continue
        day = item.get("date") or item.get("paymentDate") or item.get("recordDate")
        if not day:
            continue
        stamp = pd.Timestamp(day).normalize()
        if stamp < start or stamp > end:
            continue
        amount = item.get("dividend")
        if amount is None:
            amount = item.get("adjDividend")
        if amount is None:
            continue
        amounts[stamp] = amounts.get(stamp, 0.0) + float(amount)
    if not amounts:
        return pd.Series(dtype=float)
    return pd.Series(amounts, dtype=float).sort_index()


def align_events_to_sessions(
    session_dates: pd.DatetimeIndex,
    event_amounts: pd.Series,
) -> pd.Series:
    """Map ex-dates onto the next available observation session (up to a few days)."""
    aligned = pd.Series(0.0, index=session_dates, dtype=float)
    if event_amounts.empty:
        return aligned
    sessions = pd.DatetimeIndex(session_dates).sort_values()
    for ex_date, amount in event_amounts.items():
        if not amount or pd.isna(amount):
            continue
        ex_date = pd.Timestamp(ex_date).normalize()
        future = sessions[sessions >= ex_date]
        if future.empty:
            continue
        target = future[0]
        if (target - ex_date).days > SESSION_ALIGN_MAX_DAYS:
            continue
        if target in aligned.index:
            aligned.loc[target] = float(aligned.loc[target]) + float(amount)
    return aligned


def total_return_percent_from_price(
    price: pd.Series,
    distributions: pd.Series,
) -> pd.Series:
    """Daily simple return with cash reinvested on ex-dates."""
    price = price.astype(float)
    prior = price.shift(1)
    payout = distributions.reindex(price.index).fillna(0.0)
    numer = price + payout
    returns = numer / prior - 1.0
    returns.iloc[0] = np.nan
    return returns


def recompute_tr_level(
    returns: pd.Series,
    *,
    anchor_level: float,
    anchor_index: pd.Timestamp,
) -> pd.Series:
    """Compound ``returns`` forward from ``anchor_level`` at ``anchor_index``."""
    levels = pd.Series(np.nan, index=returns.index, dtype=float)
    if anchor_index not in returns.index:
        return levels
    position = returns.index.get_loc(anchor_index)
    levels.iloc[position] = anchor_level
    prev = anchor_level
    for idx in range(position + 1, len(returns)):
        value = returns.iloc[idx]
        if not np.isfinite(value):
            continue
        prev = prev * (1.0 + float(value))
        levels.iloc[idx] = prev
    return levels


def detect_missed_distribution_days(
    price_return: pd.Series,
    tr_return: pd.Series,
    spx_return: pd.Series,
    *,
    min_price_drop: float = 0.01,
    max_spx_move: float = 0.005,
) -> pd.DatetimeIndex:
    """Days where price and TR both fell, but the S&P did not (typical missed payout)."""
    aligned = pd.concat(
        [
            price_return.rename("price"),
            tr_return.rename("tr"),
            spx_return.rename("spx"),
        ],
        axis=1,
    ).dropna()
    if aligned.empty:
        return pd.DatetimeIndex([])
    miss = (
        (aligned["price"] <= -min_price_drop)
        & (aligned["tr"] <= -min_price_drop)
        & ((aligned["tr"] - aligned["price"]).abs() < min_price_drop)
        & (aligned["spx"].abs() < max_spx_move)
    )
    return pd.DatetimeIndex(aligned.index[miss])


def _index_like_fund(fund_row: pd.Series | None) -> bool:
    if fund_row is None:
        return False
    if bool(fund_row.get("is_index_or_idx")):
        return True
    name = str(fund_row.get("Name", ""))
    if pd.notna(name) and pd.Series([name]).str.contains(INDEX_NAME_PATTERN, regex=True).iloc[0]:
        return True
    ticker = str(fund_row.get("Benchmark Ticker", "")).strip()
    fund_type = str(fund_row.get("fund_type", "")).strip().lower()
    return ticker == ".SPXTR" and fund_type == "passive"


def _monthly_tr_return(
    daily_returns: pd.Series,
    bench_counts: pd.Series,
) -> pd.Series:
    frame = pd.DataFrame({"fund": daily_returns})
    monthly = compound_daily_to_monthly(frame, bench_counts)
    return monthly["fund"]


def horizon_gaps_vs_lipper(
    daily_tr_pct: pd.Series,
    fund_row: pd.Series,
    bench_counts: pd.Series,
) -> dict[str, float]:
    """Computed minus Lipper cumulative total return (pp) for 3y/5y/10y."""
    clipped = daily_tr_pct.loc[daily_tr_pct.index <= LIPPER_AS_OF]
    monthly = _monthly_tr_return(clipped, bench_counts)
    gaps: dict[str, float] = {}
    for horizon, months in DEFAULT_HORIZON_MONTHS.items():
        years = int(horizon.replace("y", ""))
        lipper = _lipper_metric(fund_row, years, _lipper_performance_column(years))
        if pd.isna(lipper) or len(monthly) < months:
            gaps[horizon] = float("nan")
            continue
        window = monthly.iloc[-months:]
        computed = horizon_total_return_pct(window.to_numpy(dtype=float))
        gaps[horizon] = computed - float(lipper)
    return gaps


def primary_lipper_horizon(gaps: dict[str, float]) -> str | None:
    """Longest horizon with a finite Lipper gap (10y → 5y → 3y)."""
    for horizon in LIPPER_TEST_HORIZONS:
        if pd.notna(gaps.get(horizon)):
            return horizon
    return None


def lipper_test_status(
    gaps: dict[str, float],
    *,
    close_pp: float = LIPPER_CLOSE_PP,
) -> tuple[str, str | None]:
    """Pass/fail/unscored on the longest available horizon.

    Returns ``(status, horizon)`` where status is ``pass``, ``fail``, or
    ``unscored``. Falls back 10y → 5y → 3y when a longer gap is missing.
    """
    horizon = primary_lipper_horizon(gaps)
    if horizon is None:
        return "unscored", None
    if abs(float(gaps[horizon])) <= close_pp:
        return "pass", horizon
    return "fail", horizon


def lipper_gate_should_adopt(
    gap_before: dict[str, float],
    gap_after: dict[str, float],
    *,
    close_pp: float = LIPPER_CLOSE_PP,
) -> bool:
    """Adopt rebuilt TR when the primary Lipper gap is close or improves.

    Primary horizon is the longest available on the rebuild side (10y → 5y →
    3y). If that gap is already within ``close_pp``, adopt. Otherwise compare
    shared horizons from longest to shortest: adopt on improvement; on a tie,
    try the next shorter horizon; on a worse gap, keep Datastream.
    """
    primary_after = primary_lipper_horizon(gap_after)
    if primary_after is not None and abs(float(gap_after[primary_after])) <= close_pp:
        return True

    for horizon in LIPPER_TEST_HORIZONS:
        before = gap_before.get(horizon)
        after = gap_after.get(horizon)
        if not (pd.notna(before) and pd.notna(after)):
            continue
        before_abs = abs(float(before))
        after_abs = abs(float(after))
        if after_abs < before_abs - 1e-12:
            return True
        if after_abs > before_abs + 1e-12:
            return False
        # Equal on this horizon → try a shorter horizon as tie-break.
    return False


def lipper_gate_should_adopt_only_if_pass(
    gap_before: dict[str, float],
    gap_after: dict[str, float],
    *,
    close_pp: float = LIPPER_CLOSE_PP,
) -> bool:
    """Stricter counterfactual gate: adopt only when the rebuild already passes.

    Unlike ``lipper_gate_should_adopt``, improvement that remains outside
    ``close_pp`` does **not** trigger adoption. ``gap_before`` is unused and
    kept only so callers can swap gate functions with a matching signature.
    """
    del gap_before  # Signature parity with ``lipper_gate_should_adopt``.
    status, _ = lipper_test_status(gap_after, close_pp=close_pp)
    return status == "pass"


def _gaps_from_rebuild_log_row(row: pd.Series, *, side: str) -> dict[str, float]:
    return {
        horizon: row.get(f"gap_{horizon}_{side}")
        for horizon in LIPPER_TEST_HORIZONS
    }


def summarize_rebuild_gate_transparency(
    rebuild_log: pd.DataFrame,
    *,
    close_pp: float = LIPPER_CLOSE_PP,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Post-adopt Lipper status and adopt-only-if-pass sensitivity.

    Production decisions stay those already recorded in ``rebuild_log``
    (``decision`` = ``adopted`` / ``kept_legacy``). This helper does not change
    which series were written; it reports:

    - among production adopts, how many rebuild candidates still fail Lipper;
    - how many funds the stricter adopt-only-if-pass rule would have adopted;
    - which production adopts the stricter rule would have refused.

    Returns ``(summary, adopted_still_fail_table)``.
    """
    empty_fail = pd.DataFrame(
        columns=[
            "isin",
            "ticker",
            "decision",
            "rebuild_vs_lipper",
            "rebuild_lipper_horizon",
            "gap_primary_after_pp",
            "strict_would_adopt",
        ]
    )
    if rebuild_log is None or len(rebuild_log) == 0:
        summary = {
            "n_funds": 0,
            "n_adopted": 0,
            "n_kept_legacy": 0,
            "adopted_pass": 0,
            "adopted_fail": 0,
            "adopted_unscored": 0,
            "strict_would_adopt": 0,
            "strict_would_keep": 0,
            "adopted_under_both": 0,
            "adopted_only_under_production": 0,
            "close_pp": float(close_pp),
        }
        return summary, empty_fail

    rows: list[dict[str, Any]] = []
    for row in rebuild_log.itertuples(index=False):
        series = pd.Series(row._asdict())
        gap_before = _gaps_from_rebuild_log_row(series, side="before")
        gap_after = _gaps_from_rebuild_log_row(series, side="after")
        rebuild_status, rebuild_horizon = lipper_test_status(
            gap_after, close_pp=close_pp
        )
        production_adopted = str(series.get("decision", "")).strip() == "adopted"
        strict_adopt = lipper_gate_should_adopt_only_if_pass(
            gap_before, gap_after, close_pp=close_pp
        )
        primary_gap = (
            float(gap_after[rebuild_horizon])
            if rebuild_horizon is not None and pd.notna(gap_after.get(rebuild_horizon))
            else float("nan")
        )
        rows.append(
            {
                "isin": series.get("isin"),
                "ticker": series.get("ticker"),
                "decision": series.get("decision"),
                "production_adopted": production_adopted,
                "rebuild_vs_lipper": rebuild_status,
                "rebuild_lipper_horizon": rebuild_horizon,
                "gap_primary_after_pp": primary_gap,
                "strict_would_adopt": strict_adopt,
            }
        )

    detail = pd.DataFrame(rows)
    adopted = detail.loc[detail["production_adopted"]]
    adopted_pass = int((adopted["rebuild_vs_lipper"] == "pass").sum())
    adopted_fail = int((adopted["rebuild_vs_lipper"] == "fail").sum())
    adopted_unscored = int((adopted["rebuild_vs_lipper"] == "unscored").sum())
    strict_would_adopt = int(detail["strict_would_adopt"].sum())
    adopted_under_both = int(
        (detail["production_adopted"] & detail["strict_would_adopt"]).sum()
    )
    adopted_only_under_production = int(
        (detail["production_adopted"] & ~detail["strict_would_adopt"]).sum()
    )
    summary = {
        "n_funds": int(len(detail)),
        "n_adopted": int(detail["production_adopted"].sum()),
        "n_kept_legacy": int((~detail["production_adopted"]).sum()),
        "adopted_pass": adopted_pass,
        "adopted_fail": adopted_fail,
        "adopted_unscored": adopted_unscored,
        "strict_would_adopt": strict_would_adopt,
        "strict_would_keep": int(len(detail) - strict_would_adopt),
        "adopted_under_both": adopted_under_both,
        "adopted_only_under_production": adopted_only_under_production,
        "close_pp": float(close_pp),
    }
    fail_table = (
        detail.loc[
            detail["production_adopted"] & detail["rebuild_vs_lipper"].eq("fail"),
            [
                "isin",
                "ticker",
                "decision",
                "rebuild_vs_lipper",
                "rebuild_lipper_horizon",
                "gap_primary_after_pp",
                "strict_would_adopt",
            ],
        ]
        .sort_values("gap_primary_after_pp", key=lambda s: s.abs(), ascending=False)
        .reset_index(drop=True)
    )
    return summary, fail_table


@dataclass
class RebuildFundResult:
    isin: str
    ticker: str | None
    decision: str
    source: str
    adopted: bool
    n_ex_dates: int
    n_days_changed: int
    gap_before: dict[str, float] = field(default_factory=dict)
    gap_after: dict[str, float] = field(default_factory=dict)


def _event_series_for_fund(
    ticker: str | None,
    session_dates: pd.DatetimeIndex,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    distributions_cache: dict[str, Any],
    fmp_cache: dict[str, Any] | None,
) -> tuple[pd.Series, str]:
    if not ticker:
        return pd.Series(0.0, index=session_dates, dtype=float), "none"
    yahoo = fetch_yahoo_cash_events(
        ticker,
        start,
        end,
        cache=distributions_cache,
    )
    if not yahoo.empty and yahoo["distribution"].fillna(0).abs().sum() > 0:
        events = yahoo.loc[yahoo["distribution"].fillna(0) > 0, "distribution"]
        aligned = align_events_to_sessions(session_dates, events)
        return aligned, "yahoo"
    fmp = cash_events_from_fmp(ticker, start, end, fmp_cache)
    if not fmp.empty:
        aligned = align_events_to_sessions(session_dates, fmp)
        if aligned.fillna(0).abs().sum() > 0:
            return aligned, "fmp"
    return pd.Series(0.0, index=session_dates, dtype=float), "none"


def rebuild_fund_tr(
    *,
    isin: str,
    session_dates: pd.DatetimeIndex,
    price: pd.Series,
    legacy_tr_pct: pd.Series,
    legacy_tr_level: pd.Series,
    spx_tr_pct: pd.Series,
    price_pct: pd.Series,
    fund_row: pd.Series | None,
    ticker: str | None,
    bench_counts: pd.Series,
    distributions_cache: dict[str, Any],
    fmp_cache: dict[str, Any] | None = None,
) -> tuple[pd.Series, pd.Series, RebuildFundResult]:
    """Return TR % and TR level series (rebuilt or legacy) plus metadata."""
    start = session_dates.min()
    end = session_dates.max()
    aligned_price = price.reindex(session_dates)
    distributions, dist_source = _event_series_for_fund(
        ticker,
        session_dates,
        start,
        end,
        distributions_cache=distributions_cache,
        fmp_cache=fmp_cache,
    )
    rebuilt_pct = total_return_percent_from_price(aligned_price, distributions)

    if dist_source == "none" and _index_like_fund(fund_row):
        missed = detect_missed_distribution_days(price_pct, legacy_tr_pct, spx_tr_pct)
        for day in missed:
            if day in rebuilt_pct.index:
                spx = spx_tr_pct.loc[day]
                if np.isfinite(spx):
                    rebuilt_pct.loc[day] = float(spx)

    gap_before = (
        horizon_gaps_vs_lipper(legacy_tr_pct, fund_row, bench_counts)
        if fund_row is not None
        else {h: float("nan") for h in DEFAULT_HORIZON_MONTHS}
    )
    gap_after = (
        horizon_gaps_vs_lipper(rebuilt_pct, fund_row, bench_counts)
        if fund_row is not None
        else {h: float("nan") for h in DEFAULT_HORIZON_MONTHS}
    )
    adopt = lipper_gate_should_adopt(gap_before, gap_after)
    if dist_source == "none" and not _index_like_fund(fund_row):
        adopt = False

    chosen_pct = rebuilt_pct if adopt else legacy_tr_pct.copy()
    source = dist_source if adopt else "unchanged"
    decision = "adopted" if adopt else "kept_legacy"

    anchor_candidates = legacy_tr_level.dropna()
    if anchor_candidates.empty:
        anchor_idx = session_dates[0]
        anchor_level = 100.0
    else:
        anchor_idx = anchor_candidates.index[0]
        anchor_level = float(anchor_candidates.iloc[0])

    if adopt:
        chosen_level = recompute_tr_level(
            chosen_pct,
            anchor_level=anchor_level,
            anchor_index=anchor_idx,
        )
    else:
        chosen_level = legacy_tr_level.copy()

    n_ex = int((distributions.fillna(0) > 0).sum())
    changed = int((rebuilt_pct.fillna(-99) != legacy_tr_pct.fillna(-99)).sum())

    meta = RebuildFundResult(
        isin=isin,
        ticker=None if pd.isna(ticker) else str(ticker),
        decision=decision,
        source=source,
        adopted=adopt,
        n_ex_dates=n_ex,
        n_days_changed=changed,
        gap_before=gap_before,
        gap_after=gap_after,
    )
    return chosen_pct, chosen_level, meta


def _panel_column(panel: pd.DataFrame, catalog: pd.DataFrame, header: str) -> int | str | None:
    match = catalog.loc[catalog["header"].eq(header), "column"]
    if match.empty:
        return None
    col = int(match.iloc[0])
    if col in panel.columns:
        return col
    if header in panel.columns:
        return header
    return None


def rebuild_tr_panel(
    panel: pd.DataFrame,
    catalog: pd.DataFrame,
    funds_by_isin: dict[str, pd.Series],
    isin_to_ticker: dict[str, str],
    *,
    spx_header: str = "S&P 500 TR %",
    distributions_cache: dict[str, Any] | None = None,
    fmp_cache: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply rebuild/gate to every fund TR column in ``panel``."""
    result = panel.copy()
    cache = distributions_cache if distributions_cache is not None else load_distributions_cache()
    spx_col = _panel_column(result, catalog, spx_header)
    if spx_col is None:
        raise KeyError(f"Panel has no {spx_header!r}")
    spx = result[spx_col]
    bench_counts = spx.groupby(spx.index.to_period("M")).count()
    sessions = pd.DatetimeIndex(result.index)

    rows: list[dict[str, Any]] = []
    tr_headers = catalog.loc[
        catalog["header"].astype("string").str.endswith("TR %")
        & catalog["id"].astype("string").str.match(r"[A-Z]{2}[A-Z0-9]{9}\d")
    ]
    for record in tr_headers.itertuples(index=False):
        isin = str(record.id).strip()
        tr_pct_col = int(record.column)
        if tr_pct_col not in result.columns:
            tr_pct_col = _panel_column(result, catalog, f"{isin} TR %")
        if tr_pct_col is None:
            continue
        price_col = _panel_column(result, catalog, f"{isin} Price")
        price_pct_col = _panel_column(result, catalog, f"{isin} Price %")
        level_col = _panel_column(result, catalog, f"{isin} TR")
        if price_col is None or level_col is None or price_pct_col is None:
            continue
        fund_row = funds_by_isin.get(isin)
        ticker = isin_to_ticker.get(isin)
        new_pct, new_level, meta = rebuild_fund_tr(
            isin=isin,
            session_dates=sessions,
            price=result[price_col],
            legacy_tr_pct=result[tr_pct_col],
            legacy_tr_level=result[level_col],
            spx_tr_pct=spx,
            price_pct=result[price_pct_col],
            fund_row=fund_row,
            ticker=ticker,
            bench_counts=bench_counts,
            distributions_cache=cache,
            fmp_cache=fmp_cache,
        )
        if meta.adopted:
            result[tr_pct_col] = new_pct.to_numpy()
            result[level_col] = new_level.to_numpy()
        rows.append(
            {
                "isin": isin,
                "fund": str(record.name),
                "ticker": meta.ticker,
                "decision": meta.decision,
                "source": meta.source,
                "n_ex_dates": meta.n_ex_dates,
                "n_days_changed": meta.n_days_changed,
                "gap_3y_before": meta.gap_before.get("3y"),
                "gap_3y_after": meta.gap_after.get("3y"),
                "gap_5y_before": meta.gap_before.get("5y"),
                "gap_5y_after": meta.gap_after.get("5y"),
                "gap_10y_before": meta.gap_before.get("10y"),
                "gap_10y_after": meta.gap_after.get("10y"),
            }
        )

    save_distributions_cache(cache)
    log = pd.DataFrame(rows)
    return result, log
