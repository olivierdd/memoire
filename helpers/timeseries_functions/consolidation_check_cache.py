"""Load or compute Consolidation regression comparison for export and checks."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.compare_regression_to_consolidation import (
    compare_regression_to_consolidation,
)
from helpers.timeseries_functions.compute_fund_to_index_regression import (
    compute_fund_to_index_regression,
)
from helpers.timeseries_functions.load_consolidation_regression import (
    load_consolidation_fund_regression_reference,
    load_consolidation_regression_window,
)
from helpers.timeseries_functions.regression_delta_parse import parse_regression_delta
from helpers.timeseries_functions.timeseries_check_bundle import frame_csv

CONSOLIDATION_CSV = "outputs/consolidation-regression-comparison.csv"
DEFAULT_WORKBOOK_RELATIVE = Path("input-data-alix") / "clean"
DEFAULT_WORKBOOK_FILENAME = "CLEAN_RECOLTE DONNEES-EXCEL.xlsx"

__all__ = [
    "CONSOLIDATION_CSV",
    "apply_consolidation_comparison_to_row",
    "ensure_consolidation_comparison_csv",
    "parse_consolidation_comparison_csv",
]


def parse_consolidation_comparison_csv(consol_df: pd.DataFrame) -> dict[str, object]:
    """Extract export columns from long-form consolidation comparison."""
    row: dict[str, object] = {
        "consol_window": None,
        "consol_delta_beta": None,
        "consol_delta_net_alpha": None,
        "consol_delta_te": None,
        "consol_delta_ir": None,
    }
    if consol_df.empty:
        return row
    row["consol_window"] = consol_df.iloc[0].get("Window")
    for _, crow in consol_df.iterrows():
        metric = str(crow.get("Metric", "")).strip()
        delta_raw = crow.get("Delta (notebook − Consolidation)")
        delta = parse_regression_delta(metric, delta_raw)
        if metric == "Beta":
            row["consol_delta_beta"] = delta
        elif metric == "Net alpha (annualized)":
            row["consol_delta_net_alpha"] = delta
        elif metric == "Tracking error (annualized)":
            row["consol_delta_te"] = delta
        elif metric == "Information ratio":
            row["consol_delta_ir"] = delta
    return row


def ensure_consolidation_comparison_csv(
    isin_dir: Path,
    isin: str,
    *,
    consolidation_sheet: pd.DataFrame | None = None,
    window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    workbook_relative: Path = DEFAULT_WORKBOOK_RELATIVE,
    workbook_filename: str = DEFAULT_WORKBOOK_FILENAME,
    write_cache: bool = True,
) -> pd.DataFrame | None:
    """Return comparison CSV contents, computing from check inputs if missing."""
    isin_dir = isin_dir.resolve()
    out_path = isin_dir / CONSOLIDATION_CSV
    if out_path.is_file():
        return pd.read_csv(out_path)

    params_path = isin_dir / "inputs" / "parameters.json"
    ts_path = isin_dir / "inputs" / "fund-timeseries.csv"
    static_path = isin_dir / "inputs" / "fund-static.json"
    if not params_path.is_file() or not ts_path.is_file():
        return None

    params = json.loads(params_path.read_text(encoding="utf-8"))
    fund_name = "Fund"
    if static_path.is_file():
        static = json.loads(static_path.read_text(encoding="utf-8"))
        fund_name = str(static.get("name") or fund_name)

    fund_timeseries = pd.read_csv(ts_path, parse_dates=["Date"])
    index_column = params["index_column"]
    master_column = params["master_column"]
    master_timeseries = params.get("master_timeseries", "Lipper")

    try:
        regression_result = compute_fund_to_index_regression(
            fund_timeseries,
            index_column,
            master_column,
            fund_name=fund_name,
            master_timeseries=master_timeseries,
            quiet=True,
        )
        consolidation_row = None
        if consolidation_sheet is not None:
            consolidation_row = load_consolidation_fund_regression_reference(
                isin,
                workbook_relative,
                workbook_filename,
                consolidation_sheet=consolidation_sheet,
            )
        with redirect_stdout(io.StringIO()):
            comparison = compare_regression_to_consolidation(
                regression_result,
                fund_timeseries,
                index_column,
                master_column,
                isin,
                workbook_relative,
                workbook_filename,
                fund_name=fund_name,
                master_timeseries=master_timeseries,
                consolidation_row=consolidation_row,
                window=window,
            )
    except (KeyError, ValueError):
        return None

    if write_cache:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(frame_csv(comparison), encoding="utf-8")
    return comparison


def apply_consolidation_comparison_to_row(
    row: dict[str, object],
    consol_df: pd.DataFrame | None,
    *,
    consolidation_regression_result_label,
) -> None:
    parsed = parse_consolidation_comparison_csv(
        consol_df if consol_df is not None else pd.DataFrame()
    )
    row.update(parsed)
    row["consol_regression_result"] = consolidation_regression_result_label(
        {
            "beta": parsed.get("consol_delta_beta"),
            "net_alpha": parsed.get("consol_delta_net_alpha"),
            "te": parsed.get("consol_delta_te"),
            "ir": parsed.get("consol_delta_ir"),
        }
    )
