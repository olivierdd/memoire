"""Set which workbook tabs are visible."""

from __future__ import annotations

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from helpers.format_excel.constants import VISIBLE_SHEETS


def apply_sheet_visibility(workbook: Workbook) -> dict[str, str]:
    """Hide every sheet not in ``VISIBLE_SHEETS``."""
    states: dict[str, str] = {}
    for name in workbook.sheetnames:
        worksheet = workbook[name]
        if name in VISIBLE_SHEETS:
            worksheet.sheet_state = Worksheet.SHEETSTATE_VISIBLE
            states[name] = "visible"
        else:
            worksheet.sheet_state = Worksheet.SHEETSTATE_HIDDEN
            states[name] = "hidden"
    return states