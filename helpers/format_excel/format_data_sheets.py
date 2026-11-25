"""Apply reference styling to Funds final and D-Timeseries final."""

from __future__ import annotations

from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook

from helpers.format_excel.constants import (
    HEADER_NAVY,
    HEADER_WHITE,
    LABEL_GRAY,
    SHEET_D_TIMESERIES,
    SHEET_FUNDS_FINAL,
    ZEBRA_BLUE,
)

_FILL_HEADER = PatternFill("solid", fgColor=HEADER_NAVY)
_FILL_LABEL = PatternFill("solid", fgColor=LABEL_GRAY)
_FILL_ZEBRA = PatternFill("solid", fgColor=ZEBRA_BLUE)
_FONT_HEADER = Font(name="Calibri", size=10, bold=True, color=HEADER_WHITE)
_FONT_DEFAULT = Font(name="Calibri", size=10)


def format_funds_final(workbook: Workbook) -> None:
    worksheet = workbook[SHEET_FUNDS_FINAL]
    max_row = worksheet.max_row
    max_col = worksheet.max_column
    last_col = get_column_letter(max_col)

    for col in range(1, max_col + 1):
        cell = worksheet.cell(row=1, column=col)
        cell.fill = _FILL_HEADER
        cell.font = _FONT_HEADER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        letter = get_column_letter(col)
        worksheet.column_dimensions[letter].width = max(
            worksheet.column_dimensions[letter].width or 0,
            12,
        )

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = f"A1:{last_col}{max_row}"
    worksheet.conditional_formatting._cf_rules.clear()
    worksheet.conditional_formatting.add(
        f"A2:{last_col}{max_row}",
        FormulaRule(
            formula=['MOD(SUBTOTAL(103,$A$2:$A2),2)=0'],
            fill=_FILL_ZEBRA,
        ),
    )


def format_d_timeseries(workbook: Workbook) -> None:
    worksheet = workbook[SHEET_D_TIMESERIES]
    max_col = worksheet.max_column
    max_row = worksheet.max_row
    last_col = get_column_letter(max_col)

    for col in range(1, max_col + 1):
        letter = get_column_letter(col)
        if col == 1:
            worksheet.column_dimensions[letter].width = 12
        else:
            worksheet.column_dimensions[letter].width = 14
        for row in range(1, 6):
            cell = worksheet.cell(row=row, column=col)
            cell.fill = _FILL_LABEL
            cell.font = _FONT_DEFAULT
        header = worksheet.cell(row=6, column=col)
        header.fill = _FILL_HEADER
        header.font = _FONT_HEADER
        header.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row in range(7, max_row + 1):
        cell = worksheet.cell(row=row, column=1)
        cell.number_format = "mm-dd-yy"
        cell.font = _FONT_DEFAULT

    worksheet.freeze_panes = "A7"


def format_data_sheets(workbook: Workbook) -> None:
    if SHEET_FUNDS_FINAL in workbook.sheetnames:
        format_funds_final(workbook)
    if SHEET_D_TIMESERIES in workbook.sheetnames:
        format_d_timeseries(workbook)