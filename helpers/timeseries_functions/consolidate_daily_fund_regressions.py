"""Daily fund-on-benchmark OLS matching the Consolidation spreadsheet (252-day annualisation)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

from helpers.timeseries_functions.regress_daily_to_benchmark import (
    CORRECTED_SHEET,
    DEFAULT_WORKBOOK_FILENAME,
    LIPPER_AS_OF,
    SPX_BENCH_HEADER,
    find_output_data_file,
    fund_tr_return_header,
    load_daily_return_panel,
    load_daily_timeseries_raw,
    load_funds_reference,
    parse_daily_catalog,
)

FUND_CATEGORIES = frozenset({"Active MF", "Active ETF", "Passive MF", "Passive ETF"})
RETURN_SERIES_CHOICES = ("Total return", "Price return")
DEFAULT_BENCHMARK_NAME = "S&P 500 TR"
DEFAULT_TRADING_DAYS_PER_YEAR = 252
DEFAULT_WINDOW_MONTHS = 120
DISPLAY_DECIMALS = 4

_TEXT_TABLE_COLUMNS = frozenset(
    {
        "Fund",
        "Category",
        "Indicator",
        "Statistic",
        "Parameter",
        "Default",
        "Override",
        "Used",
    }
)
_INT_TABLE_COLUMNS = frozenset({"ETF", "Active", "ETF×Active"})

FUND_TABLE_COLUMNS = [
    "Fund",
    "Category",
    "ETF",
    "Active",
    "ETF×Active",
    "Fees (%)",
    "AUM",
    "Trading days",
    "Beta",
    "Tracking error (%)",
    "Excess return (%/yr)",
    "Net alpha (%/yr)",
    "Gross alpha (%/yr)",
    "Information ratio",
    "Selected Y",
]

_CONSOLIDATION_GROUPS: list[tuple[str, int | None, int | None]] = [
    ("Active", 1, None),
    ("Passive", 0, None),
    ("Mutual Funds", None, 0),
    ("ETF", None, 1),
    ("Active MF", 1, 0),
    ("Passive MF", 0, 0),
    ("Active ETF", 1, 1),
    ("Passive ETF", 0, 1),
]

_METRIC_COLUMNS_FOR_STATS = [
    "Fees (%)",
    "Beta",
    "Tracking error (%)",
    "Excess return (%/yr)",
    "Net alpha (%/yr)",
    "Gross alpha (%/yr)",
    "Information ratio",
]


@dataclass(frozen=True)
class AnalysisParameters:
    end_date: pd.Timestamp
    start_date: pd.Timestamp
    return_series: str
    benchmark_name: str
    trading_days_per_year: int
    lipper_as_of: pd.Timestamp
    benchmark_return_header: str
    trading_days_in_window: int

    def as_display_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "Parameter": "End date",
                "Default": "",
                "Override": "",
                "Used": self.end_date.strftime("%d/%m/%Y"),
            },
            {
                "Parameter": "Start date",
                "Default": "",
                "Override": "",
                "Used": self.start_date.strftime("%d/%m/%Y"),
            },
            {
                "Parameter": "Trading days in window",
                "Default": "*calculated*",
                "Override": "",
                "Used": str(self.trading_days_in_window),
            },
            {
                "Parameter": "Return series",
                "Default": "Total return",
                "Override": "",
                "Used": self.return_series,
            },
            {
                "Parameter": "Benchmark series",
                "Default": DEFAULT_BENCHMARK_NAME,
                "Override": "",
                "Used": self.benchmark_name,
            },
            {
                "Parameter": "Benchmark return column",
                "Default": "*calculated*",
                "Override": "",
                "Used": self.benchmark_return_header,
            },
            {
                "Parameter": "Trading days per year (to annualize tracking error)",
                "Default": "*calculated*",
                "Override": "",
                "Used": str(self.trading_days_per_year),
            },
        ]


def _fund_return_header(isin: str, return_series: str) -> str:
    if return_series == "Price return":
        return f"{isin} Price %"
    return fund_tr_return_header(isin)


def benchmark_return_header_for_name(
    catalog: pd.DataFrame,
    daily_columns: pd.Index,
    benchmark_name: str,
) -> str:
    """Map Config-style index name to a daily ``… %`` header."""
    trimmed = str(benchmark_name).strip()
    matches = catalog.loc[
        catalog["name"].astype("string").str.strip().eq(trimmed)
        & catalog["header"].astype("string").str.endswith("%", na=False)
    ]
    if matches.empty:
        matches = catalog.loc[
            catalog["id"].astype("string").str.strip().eq(trimmed)
            & catalog["header"].astype("string").str.endswith("%", na=False)
        ]
    if matches.empty and trimmed == DEFAULT_BENCHMARK_NAME:
        if SPX_BENCH_HEADER in daily_columns:
            return SPX_BENCH_HEADER
        raise KeyError(f"Benchmark column {SPX_BENCH_HEADER!r} missing from daily panel")
    if matches.empty:
        raise KeyError(f"No daily return column for benchmark {benchmark_name!r}")
    header = str(matches.iloc[0]["header"]).strip()
    if header not in daily_columns:
        raise KeyError(f"Benchmark header {header!r} not in daily panel")
    return header


def list_benchmark_name_choices(catalog: pd.DataFrame) -> list[str]:
    index_rows = catalog.loc[
        catalog["category"].astype("string").str.strip().eq("Index")
    ]
    names = (
        index_rows["name"]
        .astype("string")
        .str.strip()
        .dropna()
        .unique()
        .tolist()
    )
    if DEFAULT_BENCHMARK_NAME not in names:
        names.insert(0, DEFAULT_BENCHMARK_NAME)
    return sorted(set(names), key=lambda label: (label != DEFAULT_BENCHMARK_NAME, label))


def _default_end_date(daily: pd.DataFrame, lipper_as_of: pd.Timestamp) -> pd.Timestamp:
    in_range = daily.index[daily.index <= lipper_as_of]
    if len(in_range) == 0:
        return lipper_as_of.normalize()
    return pd.Timestamp(in_range.max()).normalize()


def _count_trading_days(
    daily: pd.DataFrame,
    bench_header: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> int:
    window = daily.loc[(daily.index >= start) & (daily.index <= end)]
    bench = pd.to_numeric(window[bench_header], errors="coerce")
    return int(bench.notna().sum())


def resolve_analysis_parameters(
    daily: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    end_override: pd.Timestamp | None = None,
    start_override: pd.Timestamp | None = None,
    return_series: str = "Total return",
    benchmark_name: str = DEFAULT_BENCHMARK_NAME,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR,
    lipper_as_of: pd.Timestamp = LIPPER_AS_OF,
) -> AnalysisParameters:
    if return_series not in RETURN_SERIES_CHOICES:
        raise ValueError(f"return_series must be one of {RETURN_SERIES_CHOICES}")
    default_end = _default_end_date(daily, lipper_as_of)
    end = pd.Timestamp(end_override).normalize() if end_override is not None else default_end
    end = min(end, lipper_as_of.normalize())
    default_start = (end - pd.DateOffset(months=DEFAULT_WINDOW_MONTHS)).normalize()
    start = (
        pd.Timestamp(start_override).normalize()
        if start_override is not None
        else default_start
    )
    bench_header = benchmark_return_header_for_name(
        catalog, daily.columns, benchmark_name
    )
    trading_days = _count_trading_days(daily, bench_header, start, end)
    return AnalysisParameters(
        end_date=end,
        start_date=start,
        return_series=return_series,
        benchmark_name=benchmark_name,
        trading_days_per_year=trading_days_per_year,
        lipper_as_of=lipper_as_of.normalize(),
        benchmark_return_header=bench_header,
        trading_days_in_window=trading_days,
    )


def fit_daily_fund_benchmark_regression(
    fund_returns: np.ndarray,
    bench_returns: np.ndarray,
    *,
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR,
    fees_pct: float | None = None,
) -> dict[str, float]:
    """OLS on daily simple returns; outputs in Consolidation column units."""
    n = len(fund_returns)
    if n < 3:
        return {
            "Trading days": float(n),
            "Beta": float("nan"),
            "Tracking error (%)": float("nan"),
            "Excess return (%/yr)": float("nan"),
            "Net alpha (%/yr)": float("nan"),
            "Gross alpha (%/yr)": float("nan"),
            "Information ratio": float("nan"),
        }
    fit = sm.OLS(fund_returns, sm.add_constant(bench_returns)).fit()
    intercept = float(fit.params[0])
    beta = float(fit.params[1])
    excess = fund_returns - bench_returns
    excess_mean = float(np.mean(excess))
    te = float(np.std(excess, ddof=1) * np.sqrt(trading_days_per_year) * 100.0)
    excess_ann_pct = excess_mean * trading_days_per_year * 100.0
    net_alpha_pct = intercept * trading_days_per_year * 100.0
    fees = float(fees_pct) if fees_pct is not None and pd.notna(fees_pct) else float("nan")
    gross_alpha_pct = (
        net_alpha_pct + fees if pd.notna(fees) else float("nan")
    )
    ir = excess_ann_pct / te if te > 0 and np.isfinite(te) else float("nan")
    return {
        "Trading days": float(n),
        "Beta": beta,
        "Tracking error (%)": te,
        "Excess return (%/yr)": excess_ann_pct,
        "Net alpha (%/yr)": net_alpha_pct,
        "Gross alpha (%/yr)": gross_alpha_pct,
        "Information ratio": ir,
    }


def category_flags(category: str) -> tuple[str, int, int, int]:
    text = str(category).strip()
    is_etf = 1 if text.endswith("ETF") else 0
    is_active = 1 if text.startswith("Active") else 0
    display = text
    if text in FUND_CATEGORIES:
        style = "Active" if is_active else "Passive"
        vehicle = "ETF" if is_etf else "MF"
        display = f"{style} {vehicle}"
    return display, is_etf, is_active, is_etf * is_active


def _selection_mask(funds: pd.DataFrame) -> pd.Series | None:
    for column in ("select.outcome", "ds.is_selected", "is_selected"):
        if column in funds.columns:
            values = funds[column]
            if values.dtype == bool:
                return values.fillna(False)
            return values.astype("string").str.upper().isin({"TRUE", "1", "YES", "Y"})
    return None


def _isin_column(funds: pd.DataFrame) -> str:
    for column in ("ISIN", "ds.isin", "B"):
        if column in funds.columns:
            return column
    raise KeyError("Funds sheet has no ISIN column")


def _fees_column(funds: pd.DataFrame) -> str | None:
    for column in (
        "ds.total_expense_ratio",
        "Total Expense Ratio",
        "Fees (%)",
        "total_expense_ratio",
    ):
        if column in funds.columns:
            return column
    return None


def _aum_column(funds: pd.DataFrame) -> str | None:
    for column in (
        "ds.fund_total_assets_under_management",
        "Fund Total Assets under Management",
        "AUM",
    ):
        if column in funds.columns:
            return column
    return None


def _numeric_lookup(
    funds: pd.DataFrame,
    isin_col: str,
    value_col: str,
) -> dict[str, float]:
    subset = funds[[isin_col, value_col]].dropna(subset=[isin_col])
    isins = subset[isin_col].astype("string").str.strip()
    values = pd.to_numeric(subset[value_col], errors="coerce")
    return {
        str(isin): float(val)
        for isin, val in zip(isins, values, strict=False)
        if pd.notna(val)
    }


def load_fund_metadata_by_isin(
    workbook: Path | pd.ExcelFile,
) -> tuple[dict[str, float], dict[str, float]]:
    """TER and Lipper AUM keyed by ISIN (from Funds or Funds final)."""
    fees_map: dict[str, float] = {}
    aum_map: dict[str, float] = {}
    for sheet in ("Funds final", "Funds"):
        try:
            funds = pd.read_excel(workbook, sheet_name=sheet, engine="openpyxl")
        except ValueError:
            continue
        isin_col = _isin_column(funds)
        fees_col = _fees_column(funds)
        aum_col = _aum_column(funds)
        if fees_col is not None:
            fees_map.update(_numeric_lookup(funds, isin_col, fees_col))
        if aum_col is not None:
            aum_map.update(_numeric_lookup(funds, isin_col, aum_col))
        if fees_map and aum_map:
            break
    return fees_map, aum_map


def load_fees_by_isin(workbook: Path | pd.ExcelFile) -> dict[str, float]:
    fees_map, _ = load_fund_metadata_by_isin(workbook)
    return fees_map


def fund_universe_from_catalog(
    catalog: pd.DataFrame,
    *,
    return_series: str,
    selected_isins: set[str] | None = None,
) -> pd.DataFrame:
    suffix = " TR %" if return_series == "Total return" else " Price %"
    rows = catalog.loc[
        catalog["category"].astype("string").str.strip().isin(FUND_CATEGORIES)
        & catalog["header"].astype("string").str.endswith(suffix, na=False)
    ].copy()
    rows["isin"] = rows["id"].astype("string").str.strip()
    rows = rows.loc[rows["isin"].str.len() > 0]
    if selected_isins is not None:
        rows = rows.loc[rows["isin"].isin(selected_isins)]
    return rows.reset_index(drop=True)


def selected_isins_from_workbook(workbook: Path | pd.ExcelFile) -> set[str] | None:
    for sheet in ("Funds", "Funds final"):
        try:
            funds = pd.read_excel(workbook, sheet_name=sheet, engine="openpyxl")
        except ValueError:
            continue
        mask = _selection_mask(funds)
        if mask is None:
            continue
        isin_col = _isin_column(funds)
        chosen = funds.loc[mask, isin_col].astype("string").str.strip()
        return set(chosen.tolist())
    return None


def _aligned_daily_sample(
    daily: pd.DataFrame,
    fund_header: str,
    bench_header: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[np.ndarray, np.ndarray]:
    window = daily.loc[(daily.index >= start) & (daily.index <= end), [fund_header, bench_header]]
    fund = pd.to_numeric(window[fund_header], errors="coerce")
    bench = pd.to_numeric(window[bench_header], errors="coerce")
    paired = pd.concat([fund, bench], axis=1).dropna()
    return (
        paired.iloc[:, 0].to_numpy(dtype=float),
        paired.iloc[:, 1].to_numpy(dtype=float),
    )


def build_fund_regression_table(
    workbook: Path | pd.ExcelFile,
    params: AnalysisParameters,
    *,
    sheet_name: str = CORRECTED_SHEET,
) -> pd.DataFrame:
    if isinstance(workbook, Path):
        book = pd.ExcelFile(workbook, engine="openpyxl")
    else:
        book = workbook
    raw = load_daily_timeseries_raw(book, sheet_name=sheet_name)
    daily, _ = load_daily_return_panel(raw)
    catalog = parse_daily_catalog(raw)
    selected = selected_isins_from_workbook(book)
    universe = fund_universe_from_catalog(
        catalog, return_series=params.return_series, selected_isins=selected
    )
    fees_map, aum_map = load_fund_metadata_by_isin(book)
    bench_header = params.benchmark_return_header
    rows: list[dict[str, Any]] = []
    for record in universe.itertuples(index=False):
        isin = str(record.isin)
        fund_header = str(record.header).strip()
        if fund_header not in daily.columns or bench_header not in daily.columns:
            continue
        fund_y, bench_x = _aligned_daily_sample(
            daily, fund_header, bench_header, params.start_date, params.end_date
        )
        fees = fees_map.get(isin, float("nan"))
        aum = aum_map.get(isin, float("nan"))
        stats = fit_daily_fund_benchmark_regression(
            fund_y,
            bench_x,
            trading_days_per_year=params.trading_days_per_year,
            fees_pct=fees,
        )
        category, etf, active, cross = category_flags(str(record.category))
        net_alpha = stats["Net alpha (%/yr)"]
        rows.append(
            {
                "Fund": isin,
                "Category": category,
                "ETF": etf,
                "Active": active,
                "ETF×Active": cross,
                "Fees (%)": fees,
                "AUM": aum,
                **stats,
                "Selected Y": net_alpha,
            }
        )
    frame = pd.DataFrame(rows, columns=FUND_TABLE_COLUMNS)
    return frame


def _filter_group(frame: pd.DataFrame, active: int | None, etf: int | None) -> pd.DataFrame:
    subset = frame
    if active is not None:
        subset = subset.loc[subset["Active"].eq(active)]
    if etf is not None:
        subset = subset.loc[subset["ETF"].eq(etf)]
    return subset


def _stat_value(series: pd.Series, statistic: str) -> float | str:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return "–"
    if statistic == "Mean":
        return float(values.mean())
    if statistic == "Median":
        return float(values.median())
    if statistic == "Std dev":
        return float(values.std(ddof=1)) if len(values) > 1 else float("nan")
    if statistic == "Variance":
        return float(values.var(ddof=1)) if len(values) > 1 else float("nan")
    if statistic == "Min":
        return float(values.min())
    if statistic == "Max":
        return float(values.max())
    raise KeyError(statistic)


def _overview_value(frame: pd.DataFrame, statistic: str) -> float | str:
    if frame.empty:
        return "–"
    if statistic == "Number of funds":
        return float(len(frame))
    if statistic == "Avg trading days of data":
        return float(frame["Trading days"].mean())
    if statistic == "% net alpha > 0":
        alpha = pd.to_numeric(frame["Net alpha (%/yr)"], errors="coerce")
        valid = alpha.dropna()
        if valid.empty:
            return "–"
        return float((valid > 0).mean() * 100.0)
    if statistic == "% gross alpha > 0":
        gross = pd.to_numeric(frame["Gross alpha (%/yr)"], errors="coerce")
        valid = gross.dropna()
        if valid.empty:
            return "–"
        return float((valid > 0).mean() * 100.0)
    raise KeyError(statistic)


def build_consolidated_group_stats(fund_table: pd.DataFrame) -> pd.DataFrame:
    """Long table: Indicator, Statistic, plus one column per Consolidation group."""
    group_names = [name for name, _, _ in _CONSOLIDATION_GROUPS]
    outlines: list[dict[str, Any]] = []

    overview_stats = [
        "Number of funds",
        "Avg trading days of data",
        "% net alpha > 0",
        "% gross alpha > 0",
    ]
    for stat in overview_stats:
        row: dict[str, Any] = {"Indicator": "Overview", "Statistic": stat}
        for name, active, etf in _CONSOLIDATION_GROUPS:
            subset = _filter_group(fund_table, active, etf)
            row[name] = _overview_value(subset, stat)
        outlines.append(row)

    stat_names = ["Mean", "Median", "Std dev", "Variance", "Min", "Max"]
    for metric in _METRIC_COLUMNS_FOR_STATS:
        for stat in stat_names:
            row = {"Indicator": metric, "Statistic": stat}
            for name, active, etf in _CONSOLIDATION_GROUPS:
                subset = _filter_group(fund_table, active, etf)
                if subset.empty or metric not in subset.columns:
                    row[name] = "–"
                else:
                    row[name] = _stat_value(subset[metric], stat)
            outlines.append(row)

    columns = ["Indicator", "Statistic", *group_names]
    return pd.DataFrame(outlines, columns=columns)


def _round_display_value(
    val: Any,
    *,
    decimals: int,
    as_whole_number: bool,
) -> Any:
    if val is None:
        return val
    text = str(val).strip()
    if text in {"", "–"}:
        return val
    num = pd.to_numeric(val, errors="coerce")
    if pd.isna(num):
        return val
    if as_whole_number:
        return int(round(float(num)))
    return round(float(num), decimals)


def format_table_figures(
    frame: pd.DataFrame,
    *,
    decimals: int = DISPLAY_DECIMALS,
) -> pd.DataFrame:
    """Round numeric table cells for display (max ``decimals`` after the decimal point)."""
    out = frame.copy()
    is_fund_table = "Fund" in out.columns
    count_row = (
        out["Statistic"].eq("Number of funds")
        if "Statistic" in out.columns
        else pd.Series(False, index=out.index)
    )
    for col in out.columns:
        if col in _TEXT_TABLE_COLUMNS:
            continue
        if is_fund_table and col in _INT_TABLE_COLUMNS:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
            continue
        if is_fund_table and col == "Trading days":
            out[col] = pd.to_numeric(out[col], errors="coerce").round(0).astype("Int64")
            continue
        for idx in out.index:
            out.at[idx, col] = _round_display_value(
                out.at[idx, col],
                decimals=decimals,
                as_whole_number=bool(count_row.at[idx]),
            )
    return out


def load_daily_panel_and_catalog(
    workbook: Path | pd.ExcelFile,
    *,
    sheet_name: str = CORRECTED_SHEET,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    book = workbook
    raw = load_daily_timeseries_raw(book, sheet_name=sheet_name)
    daily, _ = load_daily_return_panel(raw)
    catalog = parse_daily_catalog(raw)
    return daily, catalog


def default_workbook_path() -> Path:
    return find_output_data_file(DEFAULT_WORKBOOK_FILENAME)


__all__ = [
    "AnalysisParameters",
    "RETURN_SERIES_CHOICES",
    "DEFAULT_BENCHMARK_NAME",
    "DEFAULT_TRADING_DAYS_PER_YEAR",
    "FUND_TABLE_COLUMNS",
    "benchmark_return_header_for_name",
    "DISPLAY_DECIMALS",
    "build_consolidated_group_stats",
    "build_fund_regression_table",
    "default_workbook_path",
    "fit_daily_fund_benchmark_regression",
    "format_table_figures",
    "list_benchmark_name_choices",
    "load_daily_panel_and_catalog",
    "load_funds_reference",
    "resolve_analysis_parameters",
]