"""Add selection columns on the Funds sheet from Funds final membership."""

from __future__ import annotations

from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook

from helpers.format_excel.constants import (
    COL_ISIN,
    COL_SELECT_OUTCOME,
    COL_SELECT_PRIMARY,
    COL_SELECT_QUALITY,
    SHEET_FUNDS,
    SHEET_FUNDS_FINAL,
)


def _header_map(worksheet) -> dict[str, int]:
    return {cell.value: cell.column for cell in worksheet[1] if cell.value}


def _ensure_column(worksheet, header_name: str) -> int:
    headers = _header_map(worksheet)
    if header_name in headers:
        return headers[header_name]
    column = worksheet.max_column + 1
    worksheet.cell(row=1, column=column, value=header_name)
    return column


def final_isins(workbook: Workbook) -> set[str]:
    """ISIN values on the Funds final sheet (column ISIN)."""
    if SHEET_FUNDS_FINAL not in workbook.sheetnames:
        return set()
    worksheet = workbook[SHEET_FUNDS_FINAL]
    headers = _header_map(worksheet)
    isin_col = headers.get("ISIN")
    if isin_col is None:
        isin_col = headers.get(COL_ISIN)
    if isin_col is None:
        return set()
    values: set[str] = set()
    for row in range(2, worksheet.max_row + 1):
        value = worksheet.cell(row=row, column=isin_col).value
        if value is not None and str(value).strip():
            values.add(str(value).strip())
    return values


def enrich_funds_selection(workbook: Workbook) -> dict[str, str]:
    """Ensure select.* columns exist and reflect Funds final ISIN membership.

    Returns mapping of logical column names to Excel column letters.
    """
    funds = workbook[SHEET_FUNDS]
    headers = _header_map(funds)
    if COL_ISIN not in headers:
        raise KeyError(f"{SHEET_FUNDS} is missing column {COL_ISIN!r}")

    isin_col = headers[COL_ISIN]
    selected = final_isins(workbook)

    primary_col = _ensure_column(funds, COL_SELECT_PRIMARY)
    outcome_col = _ensure_column(funds, COL_SELECT_OUTCOME)
    quality_col = _ensure_column(funds, COL_SELECT_QUALITY)

    for row in range(2, funds.max_row + 1):
        isin = funds.cell(row=row, column=isin_col).value
        isin_key = str(isin).strip() if isin is not None else ""
        in_final = isin_key in selected
        funds.cell(row=row, column=outcome_col, value=in_final)
        funds.cell(row=row, column=quality_col, value=in_final)
        funds.cell(row=row, column=primary_col, value=bool(in_final))

    return {
        "select_outcome": get_column_letter(outcome_col),
        "select_quality": get_column_letter(quality_col),
        "funds_last_row": str(funds.max_row),
    }