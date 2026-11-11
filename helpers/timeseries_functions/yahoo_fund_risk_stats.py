"""Yahoo fundPerformance risk statistics (alpha, beta) with disk cache."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from curl_cffi.requests.exceptions import HTTPError
from yfinance.data import YfData
from yfinance.exceptions import YFRateLimitError

from helpers.funds_functions.map_yahoo_static import resolve_cache_path

DEFAULT_CACHE = Path("cache") / "yahoo-risk-stats.json"
PAUSE_SECONDS = 0.5
SAVE_EVERY = 10
MAX_ATTEMPTS = 6
RATE_LIMIT_SLEEP_SECONDS = 60
NULLS_ARE_FINAL = "_nulls_are_final"

LARGE_LIPPER_ALPHA_PP_PER_MONTH = 0.10
YAHOO_BETA_CLOSE = 0.15

YAHOO_HORIZONS = ("3y", "5y", "10y")


def _raw_metric(field: object) -> float | None:
    if field is None:
        return None
    if isinstance(field, dict):
        raw = field.get("raw")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    try:
        return float(field)
    except (TypeError, ValueError):
        return None


def parse_fund_performance_payload(payload: object, *, ticker: str = "") -> dict:
    """Turn a quoteSummary fundPerformance payload into cached horizons."""
    if not isinstance(payload, dict):
        return {"source": "yahoo", "symbol": ticker, "horizons": {}, "error": "invalid_payload"}

    quote = payload.get("quoteSummary") if "quoteSummary" in payload else None
    if quote is None:
        quote = payload

    result_list: list[Any] = []
    if isinstance(quote, dict):
        result_list = list(quote.get("result") or [])
    if not result_list or not isinstance(result_list[0], dict):
        return {"source": "yahoo", "symbol": ticker, "horizons": {}, "error": "no_result"}

    fund_perf = result_list[0].get("fundPerformance") or {}
    risk_overview = fund_perf.get("riskOverviewStatistics") or {}
    statistics = risk_overview.get("riskStatistics") or []
    horizons: dict[str, dict[str, float | None]] = {}
    for entry in statistics:
        if not isinstance(entry, dict):
            continue
        year = str(entry.get("year") or "").strip()
        if year not in YAHOO_HORIZONS:
            continue
        horizons[year] = {
            "alpha": _raw_metric(entry.get("alpha")),
            "beta": _raw_metric(entry.get("beta")),
            "r_squared": _raw_metric(entry.get("rSquared")),
        }

    error = None if horizons else "no_risk_statistics"
    return {
        "source": "yahoo",
        "symbol": ticker,
        "horizons": horizons,
        **({"error": error} if error else {}),
    }


def load_yahoo_risk_stats_cache(cache_path: Path | None = None) -> dict:
    path = resolve_cache_path(cache_path or DEFAULT_CACHE)
    if not path.is_file():
        return {}
    try:
        cache = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return cache if isinstance(cache, dict) else {}


def save_yahoo_risk_stats_cache(cache: dict, cache_path: Path | None = None) -> None:
    path = resolve_cache_path(cache_path or DEFAULT_CACHE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2) + "\n")


def _record_has_horizons(record: object) -> bool:
    if not isinstance(record, dict):
        return False
    horizons = record.get("horizons")
    if not isinstance(horizons, dict) or not horizons:
        return False
    return any(
        isinstance(row, dict) and (row.get("alpha") is not None or row.get("beta") is not None)
        for row in horizons.values()
    )


def fetch_yahoo_risk_stats(ticker: str, *, yf_data: YfData | None = None) -> dict:
    data = yf_data or YfData(session=None)
    raw = data.get_raw_json(
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
        params={"modules": "fundPerformance"},
    )
    record = parse_fund_performance_payload(raw, ticker=ticker)
    record["symbol"] = ticker
    return record


def _fetch_with_retries(ticker: str, yf_data: YfData) -> tuple[dict | None, bool]:
    for _attempt in range(MAX_ATTEMPTS):
        try:
            return fetch_yahoo_risk_stats(ticker, yf_data=yf_data), True
        except YFRateLimitError:
            print("Yahoo rate limit, sleeping 60s")
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)
        except HTTPError as error:
            status = getattr(error.response, "status_code", None)
            if status == 429:
                print("Yahoo rate limit, sleeping 60s")
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            return (
                {
                    "source": "yahoo",
                    "symbol": ticker,
                    "horizons": {},
                    "error": f"http_{status}",
                },
                True,
            )
        except Exception as error:  # noqa: BLE001 — Yahoo errors vary by endpoint/version
            return (
                {
                    "source": "yahoo",
                    "symbol": ticker,
                    "horizons": {},
                    "error": type(error).__name__,
                },
                True,
            )
    return None, False


def refresh_yahoo_risk_stats_cache(
    tickers: list[str],
    cache_path: Path | None = None,
    *,
    pause_seconds: float = PAUSE_SECONDS,
    save_every: int = SAVE_EVERY,
) -> dict:
    """Fetch missing Yahoo risk stats and merge into the JSON cache."""
    yahoo_cache = load_yahoo_risk_stats_cache(cache_path)
    yahoo_cache.pop(NULLS_ARE_FINAL, None)

    pending = [
        ticker
        for ticker in tickers
        if ticker
        and (ticker not in yahoo_cache or not _record_has_horizons(yahoo_cache.get(ticker)))
    ]
    pending = list(dict.fromkeys(pending))
    print(
        f"{len(tickers) - len(pending)} risk profiles loaded from cache, "
        f"{len(pending)} still to look up"
    )

    yf_data = YfData(session=None)
    finished = True
    for index, ticker in enumerate(pending, start=1):
        record, stored = _fetch_with_retries(ticker, yf_data)
        if not stored:
            finished = False
            print("Yahoo rate limit. Cached risk stats saved; run the cell again to continue.")
            break
        yahoo_cache[ticker] = record
        if index % save_every == 0 or index == len(pending):
            with_data = sum(_record_has_horizons(row) for row in yahoo_cache.values())
            print(
                f"{with_data} tickers with risk stats cached, "
                f"{index} of {len(pending)} requested this run"
            )
            save_yahoo_risk_stats_cache(yahoo_cache, cache_path)
        if index < len(pending):
            time.sleep(pause_seconds)

    if finished and not pending:
        yahoo_cache[NULLS_ARE_FINAL] = True
    save_yahoo_risk_stats_cache(yahoo_cache, cache_path)
    return yahoo_cache


def risk_stats_long_frame(cache: dict) -> pd.DataFrame:
    rows: list[dict] = []
    for ticker, record in cache.items():
        if ticker.startswith("_") or not isinstance(record, dict):
            continue
        horizons = record.get("horizons") or {}
        if not isinstance(horizons, dict):
            continue
        for horizon, metrics in horizons.items():
            if not isinstance(metrics, dict):
                continue
            rows.append(
                {
                    "yahoo_ticker": ticker,
                    "horizon": horizon,
                    "yahoo_alpha_ann_pct": metrics.get("alpha"),
                    "yahoo_beta": metrics.get("beta"),
                    "yahoo_r_squared": metrics.get("r_squared"),
                }
            )
    return pd.DataFrame(rows)


def tickers_from_funds_for_comparison(
    funds: pd.DataFrame,
    comparison: pd.DataFrame,
    *,
    ticker_column: str = "openfigi_market_id",
) -> list[str]:
    isins = (
        comparison.loc[comparison["status"].eq("ok"), "isin"].astype(str).str.strip().unique()
    )
    meta = funds.copy()
    meta["isin_key"] = meta["ISIN"].astype(str).str.strip()
    subset = meta.loc[meta["isin_key"].isin(isins)]
    if ticker_column not in subset.columns:
        return []
    tickers = subset[ticker_column].dropna().astype(str).str.strip()
    tickers = tickers[~tickers.isin(("", "nan", "None"))]
    return list(dict.fromkeys(tickers.tolist()))


def _yahoo_horizon_metrics(cache: dict, ticker: str, horizon: str) -> dict | None:
    record = cache.get(ticker)
    if not isinstance(record, dict):
        return None
    horizons = record.get("horizons")
    if not isinstance(horizons, dict):
        return None
    row = horizons.get(horizon)
    return row if isinstance(row, dict) else None


def yahoo_alpha_beta_comparison(
    comparison: pd.DataFrame,
    funds: pd.DataFrame,
    yahoo_cache: dict,
    *,
    ticker_column: str = "openfigi_market_id",
) -> pd.DataFrame:
    """Join OLS/Lipper comparison rows with Yahoo risk statistics when available."""
    comp = comparison.loc[comparison["status"].eq("ok")].copy()
    comp["isin_key"] = comp["isin"].astype(str).str.strip()
    meta = funds[["ISIN", ticker_column]].copy()
    meta["isin_key"] = meta["ISIN"].astype(str).str.strip()
    meta = meta.rename(columns={ticker_column: "yahoo_ticker"})
    meta = meta.drop_duplicates("isin_key")[["isin_key", "yahoo_ticker"]]
    comp = comp.merge(meta, on="isin_key", how="left")

    rows: list[dict] = []
    for row in comp.itertuples(index=False):
        ticker = getattr(row, "yahoo_ticker", None)
        if not isinstance(ticker, str) or not ticker.strip():
            continue
        ticker = ticker.strip()
        horizon = str(row.horizon)
        yahoo = _yahoo_horizon_metrics(yahoo_cache, ticker, horizon)
        if yahoo is None:
            continue
        y_alpha = yahoo.get("alpha")
        y_beta = yahoo.get("beta")
        if y_alpha is None and y_beta is None:
            continue
        lipper_alpha = float(row.lipper_alpha_pct_per_month)
        our_alpha = float(row.alpha_pct_per_month)
        our_beta = float(row.beta)
        lipper_beta = float(row.lipper_beta)
        our_alpha_ann = our_alpha * 12.0
        lipper_alpha_ann = lipper_alpha * 12.0
        delta_alpha_pp = float(row.delta_alpha_pp_per_month)
        delta_beta = float(row.delta_beta)

        gap_alpha_ours_yahoo = (
            our_alpha_ann - float(y_alpha) if y_alpha is not None else np.nan
        )
        gap_alpha_ours_lipper = our_alpha_ann - lipper_alpha_ann
        gap_alpha_yahoo_lipper = (
            float(y_alpha) - lipper_alpha_ann if y_alpha is not None else np.nan
        )
        gap_beta_ours_yahoo = our_beta - float(y_beta) if y_beta is not None else np.nan
        gap_beta_ours_lipper = our_beta - lipper_beta
        gap_beta_yahoo_lipper = (
            float(y_beta) - lipper_beta if y_beta is not None else np.nan
        )

        abs_oy = abs(gap_alpha_ours_yahoo) if pd.notna(gap_alpha_ours_yahoo) else np.inf
        abs_ol = abs(gap_alpha_ours_lipper)
        abs_by = abs(gap_beta_ours_yahoo) if pd.notna(gap_beta_ours_yahoo) else np.inf
        abs_bl = abs(gap_beta_ours_lipper)

        rows.append(
            {
                "name": row.name,
                "isin": row.isin,
                "horizon": horizon,
                "yahoo_ticker": ticker,
                "alpha_pct_per_month": our_alpha,
                "beta": our_beta,
                "lipper_alpha_pct_per_month": lipper_alpha,
                "lipper_beta": lipper_beta,
                "lipper_alpha_ann_pct": lipper_alpha_ann,
                "alpha_ann_pct": our_alpha_ann,
                "yahoo_alpha_ann_pct": y_alpha,
                "yahoo_beta": y_beta,
                "yahoo_r_squared": yahoo.get("r_squared"),
                "delta_alpha_pp_per_month": delta_alpha_pp,
                "delta_beta": delta_beta,
                "abs_delta_alpha_pp_per_month": abs(delta_alpha_pp),
                "gap_alpha_ours_yahoo_ann_pp": gap_alpha_ours_yahoo,
                "gap_alpha_ours_lipper_ann_pp": gap_alpha_ours_lipper,
                "gap_alpha_yahoo_lipper_ann_pp": gap_alpha_yahoo_lipper,
                "gap_beta_ours_yahoo": gap_beta_ours_yahoo,
                "gap_beta_ours_lipper": gap_beta_ours_lipper,
                "gap_beta_yahoo_lipper": gap_beta_yahoo_lipper,
                "yahoo_closer_alpha": abs_oy < abs_ol if np.isfinite(abs_oy) else False,
                "yahoo_closer_beta": abs_by < abs_bl if np.isfinite(abs_by) else False,
                "lipper_alpha_large_gap": abs(delta_alpha_pp) > LARGE_LIPPER_ALPHA_PP_PER_MONTH,
                "yahoo_agrees_beta": (
                    abs(gap_beta_ours_yahoo) <= YAHOO_BETA_CLOSE
                    if pd.notna(gap_beta_ours_yahoo)
                    else False
                ),
            }
        )
    return pd.DataFrame(rows)


def yahoo_vs_lipper_summary(
    frame: pd.DataFrame,
    *,
    large_lipper_alpha_pp: float = LARGE_LIPPER_ALPHA_PP_PER_MONTH,
    yahoo_beta_close: float = YAHOO_BETA_CLOSE,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "horizon",
                "n_with_yahoo",
                "median_abs_gap_alpha_ours_yahoo_ann",
                "median_abs_gap_alpha_ours_lipper_ann",
                "median_abs_gap_beta_ours_yahoo",
                "median_abs_gap_beta_ours_lipper",
                "share_yahoo_closer_alpha",
                "share_yahoo_closer_beta",
                "n_large_lipper_alpha_gap",
                "share_yahoo_agrees_beta_when_large_alpha_gap",
            ]
        )

    rows: list[dict] = []
    for horizon, group in frame.groupby("horizon", sort=False):
        alpha_y = group["gap_alpha_ours_yahoo_ann_pp"].abs()
        alpha_l = group["gap_alpha_ours_lipper_ann_pp"].abs()
        beta_y = group["gap_beta_ours_yahoo"].abs()
        beta_l = group["gap_beta_ours_lipper"].abs()
        large = group.loc[group["abs_delta_alpha_pp_per_month"] > large_lipper_alpha_pp]
        rows.append(
            {
                "horizon": horizon,
                "n_with_yahoo": int(len(group)),
                "median_abs_gap_alpha_ours_yahoo_ann": float(alpha_y.median()),
                "median_abs_gap_alpha_ours_lipper_ann": float(alpha_l.median()),
                "median_abs_gap_beta_ours_yahoo": float(beta_y.median()),
                "median_abs_gap_beta_ours_lipper": float(beta_l.median()),
                "share_yahoo_closer_alpha": float(group["yahoo_closer_alpha"].mean()),
                "share_yahoo_closer_beta": float(group["yahoo_closer_beta"].mean()),
                "n_large_lipper_alpha_gap": int(len(large)),
                "share_yahoo_agrees_beta_when_large_alpha_gap": (
                    float(large["yahoo_agrees_beta"].mean()) if len(large) else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)
