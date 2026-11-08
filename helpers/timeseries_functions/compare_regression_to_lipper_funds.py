from pathlib import Path

import numpy as np
import pandas as pd

from helpers.timeseries_functions.compute_fund_to_index_regression import (
    FundIndexRegressionResult,
    compute_fund_to_index_regression,
)
from helpers.timeseries_functions.load_workbook import find_workbook

DEFAULT_LIPPER_HORIZON_YEARS = (3, 5, 10)

# Lipper Funds sheet: Alpha = monthly intercept in percent; Beta and R² are decimals;
# Annualised Tracking Error = annualized percent.
_LIPPER_SUFFIX = " to Last Month End"


def _lipper_horizon_columns(years: int) -> dict[str, str]:
    label = f"{years} Years"
    return {
        "alpha": f"Alpha for {label}{_LIPPER_SUFFIX}",
        "beta": f"Beta for {label}{_LIPPER_SUFFIX}",
        "r_squared": f"R-Squared for {label}{_LIPPER_SUFFIX}",
        "tracking_error": f"Annualised Tracking Error for {label}{_LIPPER_SUFFIX}",
    }


def load_lipper_fund_regression_reference(
    isin: str,
    relative: Path,
    filename: str,
) -> pd.Series:
    """One Funds-sheet row for ``isin`` (raises if missing)."""
    workbook = find_workbook(relative, filename)
    funds = pd.read_excel(workbook, sheet_name="Funds", engine="openpyxl")
    match = funds.loc[funds["ISIN"].astype(str).eq(isin)]
    if match.empty:
        raise KeyError(f"ISIN {isin} not found on Funds sheet")
    return match.iloc[0]


def _slice_horizon(
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    years: int,
) -> pd.DataFrame:
    end = fund_timeseries["Date"].max()
    start = end - pd.DateOffset(years=years)
    return fund_timeseries.loc[fund_timeseries["Date"] > start].dropna(
        subset=[index_column, master_column]
    )


def _lipper_alpha_decimal(raw: float) -> float:
    if pd.isna(raw):
        return float("nan")
    return float(raw) / 100.0


def _lipper_tracking_error_decimal(raw: float) -> float:
    if pd.isna(raw):
        return float("nan")
    return float(raw) / 100.0


def compare_regression_to_lipper_funds(
    regression_result: FundIndexRegressionResult,
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    isin: str,
    relative: Path,
    filename: str,
    *,
    fund_name: str,
    master_timeseries: str = "Lipper",
    horizon_years: tuple[int, ...] = DEFAULT_LIPPER_HORIZON_YEARS,
) -> pd.DataFrame:
    """Side-by-side notebook OLS vs Lipper Funds-sheet stats by horizon."""
    lipper_row = load_lipper_fund_regression_reference(isin, relative, filename)
    benchmark = lipper_row.get("Benchmark Name", "")

    rows: list[dict] = []

    def add_row(
        horizon: str,
        n_months: int,
        metric: str,
        computed: float,
        lipper: float,
        *,
        computed_fmt: str,
        lipper_fmt: str,
        delta_fmt: str,
    ) -> None:
        delta = computed - lipper if pd.notna(computed) and pd.notna(lipper) else np.nan
        rows.append(
            {
                "Horizon": horizon,
                "Months": n_months,
                "Metric": metric,
                "Notebook": computed_fmt.format(computed)
                if pd.notna(computed)
                else "",
                "Lipper Funds": lipper_fmt.format(lipper) if pd.notna(lipper) else "",
                "Delta (notebook − Lipper)": delta_fmt.format(delta)
                if pd.notna(delta)
                else "",
            }
        )

    full = regression_result
    add_row(
        "All available",
        full.n_months,
        "Alpha (monthly)",
        full.alpha,
        np.nan,
        computed_fmt="{:.4%}",
        lipper_fmt="{:.4%}",
        delta_fmt="{:.4%}",
    )
    add_row(
        "All available",
        full.n_months,
        "Alpha (annualized, ×12)",
        full.regression["alpha_annualized"],
        np.nan,
        computed_fmt="{:.2%}",
        lipper_fmt="{:.2%}",
        delta_fmt="{:.2%}",
    )
    add_row(
        "All available",
        full.n_months,
        "Beta",
        full.beta,
        np.nan,
        computed_fmt="{:.3f}",
        lipper_fmt="{:.3f}",
        delta_fmt="{:.3f}",
    )
    add_row(
        "All available",
        full.n_months,
        "R²",
        full.r_squared,
        np.nan,
        computed_fmt="{:.3f}",
        lipper_fmt="{:.3f}",
        delta_fmt="{:.3f}",
    )
    add_row(
        "All available",
        full.n_months,
        "Correlation",
        full.regression["correlation"],
        np.nan,
        computed_fmt="{:.3f}",
        lipper_fmt="{:.3f}",
        delta_fmt="{:.3f}",
    )
    add_row(
        "All available",
        full.n_months,
        "Annualized excess return",
        full.regression["excess_annualized"],
        np.nan,
        computed_fmt="{:.2%}",
        lipper_fmt="{:.2%}",
        delta_fmt="{:.2%}",
    )
    add_row(
        "All available",
        full.n_months,
        "Annualized tracking error",
        full.regression["residual_volatility"],
        np.nan,
        computed_fmt="{:.2%}",
        lipper_fmt="{:.2%}",
        delta_fmt="{:.2%}",
    )
    add_row(
        "All available",
        full.n_months,
        "Information ratio",
        full.regression["information_ratio"],
        np.nan,
        computed_fmt="{:.2f}",
        lipper_fmt="{:.2f}",
        delta_fmt="{:.2f}",
    )

    for years in horizon_years:
        horizon_label = f"{years}y to last month end"
        cols = _lipper_horizon_columns(years)
        window = _slice_horizon(fund_timeseries, index_column, master_column, years)
        if len(window) < 3:
            continue

        window_result = compute_fund_to_index_regression(
            window,
            index_column,
            master_column,
            fund_name=fund_name,
            master_timeseries=master_timeseries,
            quiet=True,
        )

        lipper_alpha = _lipper_alpha_decimal(lipper_row.get(cols["alpha"]))
        lipper_beta = float(lipper_row.get(cols["beta"], np.nan))
        lipper_r2 = float(lipper_row.get(cols["r_squared"], np.nan))
        lipper_te = _lipper_tracking_error_decimal(lipper_row.get(cols["tracking_error"]))

        n = window_result.n_months
        add_row(
            horizon_label,
            n,
            "Alpha (monthly)",
            window_result.alpha,
            lipper_alpha,
            computed_fmt="{:.4%}",
            lipper_fmt="{:.4%}",
            delta_fmt="{:.4%}",
        )
        add_row(
            horizon_label,
            n,
            "Beta",
            window_result.beta,
            lipper_beta,
            computed_fmt="{:.3f}",
            lipper_fmt="{:.3f}",
            delta_fmt="{:.3f}",
        )
        add_row(
            horizon_label,
            n,
            "R²",
            window_result.r_squared,
            lipper_r2,
            computed_fmt="{:.3f}",
            lipper_fmt="{:.3f}",
            delta_fmt="{:.3f}",
        )
        add_row(
            horizon_label,
            n,
            "Annualized tracking error",
            window_result.regression["residual_volatility"],
            lipper_te,
            computed_fmt="{:.2%}",
            lipper_fmt="{:.2%}",
            delta_fmt="{:.2%}",
        )

    comparison = pd.DataFrame(rows)
    print(f"Lipper Funds benchmark: {benchmark}")
    print(
        "Compare fixed horizons (3y / 5y / 10y) to Lipper columns on the Funds sheet. "
        "Lipper Alpha is stored as monthly percent (÷100 → decimal); "
        "tracking error is annualized percent. "
        "Same OLS as above, no risk-free rate."
    )
    return comparison
