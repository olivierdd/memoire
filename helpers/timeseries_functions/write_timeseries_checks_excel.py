"""Write the consolidated timeseries-checks workbook from per-fund JSON caches."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from helpers.timeseries_functions.save_timeseries_check import find_project_root
from helpers.timeseries_functions.timeseries_checks_methodology import (
    METHODOLOGY_ROWS,
    METHODOLOGY_SHEET_NAME,
)
from helpers.timeseries_functions.timeseries_checks_rows import (
    COLUMN_FAMILIES,
    EXCLUSIONS_COLUMNS,
    build_regression_exclusions_rows,
    build_timeseries_checks_rows,
)
from helpers.funds_functions.load_workbook import find_workbook, load_workbook

SHEET_NAME = "Timeseries-checks"
EXCLUSIONS_SHEET_NAME = "Regression-exclusions"
OUTPUT_SUFFIX = "_timeseries-checks"

__all__ = [
    "export_timeseries_checks",
    "build_export_bundle",
    "build_timeseries_checks_frame",
    "write_timeseries_checks_excel",
]

_EXPORT_SPECS = [spec for spec in COLUMN_FAMILIES if not spec.key.startswith("_gap")]

_FAMILY_FILLS: dict[str, PatternFill] = {
    "Fund (Lipper)": PatternFill("solid", fgColor="D9E1F2"),
    "Check: Lipper vs Yahoo": PatternFill("solid", fgColor="E2EFDA"),
    "Check: Lipper quality": PatternFill("solid", fgColor="FFF2CC"),
    "Check: Yahoo quality": PatternFill("solid", fgColor="FCE4D6"),
    "Check: regression": PatternFill("solid", fgColor="DDEBF7"),
    "Check: vs Lipper Funds": PatternFill("solid", fgColor="E4DFEC"),
    "Check: vs Consolidation": PatternFill("solid", fgColor="F4CCCC"),
    "Decision": PatternFill("solid", fgColor="E8F5E9"),
}
_DEFAULT_FAMILY_FILL = PatternFill("solid", fgColor="D0D0D0")
_HEADER_FILL = PatternFill("solid", fgColor="404040")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
_FAMILY_FONT = Font(bold=True, size=10)
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
_FAMILY_ALIGN = Alignment(horizontal="center", vertical="center")

_FILL_MATCH = PatternFill("solid", fgColor="C6EFCE")
_FILL_MISMATCH = PatternFill("solid", fgColor="FFC7CE")
_FILL_NA = PatternFill("solid", fgColor="EDEDED")
_FILL_ZEBRA = PatternFill("solid", fgColor="F7F7F7")

_RESULT_STYLES: dict[str, tuple[PatternFill, Font]] = {
    "Match": (_FILL_MATCH, Font(bold=True, color="006100")),
    "Recreates sheet": (_FILL_MATCH, Font(bold=True, color="006100")),
    "Date alignment": (_FILL_MATCH, Font(bold=True, color="006100")),
    "Mismatch": (_FILL_MISMATCH, Font(bold=True, color="9C0006")),
    "Drifts from sheet": (_FILL_MISMATCH, Font(bold=True, color="9C0006")),
    "Not comparable": (_FILL_NA, Font(bold=True, color="525252")),
}
_RESULT_ALIGN = Alignment(horizontal="center", vertical="top")
_METHODOLOGY_TITLE_FONT = Font(bold=True, size=12)
_METHODOLOGY_SECTION_FONT = Font(bold=True, size=11)
_METHODOLOGY_BODY_FONT = Font(size=11)
_METHODOLOGY_BODY_ALIGN = Alignment(wrap_text=True, vertical="top")
_METHODOLOGY_HEADER_FILL = PatternFill("solid", fgColor="404040")
_METHODOLOGY_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)


def _output_path(source_workbook: Path) -> Path:
    return find_project_root() / "output-data" / f"{source_workbook.stem}{OUTPUT_SUFFIX}.xlsx"


def build_timeseries_checks_frame(
    funds: pd.DataFrame,
    checks_root: Path | None = None,
) -> pd.DataFrame:
    flat = build_timeseries_checks_rows(funds, checks_root=checks_root)
    return flat[[spec.key for spec in _EXPORT_SPECS]]


def build_export_bundle(
    funds: pd.DataFrame,
    checks_root: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build main and exclusions frames in one pass over check folders."""
    main = build_timeseries_checks_rows(funds, checks_root=checks_root)
    frame = main[[spec.key for spec in _EXPORT_SPECS]] if not main.empty else main
    exclusions = build_regression_exclusions_rows(
        checks_root=checks_root,
        main=main,
    )
    return frame, exclusions


def _family_spans() -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    col = 0
    current: str | None = None
    start = 0
    for spec in _EXPORT_SPECS:
        col += 1
        if spec.family != current:
            if current:
                spans.append((current, start, col - 1))
            current = spec.family
            start = col
    if current:
        spans.append((current, start, col))
    return spans


def _write_section_header_row(worksheet) -> None:
    for family, col_start, col_end in _family_spans():
        cell = worksheet.cell(row=1, column=col_start, value=family)
        fill = _FAMILY_FILLS.get(family, _DEFAULT_FAMILY_FILL)
        cell.fill = fill
        cell.font = _FAMILY_FONT
        cell.alignment = _FAMILY_ALIGN
        if col_start != col_end:
            worksheet.merge_cells(
                start_row=1,
                start_column=col_start,
                end_row=1,
                end_column=col_end,
            )
    for col_idx, spec in enumerate(_EXPORT_SPECS, start=1):
        cell = worksheet.cell(row=2, column=col_idx, value=spec.header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _HEADER_ALIGN


def _apply_layout(worksheet, *, n_data_rows: int, ncols: int) -> None:
    for idx, spec in enumerate(_EXPORT_SPECS, start=1):
        worksheet.column_dimensions[get_column_letter(idx)].width = spec.width
    worksheet.row_dimensions[1].height = 22
    worksheet.row_dimensions[2].height = 54
    worksheet.freeze_panes = "E3"
    last_col = get_column_letter(ncols)
    worksheet.auto_filter.ref = f"A2:{last_col}{n_data_rows + 2}"


def _non_result_column_spans(ncols: int) -> list[tuple[int, int]]:
    result_cols = {
        idx for idx, spec in enumerate(_EXPORT_SPECS, start=1) if spec.kind == "result"
    }
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for col in range(1, ncols + 1):
        if col in result_cols:
            if start is not None:
                spans.append((start, col - 1))
                start = None
        elif start is None:
            start = col
    if start is not None:
        spans.append((start, ncols))
    return spans


def _apply_zebra_striping(worksheet, *, n_data_rows: int, ncols: int) -> None:
    if n_data_rows <= 0:
        return
    first_row = 3
    last_row = n_data_rows + 2
    for col_start, col_end in _non_result_column_spans(ncols):
        col_a = get_column_letter(col_start)
        col_b = get_column_letter(col_end)
        data_range = f"{col_a}{first_row}:{col_b}{last_row}"
        worksheet.conditional_formatting.add(
            data_range,
            FormulaRule(formula=["MOD(ROW(),2)=0"], fill=_FILL_ZEBRA),
        )


def _apply_result_cell_colors(worksheet, frame: pd.DataFrame, *, first_row: int = 3) -> None:
    result_columns = [
        (col_idx, spec.key)
        for col_idx, spec in enumerate(_EXPORT_SPECS, start=1)
        if spec.kind == "result"
    ]
    for row_offset in range(len(frame)):
        excel_row = first_row + row_offset
        for col_idx, key in result_columns:
            raw = frame.iloc[row_offset][key]
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                continue
            label = str(raw).strip()
            styles = _RESULT_STYLES.get(label)
            cell = worksheet.cell(row=excel_row, column=col_idx)
            cell.alignment = _RESULT_ALIGN
            if styles is None:
                continue
            fill, font = styles
            cell.fill = fill
            cell.font = font


def _write_methodology_sheet(workbook) -> None:
    ws = workbook.create_sheet(METHODOLOGY_SHEET_NAME)
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 96

    ws["A1"] = "Topic"
    ws["B1"] = "Description"
    for col in ("A", "B"):
        cell = ws[f"{col}1"]
        cell.fill = _METHODOLOGY_HEADER_FILL
        cell.font = _METHODOLOGY_HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws["A2"] = "Document"
    ws["B2"] = (
        "Timeseries data selection, quality checks, and regression methodology for "
        "the timeseries-checks export. Built from output-data/timeseries-checks/<ISIN>/."
    )
    ws["A2"].font = _METHODOLOGY_SECTION_FONT
    ws["B2"].font = _METHODOLOGY_BODY_FONT
    ws["B2"].alignment = _METHODOLOGY_BODY_ALIGN

    row = 3
    for heading, body in METHODOLOGY_ROWS:
        ws.cell(row=row, column=1, value=heading or "")
        body_cell = ws.cell(row=row, column=2, value=body)
        body_cell.font = _METHODOLOGY_BODY_FONT
        body_cell.alignment = _METHODOLOGY_BODY_ALIGN
        if heading:
            ws.cell(row=row, column=1).font = _METHODOLOGY_SECTION_FONT
        row += 1

    ws.freeze_panes = "A2"


def _write_exclusions_sheet(writer, exclusions: pd.DataFrame) -> None:
    exclusions.to_excel(
        writer,
        sheet_name=EXCLUSIONS_SHEET_NAME,
        index=False,
    )
    ws = writer.sheets[EXCLUSIONS_SHEET_NAME]
    widths = {"ISIN": 16, "Name": 43, "Period": 12, "Date": 14, "Exclude": 10}
    for idx, col in enumerate(EXCLUSIONS_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = widths.get(col, 12)
    ws.freeze_panes = "A2"
    if len(exclusions) > 0:
        ws.auto_filter.ref = f"A1:E{len(exclusions) + 1}"


def write_timeseries_checks_excel(
    funds: pd.DataFrame,
    destination: Path,
    checks_root: Path | None = None,
    *,
    frame: pd.DataFrame | None = None,
    exclusions: pd.DataFrame | None = None,
) -> Path:
    """Create xlsx (Timeseries-checks + Regression-exclusions + Methodology)."""
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if frame is None or exclusions is None:
        frame, exclusions = build_export_bundle(funds, checks_root=checks_root)
    n_data_rows, ncols = frame.shape

    with NamedTemporaryFile(suffix=".xlsx", dir=destination.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
            frame.to_excel(
                writer,
                sheet_name=SHEET_NAME,
                index=False,
                header=False,
                startrow=2,
            )
            ws = writer.sheets[SHEET_NAME]
            _write_section_header_row(ws)
            _apply_layout(ws, n_data_rows=n_data_rows, ncols=ncols)
            _apply_result_cell_colors(ws, frame)
            _apply_zebra_striping(ws, n_data_rows=n_data_rows, ncols=ncols)
            _write_exclusions_sheet(writer, exclusions)
            _write_methodology_sheet(writer.book)
        os.replace(tmp_path, destination)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return destination


def export_timeseries_checks(
    funds: pd.DataFrame | None = None,
    workbook: Path | None = None,
    checks_root: Path | None = None,
) -> Path:
    """Write ``output-data/<workbook stem>_timeseries-checks.xlsx``.

    Only ISINs present in ``funds`` (in sheet order) are exported, among those
    that have a folder under ``output-data/timeseries-checks/<ISIN>/``. Pass the
    same limited table as the batch (e.g. ``eligible`` after ``FUND_LIMIT``),
    not the full Lipper fund list, to match a trial run.
    """
    source = find_workbook() if workbook is None else Path(workbook).resolve()
    if funds is None:
        funds = load_workbook(source)
    destination = _output_path(source)
    frame, exclusions = build_export_bundle(funds, checks_root=checks_root)
    write_timeseries_checks_excel(
        funds,
        destination,
        checks_root=checks_root,
        frame=frame,
        exclusions=exclusions,
    )
    n_rows = len(frame)
    print(
        f"Timeseries-checks export: {n_rows} fund rows written to {destination} "
        f"({SHEET_NAME} + {EXCLUSIONS_SHEET_NAME} + {METHODOLOGY_SHEET_NAME})"
    )
    return destination
