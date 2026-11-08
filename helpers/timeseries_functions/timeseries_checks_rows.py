"""Build tabular rows for the timeseries-checks export sheet."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from helpers.timeseries_functions.consolidation_check_cache import (
    DEFAULT_WORKBOOK_FILENAME,
    DEFAULT_WORKBOOK_RELATIVE,
    apply_consolidation_comparison_to_row,
    ensure_consolidation_comparison_csv,
)
from helpers.timeseries_functions.load_consolidation_regression import (
    load_consolidation_regression_window,
    load_consolidation_sheet,
)
from helpers.timeseries_functions.save_timeseries_check import find_project_root
from helpers.timeseries_functions.regression_delta_parse import parse_regression_delta
from helpers.timeseries_functions.series_check_summary import (
    load_quality_summaries,
    quality_result_label,
)

ColumnKind = Literal["text", "bool", "number", "result", "wrap"]

# Lipper Funds horizon deltas (see regression_delta_parse for units).
LIPPER_DELTA_BETA_MAX = 0.05
LIPPER_DELTA_R2_MAX = 0.05
LIPPER_DELTA_ALPHA_MO_MAX_PP = 0.05  # pp/mo (~5 bp/mo)
LIPPER_DELTA_TE_MAX_PP = 0.5  # annualized pp (0.5% tracking-error gap)

# Consolidation sheet reproduction (tight; same Lipper window as Excel).
CONSOL_DELTA_BETA_IR_MAX = 1e-4
CONSOL_DELTA_PERCENT_PP_MAX = 0.01  # 1 bp on annualized % metrics

_HORIZON_KEYS = {
    "3y to last month end": "3y",
    "5y to last month end": "5y",
    "10y to last month end": "10y",
}


@dataclass(frozen=True)
class ColumnSpec:
    family: str
    header: str
    key: str
    width: float
    kind: ColumnKind = "text"


def _quality_columns(prefix: str, family: str) -> list[ColumnSpec]:
    p = prefix
    return [
        ColumnSpec(family, "Gaps", f"{p}_gap_count", 8, "number"),
        ColumnSpec(family, "Spikes", f"{p}_spike_count", 8, "number"),
        ColumnSpec(family, "Scale shift", f"{p}_scale_shift", 10, "bool"),
        ColumnSpec(family, "Scale shift date", f"{p}_scale_shift_date", 14),
        ColumnSpec(family, "Level jumps", f"{p}_level_jump_count", 10, "number"),
        ColumnSpec(family, "Index div.", f"{p}_index_divergence_count", 10, "number"),
        ColumnSpec(family, "Largest gap (bp)", f"{p}_largest_gap_bp", 12, "number"),
        ColumnSpec(family, "Largest gap date", f"{p}_largest_gap_date", 14),
        ColumnSpec(family, "Result", f"{p}_quality_result", 14, "result"),
    ]


COLUMN_FAMILIES: list[ColumnSpec] = [
    ColumnSpec("Fund (Lipper)", "ISIN", "lipper_isin", 16),
    ColumnSpec("Fund (Lipper)", "Name", "lipper_name", 43),
    ColumnSpec("Fund (Lipper)", "fund_wrapper", "fund_wrapper", 14),
    ColumnSpec("Fund (Lipper)", "fund_type", "fund_type", 12),
    ColumnSpec("", "", "_gap1", 1.5),
    ColumnSpec("Check: Lipper vs Yahoo", "Months compared", "yahoo_n_months", 10, "number"),
    ColumnSpec("Check: Lipper vs Yahoo", "Perfect matches", "yahoo_perfect", 10, "number"),
    ColumnSpec(
        "Check: Lipper vs Yahoo", "Acceptable matches", "yahoo_acceptable", 12, "number"
    ),
    ColumnSpec("Check: Lipper vs Yahoo", "Mismatches", "yahoo_mismatches", 10, "number"),
    ColumnSpec(
        "Check: Lipper vs Yahoo", "Shifted dates", "yahoo_shifted_dates", 10, "number"
    ),
    ColumnSpec(
        "Check: Lipper vs Yahoo", "One-side missing", "yahoo_one_side_missing", 12, "number"
    ),
    ColumnSpec("Check: Lipper vs Yahoo", "Worst gap (bp)", "yahoo_worst_gap_bp", 12, "number"),
    ColumnSpec("Check: Lipper vs Yahoo", "Worst gap date", "yahoo_worst_gap_date", 14),
    ColumnSpec(
        "Check: Lipper vs Yahoo",
        "Nearby session OK",
        "yahoo_nearby_within_tolerance",
        12,
        "bool",
    ),
    ColumnSpec("Check: Lipper vs Yahoo", "Date mismatch", "yahoo_date_mismatch", 12, "bool"),
    ColumnSpec("Check: Lipper vs Yahoo", "Result", "yahoo_result", 14, "result"),
    ColumnSpec(
        "Check: Lipper vs Yahoo",
        "Drilldown conclusion",
        "yahoo_drilldown_conclusion",
        48,
        "wrap",
    ),
    ColumnSpec("", "", "_gap2", 1.5),
    *_quality_columns("lipper", "Check: Lipper quality"),
    ColumnSpec("", "", "_gap3", 1.5),
    *_quality_columns("yahoo", "Check: Yahoo quality"),
    ColumnSpec("", "", "_gap4", 1.5),
    ColumnSpec("Check: regression", "Index", "reg_index", 14),
    ColumnSpec("Check: regression", "Sample start", "reg_start", 12),
    ColumnSpec("Check: regression", "Sample end", "reg_end", 12),
    ColumnSpec("Check: regression", "Months", "reg_n_months", 8, "number"),
    ColumnSpec("Check: regression", "Alpha (bp/mo)", "reg_alpha_bp", 12, "number"),
    ColumnSpec("Check: regression", "Beta", "reg_beta", 8, "number"),
    ColumnSpec("Check: regression", "R²", "reg_r_squared", 8, "number"),
    ColumnSpec("Check: regression", "Equation", "reg_equation", 40, "wrap"),
    ColumnSpec("", "", "_gap5", 1.5),
    ColumnSpec("Check: vs Lipper Funds", "Δ Beta (3y)", "lipper_delta_beta_3y", 10, "number"),
    ColumnSpec("Check: vs Lipper Funds", "Δ Beta (5y)", "lipper_delta_beta_5y", 10, "number"),
    ColumnSpec("Check: vs Lipper Funds", "Δ Beta (10y)", "lipper_delta_beta_10y", 10, "number"),
    ColumnSpec(
        "Check: vs Lipper Funds", "Δ Alpha mo (3y)", "lipper_delta_alpha_3y", 12, "number"
    ),
    ColumnSpec(
        "Check: vs Lipper Funds", "Δ Alpha mo (5y)", "lipper_delta_alpha_5y", 12, "number"
    ),
    ColumnSpec(
        "Check: vs Lipper Funds", "Δ Alpha mo (10y)", "lipper_delta_alpha_10y", 12, "number"
    ),
    ColumnSpec("Check: vs Lipper Funds", "Δ R² (3y)", "lipper_delta_r2_3y", 10, "number"),
    ColumnSpec("Check: vs Lipper Funds", "Δ R² (5y)", "lipper_delta_r2_5y", 10, "number"),
    ColumnSpec("Check: vs Lipper Funds", "Δ R² (10y)", "lipper_delta_r2_10y", 10, "number"),
    ColumnSpec("Check: vs Lipper Funds", "Δ TE (3y)", "lipper_delta_te_3y", 10, "number"),
    ColumnSpec("Check: vs Lipper Funds", "Δ TE (5y)", "lipper_delta_te_5y", 10, "number"),
    ColumnSpec("Check: vs Lipper Funds", "Δ TE (10y)", "lipper_delta_te_10y", 10, "number"),
    ColumnSpec(
        "Check: vs Lipper Funds", "Result", "lipper_regression_result", 14, "result"
    ),
    ColumnSpec("", "", "_gap6", 1.5),
    ColumnSpec("Check: vs Consolidation", "Window", "consol_window", 28),
    ColumnSpec("Check: vs Consolidation", "Δ Beta", "consol_delta_beta", 10, "number"),
    ColumnSpec(
        "Check: vs Consolidation", "Δ Net alpha", "consol_delta_net_alpha", 12, "number"
    ),
    ColumnSpec("Check: vs Consolidation", "Δ TE", "consol_delta_te", 10, "number"),
    ColumnSpec("Check: vs Consolidation", "Δ IR", "consol_delta_ir", 10, "number"),
    ColumnSpec(
        "Check: vs Consolidation", "Result", "consol_regression_result", 14, "result"
    ),
    ColumnSpec("", "", "_gap7", 1.5),
    ColumnSpec("Decision", "Include fund", "decision_include", 12, "bool"),
    ColumnSpec(
        "Decision", "Excluded months (summary)", "decision_exclude_summary", 36, "wrap"
    ),
    ColumnSpec("Decision", "Excluded month count", "decision_exclude_count", 12, "number"),
]

DATA_COLUMN_KEYS = [c.key for c in COLUMN_FAMILIES if not c.key.startswith("_gap")]

EXCLUSIONS_COLUMNS = ["ISIN", "Name", "Period", "Date", "Exclude"]

__all__ = [
    "COLUMN_FAMILIES",
    "DATA_COLUMN_KEYS",
    "EXCLUSIONS_COLUMNS",
    "build_regression_exclusions_rows",
    "build_timeseries_checks_rows",
    "discover_check_isins",
    "yahoo_result_label",
    "lipper_regression_result_label",
    "consolidation_regression_result_label",
]


def _cell(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    return text if text else None


def _normalize_isin(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip().upper()


def discover_check_isins(checks_root: Path | None = None) -> list[str]:
    root = checks_root or (find_project_root() / "output-data" / "timeseries-checks")
    if not root.is_dir():
        return []
    isins: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            isins.append(child.name)
    return isins


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def yahoo_result_label(
    summary: dict[str, Any] | None,
    worst: dict[str, Any] | None,
) -> str:
    if summary is None:
        return "Not comparable"
    n_months = int(summary.get("n_months") or 0)
    if n_months == 0:
        return "Not comparable"
    mismatches = int(summary.get("mismatches") or 0)
    if mismatches == 0:
        return "Match"
    if worst is None:
        return "Mismatch"
    within = bool(worst.get("within_tolerance"))
    date_mismatch = bool(worst.get("date_mismatch"))
    if within or date_mismatch:
        return "Date alignment"
    return "Mismatch"


def _lipper_horizon_deltas(comparison: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    out: dict[str, dict[str, float | None]] = {
        "3y": {},
        "5y": {},
        "10y": {},
    }
    if comparison.empty:
        return out
    for _, row in comparison.iterrows():
        horizon = str(row.get("Horizon", "")).strip()
        key = _HORIZON_KEYS.get(horizon)
        if key is None:
            continue
        metric = str(row.get("Metric", "")).strip()
        delta = parse_regression_delta(metric, row.get("Delta (notebook − Lipper)"))
        lipper_val = row.get("Lipper Funds")
        if metric == "Beta":
            out[key]["beta"] = delta
            out[key]["has_lipper"] = lipper_val is not None and str(lipper_val).strip() != ""
        elif metric == "Alpha (monthly)":
            out[key]["alpha"] = delta
            if lipper_val is not None and str(lipper_val).strip():
                out[key]["has_lipper"] = True
        elif metric == "R²":
            out[key]["r2"] = delta
        elif metric == "Annualized tracking error":
            out[key]["te"] = delta
    return out


def lipper_regression_result_label(deltas: dict[str, dict[str, float | None]]) -> str:
    has_reference = any(d.get("has_lipper") for d in deltas.values())
    if not has_reference:
        return "Not comparable"
    betas: list[float] = []
    r2s: list[float] = []
    alphas: list[float] = []
    tes: list[float] = []
    for data in deltas.values():
        if data.get("beta") is not None:
            betas.append(abs(float(data["beta"])))
        if data.get("r2") is not None:
            r2s.append(abs(float(data["r2"])))
        if data.get("alpha") is not None:
            alphas.append(abs(float(data["alpha"])))
        if data.get("te") is not None:
            tes.append(abs(float(data["te"])))
    if not betas and not r2s and not alphas and not tes:
        return "Not comparable"
    if (
        (not betas or max(betas) <= LIPPER_DELTA_BETA_MAX)
        and (not r2s or max(r2s) <= LIPPER_DELTA_R2_MAX)
        and (not alphas or max(alphas) <= LIPPER_DELTA_ALPHA_MO_MAX_PP)
        and (not tes or max(tes) <= LIPPER_DELTA_TE_MAX_PP)
    ):
        return "Match"
    return "Mismatch"


def consolidation_regression_result_label(deltas: dict[str, float | None]) -> str:
    """Label notebook vs Consolidation tab (sheet reproduction, not external QA)."""
    beta = deltas.get("beta")
    net_alpha = deltas.get("net_alpha")
    te = deltas.get("te")
    ir = deltas.get("ir")
    if all(v is None for v in (beta, net_alpha, te, ir)):
        return "Not comparable"

    def _ok_percent(v: float | None) -> bool:
        return v is None or abs(v) <= CONSOL_DELTA_PERCENT_PP_MAX

    def _ok_unitless(v: float | None) -> bool:
        return v is None or abs(v) <= CONSOL_DELTA_BETA_IR_MAX

    if _ok_unitless(beta) and _ok_percent(net_alpha) and _ok_percent(te) and _ok_unitless(ir):
        return "Recreates sheet"
    return "Drifts from sheet"


def _apply_quality_prefix(row: dict[str, Any], prefix: str, summary: dict[str, Any]) -> None:
    row[f"{prefix}_gap_count"] = summary.get("gap_count")
    row[f"{prefix}_spike_count"] = summary.get("spike_count")
    row[f"{prefix}_scale_shift"] = summary.get("scale_shift")
    row[f"{prefix}_scale_shift_date"] = _cell(summary.get("scale_shift_date"))
    row[f"{prefix}_level_jump_count"] = summary.get("level_jump_count")
    row[f"{prefix}_index_divergence_count"] = summary.get("index_divergence_count")
    row[f"{prefix}_largest_gap_bp"] = summary.get("largest_gap_bp")
    row[f"{prefix}_largest_gap_date"] = _cell(summary.get("largest_gap_date"))
    if summary.get("gap_count") is None:
        row[f"{prefix}_quality_result"] = "Not comparable"
    else:
        row[f"{prefix}_quality_result"] = quality_result_label(summary)


def _row_for_isin(
    isin: str,
    isin_dir: Path,
    fund_row: pd.Series | None,
    *,
    consolidation_sheet: pd.DataFrame | None = None,
    consolidation_window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> dict[str, Any]:
    static = _read_json(isin_dir / "inputs" / "fund-static.json") or {}
    yahoo_summary = _read_json(isin_dir / "outputs" / "source-comparison-summary.json")
    worst = _read_json(isin_dir / "outputs" / "worst-mismatch-summary.json")
    regression = _read_json(isin_dir / "outputs" / "regression.json")

    name = _cell(static.get("name")) or (
        _cell(fund_row.get("Name")) if fund_row is not None else None
    )
    row: dict[str, Any] = {
        "lipper_isin": isin,
        "lipper_name": name,
        "fund_wrapper": _cell(static.get("fund_wrapper"))
        or (_cell(fund_row.get("fund_wrapper")) if fund_row is not None else None),
        "fund_type": _cell(static.get("fund_type"))
        or (_cell(fund_row.get("fund_type")) if fund_row is not None else None),
    }

    if yahoo_summary:
        row["yahoo_n_months"] = yahoo_summary.get("n_months")
        row["yahoo_perfect"] = yahoo_summary.get("perfect_matches")
        row["yahoo_acceptable"] = yahoo_summary.get("acceptable_matches")
        row["yahoo_mismatches"] = yahoo_summary.get("mismatches")
        row["yahoo_one_side_missing"] = yahoo_summary.get("one_side_missing")
    if worst:
        best_gap = worst.get("best_gap")
        row["yahoo_worst_gap_bp"] = (
            float(best_gap) * 1e4 if best_gap is not None else None
        )
        row["yahoo_worst_gap_date"] = _cell(worst.get("best_date"))
        row["yahoo_nearby_within_tolerance"] = worst.get("within_tolerance")
        row["yahoo_date_mismatch"] = worst.get("date_mismatch")
        row["yahoo_drilldown_conclusion"] = _cell(worst.get("conclusion"))
    row["yahoo_result"] = yahoo_result_label(yahoo_summary, worst)

    quality_path = isin_dir / "outputs" / "quality-summary.json"
    quality_doc = _read_json(quality_path) if quality_path.is_file() else None
    shifted = (quality_doc or {}).get("shifted_months") or {}
    row["yahoo_shifted_dates"] = shifted.get("count", 0)

    lipper_q, yahoo_q = load_quality_summaries(isin_dir, write_cache=True)
    _apply_quality_prefix(row, "lipper", lipper_q)
    _apply_quality_prefix(row, "yahoo", yahoo_q)

    if regression:
        stats = regression.get("statistics") or {}
        row["reg_index"] = _cell(regression.get("index_column"))
        row["reg_start"] = _cell(regression.get("start"))
        row["reg_end"] = _cell(regression.get("end"))
        row["reg_n_months"] = stats.get("n_months")
        alpha_bp = regression.get("alpha_bp_per_month")
        if alpha_bp is None and stats.get("alpha") is not None:
            alpha_bp = float(stats["alpha"]) * 1e4
        row["reg_alpha_bp"] = alpha_bp
        row["reg_beta"] = stats.get("beta")
        row["reg_r_squared"] = stats.get("r_squared")
        row["reg_equation"] = _cell(regression.get("equation"))

    lipper_path = isin_dir / "outputs" / "lipper-regression-comparison.csv"
    horizon_deltas: dict[str, dict[str, float | None]] = {
        "3y": {},
        "5y": {},
        "10y": {},
    }
    if lipper_path.is_file():
        lipper_df = pd.read_csv(lipper_path)
        horizon_deltas = _lipper_horizon_deltas(lipper_df)
    for h in ("3y", "5y", "10y"):
        data = horizon_deltas.get(h, {})
        row[f"lipper_delta_beta_{h}"] = data.get("beta")
        row[f"lipper_delta_alpha_{h}"] = data.get("alpha")
        row[f"lipper_delta_r2_{h}"] = data.get("r2")
        row[f"lipper_delta_te_{h}"] = data.get("te")
    row["lipper_regression_result"] = lipper_regression_result_label(horizon_deltas)

    consol_df = ensure_consolidation_comparison_csv(
        isin_dir,
        isin,
        consolidation_sheet=consolidation_sheet,
        window=consolidation_window,
        workbook_relative=DEFAULT_WORKBOOK_RELATIVE,
        workbook_filename=DEFAULT_WORKBOOK_FILENAME,
        write_cache=True,
    )
    apply_consolidation_comparison_to_row(
        row,
        consol_df,
        consolidation_regression_result_label=consolidation_regression_result_label,
    )

    row["decision_include"] = True
    row["decision_exclude_summary"] = None
    row["decision_exclude_count"] = 0
    return row


def build_timeseries_checks_rows(
    funds: pd.DataFrame,
    checks_root: Path | None = None,
) -> pd.DataFrame:
    """One export row per checked ISIN, ordered like ``funds`` when present."""
    root = checks_root or (find_project_root() / "output-data" / "timeseries-checks")
    check_isins = set(discover_check_isins(root))
    if not check_isins:
        return pd.DataFrame(columns=DATA_COLUMN_KEYS)

    fund_by_isin: dict[str, pd.Series] = {}
    order: list[str] = []
    for _, fund_row in funds.iterrows():
        isin = _normalize_isin(fund_row.get("ISIN"))
        if not isin:
            continue
        fund_by_isin[isin] = fund_row
        if isin in check_isins:
            order.append(isin)

    if not order and check_isins:
        order = sorted(check_isins)

    consolidation_sheet: pd.DataFrame | None = None
    consolidation_window: tuple[pd.Timestamp, pd.Timestamp] | None = None
    try:
        consolidation_sheet = load_consolidation_sheet(
            DEFAULT_WORKBOOK_RELATIVE,
            DEFAULT_WORKBOOK_FILENAME,
        )
        consolidation_window = load_consolidation_regression_window(
            DEFAULT_WORKBOOK_RELATIVE,
            DEFAULT_WORKBOOK_FILENAME,
        )
    except (FileNotFoundError, KeyError, ValueError):
        consolidation_sheet = None
        consolidation_window = None

    rows = [
        _row_for_isin(
            isin,
            root / isin,
            fund_by_isin.get(isin),
            consolidation_sheet=consolidation_sheet,
            consolidation_window=consolidation_window,
        )
        for isin in order
    ]
    return pd.DataFrame(rows)


def build_regression_exclusions_rows(
    funds: pd.DataFrame | None = None,
    checks_root: Path | None = None,
    *,
    main: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One row per regression-sample month for each checked fund."""
    root = checks_root or (find_project_root() / "output-data" / "timeseries-checks")
    if main is None:
        if funds is None:
            raise ValueError("Provide funds or main")
        main = build_timeseries_checks_rows(funds, checks_root=root)
    if main.empty:
        return pd.DataFrame(columns=EXCLUSIONS_COLUMNS)

    pieces: list[pd.DataFrame] = []
    for isin, name in zip(main["lipper_isin"], main["lipper_name"], strict=True):
        sample_path = root / str(isin) / "outputs" / "regression-sample.csv"
        if not sample_path.is_file():
            continue
        sample = pd.read_csv(
            sample_path, usecols=["Period", "Date"], dtype={"Period": str}
        )
        n = len(sample)
        pieces.append(
            pd.DataFrame(
                {
                    "ISIN": [isin] * n,
                    "Name": [name] * n,
                    "Period": sample["Period"].to_numpy(),
                    "Date": sample["Date"].to_numpy(),
                    "Exclude": [False] * n,
                }
            )
        )
    if not pieces:
        return pd.DataFrame(columns=EXCLUSIONS_COLUMNS)
    return pd.concat(pieces, ignore_index=True)
