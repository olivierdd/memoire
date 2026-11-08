from pathlib import Path

import numpy as np
import pandas as pd

from helpers.timeseries_functions.compute_fund_to_index_regression import (
    FundIndexRegressionResult,
    compute_fund_to_index_regression,
)
from helpers.timeseries_functions.load_consolidation_regression import (
    load_consolidation_fund_regression_reference,
    load_consolidation_regression_window,
)


def _slice_consolidation_window(
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    dates = pd.to_datetime(fund_timeseries["Date"])
    mask = (dates >= start) & (dates <= end)
    return fund_timeseries.loc[mask].dropna(subset=[index_column, master_column])


def _consolidation_percent_decimal(raw: float) -> float:
    if pd.isna(raw):
        return float("nan")
    return float(raw) / 100.0


def build_consolidation_comparison_rows(
    window_result: FundIndexRegressionResult,
    consolidation_row: pd.Series,
) -> list[dict]:
    """Long-form rows: notebook OLS vs Consolidation reference (same units)."""
    fees_pct = float(consolidation_row.get("Fees (%)", np.nan))
    fees_decimal = _consolidation_percent_decimal(fees_pct)
    gross_notebook = window_result.regression["alpha_annualized"]
    if pd.notna(fees_decimal):
        gross_notebook = gross_notebook + fees_decimal

    specs: list[tuple[str, float, float, str, str, str]] = [
        (
            "Months",
            float(window_result.n_months),
            float(consolidation_row.get("Months", np.nan)),
            "{:.0f}",
            "{:.0f}",
            "{:.0f}",
        ),
        (
            "Beta",
            window_result.beta,
            float(consolidation_row.get("Beta", np.nan)),
            "{:.6f}",
            "{:.6f}",
            "{:.6f}",
        ),
        (
            "Tracking error (annualized)",
            window_result.regression["residual_volatility"],
            _consolidation_percent_decimal(
                consolidation_row.get("Tracking error (%)")
            ),
            "{:.4%}",
            "{:.4%}",
            "{:.4%}",
        ),
        (
            "Excess return (annualized)",
            window_result.regression["excess_annualized"],
            _consolidation_percent_decimal(
                consolidation_row.get("Excess return (%/yr)")
            ),
            "{:.4%}",
            "{:.4%}",
            "{:.4%}",
        ),
        (
            "Net alpha (annualized)",
            window_result.regression["alpha_annualized"],
            _consolidation_percent_decimal(consolidation_row.get("Net alpha (%/yr)")),
            "{:.4%}",
            "{:.4%}",
            "{:.4%}",
        ),
        (
            "Gross alpha (annualized)",
            gross_notebook,
            _consolidation_percent_decimal(
                consolidation_row.get("Gross alpha (%/yr)")
            ),
            "{:.4%}",
            "{:.4%}",
            "{:.4%}",
        ),
        (
            "Information ratio",
            window_result.regression["information_ratio"],
            float(consolidation_row.get("Information ratio", np.nan)),
            "{:.6f}",
            "{:.6f}",
            "{:.6f}",
        ),
    ]

    rows: list[dict] = []
    for metric, computed, reference, nb_fmt, ref_fmt, delta_fmt in specs:
        delta = (
            computed - reference
            if pd.notna(computed) and pd.notna(reference)
            else np.nan
        )
        rows.append(
            {
                "Metric": metric,
                "Notebook": nb_fmt.format(computed) if pd.notna(computed) else "",
                "Consolidation": ref_fmt.format(reference)
                if pd.notna(reference)
                else "",
                "Delta (notebook − Consolidation)": delta_fmt.format(delta)
                if pd.notna(delta)
                else "",
            }
        )
    return rows


def compare_regression_to_consolidation(
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
    consolidation_row: pd.Series | None = None,
    window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    consolidation_sheet: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Side-by-side notebook OLS vs Consolidation sheet on the AE6–AE5 window."""
    _ = regression_result  # full-sample result kept for API symmetry with Lipper helper
    if window is None:
        start, end = load_consolidation_regression_window(relative, filename)
    else:
        start, end = window
    if consolidation_row is None:
        consolidation_row = load_consolidation_fund_regression_reference(
            isin,
            relative,
            filename,
            consolidation_sheet=consolidation_sheet,
        )
    window = _slice_consolidation_window(
        fund_timeseries, index_column, master_column, start, end
    )
    if len(window) < 3:
        raise ValueError(
            f"Need at least 3 months in Consolidation window {start.date()}–{end.date()}"
        )

    window_result = compute_fund_to_index_regression(
        window,
        index_column,
        master_column,
        fund_name=fund_name,
        master_timeseries=master_timeseries,
        quiet=True,
    )
    rows = build_consolidation_comparison_rows(window_result, consolidation_row)
    comparison = pd.DataFrame(rows)
    comparison.insert(0, "Months", window_result.n_months)
    comparison.insert(
        0,
        "Window",
        f"{start:%Y-%m-%d} to {end:%Y-%m-%d}",
    )

    print(
        f"Consolidation window: {start:%Y-%m-%d} to {end:%Y-%m-%d} "
        f"({window_result.n_months} months)."
    )
    print(
        "Consolidation uses Lipper fund returns from Timeseries vs the index column "
        "(Timeseries column E in Excel; here the notebook index column). "
        "Notebook OLS is rerun on the same date window. "
        "The regression cell above uses all available months unless the window matches."
    )
    return comparison
