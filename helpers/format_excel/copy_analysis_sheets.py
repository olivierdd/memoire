"""Copy analysis tabs from the reference template and retarget formulas."""

from __future__ import annotations

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook

from helpers.format_excel.constants import (
    ANALYSIS_SHEETS,
    SHEET_D_TIMESERIES,
    SHEET_FUNDS,
)
from helpers.format_excel.retarget_formulas import (
    RetargetSpec,
    build_retarget_spec,
    retarget_worksheet,
)
from helpers.format_excel.sheet_copy import replace_sheet_from_template


def copy_analysis_sheets(
    target: Workbook,
    template_path,
    *,
    select_outcome_col: str,
    select_quality_col: str,
) -> tuple[RetargetSpec, dict[str, int]]:
    """Copy Config, Fund Analysis, Consolidation, and Funds by AUM from template."""
    template = load_workbook(template_path, data_only=False)
    try:
        funds_row = target[SHEET_FUNDS].max_row
        dts = target[SHEET_D_TIMESERIES]
        dts_row = dts.max_row
        dts_col = get_column_letter(dts.max_column)
        spec = build_retarget_spec(
            funds_last_row=funds_row,
            dts_last_row=dts_row,
            dts_last_col=dts_col,
            select_outcome_col=select_outcome_col,
            select_quality_col=select_quality_col,
        )
        updated: dict[str, int] = {}
        for name in ANALYSIS_SHEETS:
            if name not in template.sheetnames:
                raise KeyError(f"Template workbook missing sheet {name!r}")
            replace_sheet_from_template(target, template[name], title=name)
            updated[name] = retarget_worksheet(target[name], spec)
        retarget_worksheet(target["Config"], spec)
        return spec, updated
    finally:
        template.close()