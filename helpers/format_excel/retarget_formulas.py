"""Rewrite template range references for the current workbook geometry."""

from __future__ import annotations

from dataclasses import dataclass

from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet

from helpers.format_excel.constants import (
    TEMPLATE_CONSOLIDATION_LAST_ROW,
    TEMPLATE_DTS_LAST_COL,
    TEMPLATE_DTS_LAST_ROW,
    TEMPLATE_FUND_ANALYSIS_LAST_ROW,
    TEMPLATE_FUNDS_LAST_ROW,
    TEMPLATE_QUALITY_COL,
    TEMPLATE_SELECT_COL,
)


@dataclass(frozen=True)
class RetargetSpec:
    funds_last_row: int
    dts_last_row: int
    dts_last_col: str
    fund_analysis_last_row: int
    consolidation_last_row: int
    select_outcome_col: str
    select_quality_col: str
    funds_select_col: str | None = None  # legacy alias


def build_retarget_spec(
    *,
    funds_last_row: int,
    dts_last_row: int,
    dts_last_col: str,
    select_outcome_col: str,
    select_quality_col: str,
) -> RetargetSpec:
    return RetargetSpec(
        funds_last_row=funds_last_row,
        dts_last_row=dts_last_row,
        dts_last_col=dts_last_col.upper(),
        fund_analysis_last_row=dts_last_row - 5,
        consolidation_last_row=max(
            TEMPLATE_CONSOLIDATION_LAST_ROW,
            min(funds_last_row, dts_last_row),
        ),
        select_outcome_col=select_outcome_col.upper(),
        select_quality_col=select_quality_col.upper(),
    )


def retarget_worksheet(worksheet: Worksheet, spec: RetargetSpec) -> int:
    """Return count of cells whose formulas were rewritten."""
    updated = 0
    for row in worksheet.iter_rows():
        for cell in row:
            if not isinstance(cell, Cell):
                continue
            value = cell.value
            if not isinstance(value, str) or not value.startswith("="):
                continue
            new_value = retarget_formula(value, spec)
            if new_value != value:
                cell.value = new_value
                updated += 1
    return updated


def retarget_formula(formula: str, spec: RetargetSpec) -> str:
    """Replace hard-coded template dimensions inside a formula string."""
    replacements: list[tuple[str, str]] = [
        (f"${TEMPLATE_DTS_LAST_COL}$", f"${spec.dts_last_col}$"),
        (f":${TEMPLATE_DTS_LAST_COL}$", f":${spec.dts_last_col}$"),
        (TEMPLATE_DTS_LAST_COL, spec.dts_last_col),
        (f"${TEMPLATE_DTS_LAST_ROW}", f"${spec.dts_last_row}"),
        (f"{TEMPLATE_DTS_LAST_ROW}", f"{spec.dts_last_row}"),
        (f"${TEMPLATE_FUNDS_LAST_ROW}", f"${spec.funds_last_row}"),
        (f":${TEMPLATE_FUNDS_LAST_ROW}", f":${spec.funds_last_row}"),
        (f"{TEMPLATE_FUNDS_LAST_ROW}", f"{spec.funds_last_row}"),
        (f"${TEMPLATE_FUND_ANALYSIS_LAST_ROW}", f"${spec.fund_analysis_last_row}"),
        (f":${TEMPLATE_FUND_ANALYSIS_LAST_ROW}", f":${spec.fund_analysis_last_row}"),
        (f"{TEMPLATE_FUND_ANALYSIS_LAST_ROW}", f"{spec.fund_analysis_last_row}"),
        (f"${TEMPLATE_CONSOLIDATION_LAST_ROW}", f"${spec.consolidation_last_row}"),
        (f"{TEMPLATE_CONSOLIDATION_LAST_ROW}", f"{spec.consolidation_last_row}"),
        (f"Funds!${TEMPLATE_SELECT_COL}$", f"Funds!${spec.select_outcome_col}$"),
        (f"Funds!${TEMPLATE_QUALITY_COL}$", f"Funds!${spec.select_quality_col}$"),
        (f"${TEMPLATE_SELECT_COL}$", f"${spec.select_outcome_col}$"),
        (f"${TEMPLATE_QUALITY_COL}$", f"${spec.select_quality_col}$"),
    ]
    out = formula
    for old, new in replacements:
        out = out.replace(old, new)
    return out