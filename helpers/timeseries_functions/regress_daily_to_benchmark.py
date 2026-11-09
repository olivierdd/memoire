"""Monthly fund-on-benchmark OLS from the daily D-Timeseries sheets vs Lipper Funds stats."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from helpers.timeseries_functions.compare_regression_to_lipper_funds import (
    _lipper_horizon_columns,
)

LABEL_ROWS = 6
DEFAULT_WORKBOOK_FILENAME = "v2-funds-normalized.xlsx"
FUNDS_SHEET = "Funds final"
# The series notebook replaces CORRECTED_SHEET with the cleaned data and keeps
# the sheet as it was before cleaning in ORIGINAL_SHEET.
CORRECTED_SHEET = "D-Timeseries final"
ORIGINAL_SHEET = "D-Timeseries raw"
SPX_BENCH_HEADER = "S&P 500 TR %"
US_TBILL_HEADER = "US T-Bill 3M"
MIN_BENCH_DAYS_PER_MONTH = 15
DEFAULT_HORIZON_MONTHS: dict[str, int] = {"3y": 36, "5y": 60, "10y": 120}

# Lipper tickers present in the daily sheet header row.
BENCHMARK_TICKER_TO_HEADER: dict[str, str] = {
    ".SPXTR": SPX_BENCH_HEADER,
    ".INX": "S&P 500 C Price %",
}

LIPPER_MATCH_TOLERANCES = {
    "alpha_pp_per_month": 0.05,
    "beta": 0.05,
    "r_squared": 0.05,
    "tracking_error_pp": 0.5,
}


def find_output_data_file(filename: str) -> Path:
    """Locate a file under ``output-data/`` from the repo root or a subfolder."""
    relative = Path("output-data") / filename
    start = Path.cwd().resolve()
    for directory in [start, *start.parents]:
        candidate = directory / relative
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not find {relative}, starting from {start}")


def load_daily_timeseries_raw(
    workbook: Path | pd.ExcelFile,
    *,
    sheet_name: str | int = 0,
    label_rows: int = LABEL_ROWS,
) -> pd.DataFrame:
    raw = pd.read_excel(workbook, sheet_name=sheet_name, header=None, engine="openpyxl")
    if len(raw) <= label_rows or raw.shape[1] < 2:
        raise ValueError(f"Sheet {sheet_name!r} has no observation rows")
    return raw


def parse_daily_catalog(raw: pd.DataFrame, *, label_rows: int = LABEL_ROWS) -> pd.DataFrame:
    labels = raw.iloc[:label_rows, 1:]
    return (
        pd.DataFrame(
            {
                "column": labels.columns.astype(int),
                "id": labels.iloc[0].astype("string").str.strip().to_numpy(),
                "name": labels.iloc[1].astype("string").str.strip().to_numpy(),
                "category": labels.iloc[2].astype("string").str.strip().to_numpy(),
                "header": labels.iloc[5].astype("string").str.strip().to_numpy(),
            }
        )
        .reset_index(drop=True)
    )


def load_daily_return_panel(
    raw: pd.DataFrame,
    *,
    label_rows: int = LABEL_ROWS,
) -> tuple[pd.DataFrame, pd.Series]:
    """Return levels/returns panel indexed by date; columns use row-6 headers."""
    headers = raw.iloc[5, 1:].astype("string").str.strip()
    dates = pd.to_datetime(raw.iloc[label_rows:, 0], errors="coerce")
    body = raw.iloc[label_rows:, 1:].apply(pd.to_numeric, errors="coerce")
    body.index = pd.Index(dates, name="date")
    body.columns = headers.to_numpy()
    counts = body[SPX_BENCH_HEADER].groupby(body.index.to_period("M")).count()
    return body, counts


def compound_daily_to_monthly(
    daily: pd.DataFrame,
    bench_counts: pd.Series,
    *,
    min_bench_days: int = MIN_BENCH_DAYS_PER_MONTH,
) -> pd.DataFrame:
    """Compound daily simple returns to calendar months; drop thin benchmark months."""
    keep_months = bench_counts.loc[bench_counts >= min_bench_days].index
    month_index = daily.index.to_period("M")
    log1p = np.log1p(daily)
    log1p.index = month_index
    monthly = np.expm1(log1p.groupby(level=0).sum(min_count=1))
    monthly = monthly.loc[monthly.index.isin(keep_months)]
    monthly.index = monthly.index.astype("period[M]")
    return monthly


def benchmark_header_for_ticker(ticker: object) -> str | None:
    if ticker is None or (isinstance(ticker, float) and np.isnan(ticker)):
        return None
    text = str(ticker).strip()
    if not text:
        return None
    return BENCHMARK_TICKER_TO_HEADER.get(text)


def fund_tr_return_header(isin: str) -> str:
    return f"{isin} TR %"


@dataclass(frozen=True)
class HorizonRegression:
    horizon: str
    months: int
    window_start: str
    window_end: str
    alpha_pct_per_month: float
    beta: float
    r_squared: float
    tracking_error_ann_pct: float
    correlation: float
    total_return_pct: float
    sharpe_ratio: float


def _lipper_performance_column(years: int) -> str:
    return f"{years} Year Performance to Last Month End"


def _lipper_sharpe_column(years: int) -> str:
    return f"Sharpe Ratio for {years} Years to Last Month End"


def horizon_total_return_pct(returns: np.ndarray) -> float:
    return float((np.prod(1.0 + returns) - 1.0) * 100.0)


def horizon_sharpe_ratio(
    returns: np.ndarray,
    risk_free: np.ndarray | None = None,
) -> float:
    if len(returns) < 3:
        return float("nan")
    excess = returns if risk_free is None else returns - risk_free
    scale = float(np.std(excess, ddof=1))
    if scale == 0.0 or np.isnan(scale):
        return float("nan")
    return float(np.mean(excess) / scale * np.sqrt(12))


def monthly_risk_free_rate(daily: pd.DataFrame) -> pd.Series | None:
    """Month-end 3M T-bill annual % in the daily sheet → monthly decimal return."""
    if US_TBILL_HEADER not in daily.columns:
        return None
    rates = pd.to_numeric(daily[US_TBILL_HEADER], errors="coerce")
    if rates.notna().sum() == 0:
        return None
    month = daily.index.to_period("M")
    annual_pct = rates.groupby(month).last()
    monthly = (1.0 + annual_pct / 100.0) ** (1.0 / 12.0) - 1.0
    monthly = monthly.dropna()
    return monthly if len(monthly) else None


def fit_monthly_regression(
    fund: pd.Series,
    benchmark: pd.Series,
    *,
    horizon: str,
    last_n_months: int,
    risk_free_monthly: pd.Series | None = None,
) -> HorizonRegression | None:
    aligned = pd.concat([fund.rename("fund"), benchmark.rename("bench")], axis=1).dropna()
    if len(aligned) < 3:
        return None
    window = aligned.iloc[-last_n_months:]
    if len(window) < 3:
        return None
    y = window["fund"].to_numpy(dtype=float)
    x = window["bench"].to_numpy(dtype=float)
    fit = sm.OLS(y, sm.add_constant(x)).fit()
    alpha = float(fit.params[0])
    beta = float(fit.params[1])
    excess = y - x
    te = float(np.std(excess, ddof=1) * np.sqrt(12) * 100) if len(excess) > 2 else float("nan")
    corr = float(np.corrcoef(x, y)[0, 1])
    rf: np.ndarray | None = None
    if risk_free_monthly is not None:
        aligned_rf = risk_free_monthly.reindex(window.index)
        if aligned_rf.notna().sum() >= len(window) // 2:
            rf = aligned_rf.to_numpy(dtype=float)
            rf = np.where(np.isnan(rf), 0.0, rf)
    return HorizonRegression(
        horizon=horizon,
        months=len(window),
        window_start=str(window.index[0]),
        window_end=str(window.index[-1]),
        alpha_pct_per_month=alpha * 100.0,
        beta=beta,
        r_squared=float(fit.rsquared),
        tracking_error_ann_pct=te,
        correlation=corr,
        total_return_pct=horizon_total_return_pct(y),
        sharpe_ratio=horizon_sharpe_ratio(y, rf),
    )


def _lipper_value(row: pd.Series, years: int, key: str) -> float:
    col = _lipper_horizon_columns(years)[key]
    value = pd.to_numeric(row.get(col), errors="coerce")
    return float(value) if pd.notna(value) else float("nan")


def _lipper_metric(row: pd.Series, years: int, column: str) -> float:
    value = pd.to_numeric(row.get(column), errors="coerce")
    return float(value) if pd.notna(value) else float("nan")


def regression_rows_for_funds(
    funds: pd.DataFrame,
    monthly: pd.DataFrame,
    *,
    series_source: str,
    risk_free_monthly: pd.Series | None = None,
) -> pd.DataFrame:
    rows: list[dict] = []
    for _, fund in funds.iterrows():
        isin = str(fund["ISIN"]).strip()
        name = fund.get("Name", "")
        ticker = fund.get("Benchmark Ticker")
        bench_header = benchmark_header_for_ticker(ticker)
        fund_header = fund_tr_return_header(isin)
        comparable = bench_header is not None and fund_header in monthly.columns
        if not comparable:
            for horizon, n_months in DEFAULT_HORIZON_MONTHS.items():
                rows.append(
                    _empty_row(
                        isin=isin,
                        name=name,
                        series_source=series_source,
                        horizon=horizon,
                        benchmark_ticker=ticker,
                        benchmark_header=bench_header,
                        reason="benchmark_not_on_sheet"
                        if bench_header is None
                        else "fund_series_missing",
                    )
                )
            continue
        bench = monthly[bench_header]
        fund_series = monthly[fund_header]
        for horizon, n_months in DEFAULT_HORIZON_MONTHS.items():
            years = int(horizon.replace("y", ""))
            result = fit_monthly_regression(
                fund_series,
                bench,
                horizon=horizon,
                last_n_months=n_months,
                risk_free_monthly=risk_free_monthly,
            )
            lipper_alpha = _lipper_value(fund, years, "alpha")
            lipper_beta = _lipper_value(fund, years, "beta")
            lipper_r2 = _lipper_value(fund, years, "r_squared")
            lipper_te = _lipper_value(fund, years, "tracking_error")
            lipper_tr = _lipper_metric(fund, years, _lipper_performance_column(years))
            lipper_sharpe = _lipper_metric(fund, years, _lipper_sharpe_column(years))
            if result is None:
                rows.append(
                    _empty_row(
                        isin=isin,
                        name=name,
                        series_source=series_source,
                        horizon=horizon,
                        benchmark_ticker=ticker,
                        benchmark_header=bench_header,
                        reason="insufficient_months",
                    )
                )
                continue
            rows.append(
                _result_row(
                    isin=isin,
                    name=name,
                    series_source=series_source,
                    horizon=horizon,
                    benchmark_ticker=ticker,
                    benchmark_header=bench_header,
                    result=result,
                    lipper_alpha=lipper_alpha,
                    lipper_beta=lipper_beta,
                    lipper_r2=lipper_r2,
                    lipper_te=lipper_te,
                    lipper_total_return_pct=lipper_tr,
                    lipper_sharpe=lipper_sharpe,
                )
            )
    return pd.DataFrame(rows)


def _empty_row(
    *,
    isin: str,
    name: str,
    series_source: str,
    horizon: str,
    benchmark_ticker: object,
    benchmark_header: str | None,
    reason: str,
) -> dict:
    return {
        "isin": isin,
        "name": name,
        "series_source": series_source,
        "horizon": horizon,
        "benchmark_ticker": benchmark_ticker,
        "benchmark_header": benchmark_header,
        "months": np.nan,
        "window_start": None,
        "window_end": None,
        "alpha_pct_per_month": np.nan,
        "beta": np.nan,
        "r_squared": np.nan,
        "tracking_error_ann_pct": np.nan,
        "correlation": np.nan,
        "lipper_alpha_pct_per_month": np.nan,
        "lipper_beta": np.nan,
        "lipper_r_squared": np.nan,
        "lipper_tracking_error_ann_pct": np.nan,
        "delta_alpha_pp_per_month": np.nan,
        "delta_beta": np.nan,
        "delta_r_squared": np.nan,
        "delta_tracking_error_pp": np.nan,
        "total_return_pct": np.nan,
        "sharpe_ratio": np.nan,
        "lipper_total_return_pct": np.nan,
        "lipper_sharpe": np.nan,
        "delta_total_return_pct": np.nan,
        "delta_sharpe": np.nan,
        "lipper_match": None,
        "status": reason,
    }


def _result_row(
    *,
    isin: str,
    name: str,
    series_source: str,
    horizon: str,
    benchmark_ticker: object,
    benchmark_header: str,
    result: HorizonRegression,
    lipper_alpha: float,
    lipper_beta: float,
    lipper_r2: float,
    lipper_te: float,
    lipper_total_return_pct: float,
    lipper_sharpe: float,
) -> dict:
    delta_alpha = (
        result.alpha_pct_per_month - lipper_alpha
        if pd.notna(lipper_alpha)
        else np.nan
    )
    delta_beta = result.beta - lipper_beta if pd.notna(lipper_beta) else np.nan
    delta_r2 = result.r_squared - lipper_r2 if pd.notna(lipper_r2) else np.nan
    delta_te = (
        result.tracking_error_ann_pct - lipper_te if pd.notna(lipper_te) else np.nan
    )
    delta_tr = (
        result.total_return_pct - lipper_total_return_pct
        if pd.notna(lipper_total_return_pct)
        else np.nan
    )
    delta_sharpe = (
        result.sharpe_ratio - lipper_sharpe if pd.notna(lipper_sharpe) else np.nan
    )
    match = lipper_horizon_match(
        delta_alpha_pp_per_month=delta_alpha,
        delta_beta=delta_beta,
        delta_r_squared=delta_r2,
        delta_tracking_error_pp=delta_te,
        has_lipper=pd.notna(lipper_beta),
    )
    return {
        "isin": isin,
        "name": name,
        "series_source": series_source,
        "horizon": horizon,
        "benchmark_ticker": benchmark_ticker,
        "benchmark_header": benchmark_header,
        "months": result.months,
        "window_start": result.window_start,
        "window_end": result.window_end,
        "alpha_pct_per_month": result.alpha_pct_per_month,
        "beta": result.beta,
        "r_squared": result.r_squared,
        "tracking_error_ann_pct": result.tracking_error_ann_pct,
        "correlation": result.correlation,
        "lipper_alpha_pct_per_month": lipper_alpha,
        "lipper_beta": lipper_beta,
        "lipper_r_squared": lipper_r2,
        "lipper_tracking_error_ann_pct": lipper_te,
        "delta_alpha_pp_per_month": delta_alpha,
        "delta_beta": delta_beta,
        "delta_r_squared": delta_r2,
        "delta_tracking_error_pp": delta_te,
        "total_return_pct": result.total_return_pct,
        "sharpe_ratio": result.sharpe_ratio,
        "lipper_total_return_pct": lipper_total_return_pct,
        "lipper_sharpe": lipper_sharpe,
        "delta_total_return_pct": delta_tr,
        "delta_sharpe": delta_sharpe,
        "lipper_match": match,
        "status": "ok",
    }


def lipper_horizon_match(
    *,
    delta_alpha_pp_per_month: float,
    delta_beta: float,
    delta_r_squared: float,
    delta_tracking_error_pp: float,
    has_lipper: bool,
) -> bool | None:
    if not has_lipper:
        return None
    if any(
        pd.isna(v)
        for v in (
            delta_alpha_pp_per_month,
            delta_beta,
            delta_r_squared,
            delta_tracking_error_pp,
        )
    ):
        return None
    tol = LIPPER_MATCH_TOLERANCES
    return (
        abs(delta_alpha_pp_per_month) <= tol["alpha_pp_per_month"]
        and abs(delta_beta) <= tol["beta"]
        and abs(delta_r_squared) <= tol["r_squared"]
        and abs(delta_tracking_error_pp) <= tol["tracking_error_pp"]
    )


def fund_lipper_match_summary(comparison: pd.DataFrame) -> pd.DataFrame:
    """One row per fund and series source: all horizons with Lipper must match."""
    ok = comparison.loc[comparison["status"].eq("ok") & comparison["lipper_beta"].notna()]
    grouped = (
        ok.groupby(["isin", "name", "series_source"], as_index=False)
        .agg(
            horizons=("horizon", "count"),
            horizons_match=("lipper_match", lambda s: int(s.fillna(False).all())),
        )
        .assign(
            lipper_match=lambda frame: frame["horizons_match"].eq(frame["horizons"]),
        )
    )
    return grouped


def match_rate_by_horizon(comparison: pd.DataFrame) -> pd.DataFrame:
    ok = comparison.loc[
        comparison["status"].eq("ok") & comparison["lipper_beta"].notna()
    ]
    return (
        ok.groupby(["series_source", "horizon"], as_index=False)
        .agg(
            funds=("isin", "nunique"),
            match=("lipper_match", lambda s: int(s.fillna(False).sum())),
        )
        .assign(match_rate=lambda frame: frame["match"] / frame["funds"])
    )


def load_funds_reference(
    workbook: Path | pd.ExcelFile | None = None,
    *,
    sheet_name: str = FUNDS_SHEET,
) -> pd.DataFrame:
    source = workbook if workbook is not None else find_output_data_file(DEFAULT_WORKBOOK_FILENAME)
    return pd.read_excel(source, sheet_name=sheet_name, engine="openpyxl")


def monthly_returns_from_workbook(
    workbook: Path | pd.ExcelFile,
    *,
    sheet_name: str | int = 0,
) -> tuple[pd.DataFrame, pd.Series | None]:
    raw = load_daily_timeseries_raw(workbook, sheet_name=sheet_name)
    daily, bench_counts = load_daily_return_panel(raw)
    monthly = compound_daily_to_monthly(daily, bench_counts)
    risk_free = monthly_risk_free_rate(daily)
    return monthly, risk_free


def daily_series_sheets(sheet_names: list[str]) -> dict[str, str]:
    """Series versions to regress, keyed by label, the cleaned one first.

    Before the series notebook saves its corrections there is no
    ``ORIGINAL_SHEET``, and ``CORRECTED_SHEET`` still holds the data as it was
    downloaded, so it is labelled ``original``.
    """
    if CORRECTED_SHEET not in sheet_names:
        raise ValueError(f"The workbook has no {CORRECTED_SHEET!r} sheet")
    if ORIGINAL_SHEET in sheet_names:
        return {"corrected": CORRECTED_SHEET, "original": ORIGINAL_SHEET}
    return {"original": CORRECTED_SHEET}


def compare_daily_sheets_to_lipper(
    workbook: Path | None = None,
    *,
    funds: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, str]]:
    """Regress each daily-series sheet of the normalized workbook on its benchmark.

    Returns the long comparison, the monthly panel per series version, and the
    sheet each version was read from.
    """
    path = workbook if workbook is not None else find_output_data_file(DEFAULT_WORKBOOK_FILENAME)
    with pd.ExcelFile(path, engine="openpyxl") as book:
        sheets = daily_series_sheets(book.sheet_names)
        funds = funds if funds is not None else load_funds_reference(book)
        monthly_by_source: dict[str, pd.DataFrame] = {}
        parts = []
        for source, sheet in sheets.items():
            monthly, risk_free = monthly_returns_from_workbook(book, sheet_name=sheet)
            monthly_by_source[source] = monthly
            parts.append(
                regression_rows_for_funds(
                    funds,
                    monthly,
                    series_source=source,
                    risk_free_monthly=risk_free,
                )
            )
    comparison = pd.concat(parts, ignore_index=True)
    return comparison, monthly_by_source, sheets


def monthly_scatter_frame(
    monthly: pd.DataFrame,
    isin: str,
    benchmark_header: str,
    *,
    last_n_months: int = 120,
) -> pd.DataFrame:
    fund_header = fund_tr_return_header(isin)
    aligned = pd.concat(
        [
            monthly[fund_header].rename("fund"),
            monthly[benchmark_header].rename("benchmark"),
        ],
        axis=1,
    ).dropna()
    window = aligned.iloc[-last_n_months:]
    return window.reset_index(names="month")
