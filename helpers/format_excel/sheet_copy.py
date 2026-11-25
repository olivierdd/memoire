"""Copy worksheets between openpyxl workbooks."""

from __future__ import annotations

from copy import copy

from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet


def replace_sheet_from_template(
    target: Workbook,
    source: Worksheet,
    *,
    title: str | None = None,
) -> Worksheet:
    """Replace ``title`` on ``target`` with a deep copy of ``source``."""
    name = title or source.title
    if name in target.sheetnames:
        del target[name]
    worksheet = target.create_sheet(name)
    _copy_sheet_content(source, worksheet)
    return worksheet


def _copy_sheet_content(source: Worksheet, target: Worksheet) -> None:
    target.sheet_format = copy(source.sheet_format)
    target.sheet_properties = copy(source.sheet_properties)
    target.merged_cells = copy(source.merged_cells)
    target.page_setup = copy(source.page_setup)
    target.print_options = copy(source.print_options)

    for index, row_dim in source.row_dimensions.items():
        if row_dim.height is not None:
            target.row_dimensions[index].height = row_dim.height
    for letter, col_dim in source.column_dimensions.items():
        if col_dim.width is not None:
            target.column_dimensions[letter].width = col_dim.width

    for row in source.iter_rows():
        for cell in row:
            new_cell = target.cell(row=cell.row, column=cell.column, value=cell.value)
            new_cell.number_format = cell.number_format
            if cell.has_style:
                new_cell.font = copy(cell.font)
                new_cell.fill = copy(cell.fill)
                new_cell.border = copy(cell.border)
                new_cell.alignment = copy(cell.alignment)
                new_cell.protection = copy(cell.protection)
            if cell.hyperlink:
                new_cell.hyperlink = copy(cell.hyperlink)
            if cell.comment:
                new_cell.comment = copy(cell.comment)

    target.freeze_panes = source.freeze_panes
    if source.auto_filter and source.auto_filter.ref:
        target.auto_filter.ref = source.auto_filter.ref

    for range_string, rules in source.conditional_formatting._cf_rules.items():
        for rule in rules:
            target.conditional_formatting.add(range_string, copy(rule))

    for validation in source.data_validations.dataValidation:
        target.data_validations.append(copy(validation))