"""Build a formatted analysis workbook from a cleaned pipeline export."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from helpers.format_excel.constants import (
    DEFAULT_TEMPLATE_RELATIVE,
    SHEET_D_TIMESERIES,
    SHEET_FUNDS,
)
from helpers.format_excel.copy_analysis_sheets import copy_analysis_sheets
from helpers.format_excel.enrich_funds_selection import enrich_funds_selection
from helpers.format_excel.format_data_sheets import format_data_sheets
from helpers.format_excel.sheet_visibility import apply_sheet_visibility


@dataclass(frozen=True)
class FormatWorkbookResult:
    output_path: Path
    input_path: Path
    template_path: Path
    sheet_states: dict[str, str]
    formula_cells_updated: dict[str, int]
    select_outcome_col: str
    select_quality_col: str
    dts_last_col: str
    funds_last_row: int
    dts_last_row: int


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "helpers" / "format_excel").is_dir():
            return directory
    raise FileNotFoundError("Could not locate repository root (helpers/format_excel).")


def default_template_path(repo_root: Path | None = None) -> Path:
    root = repo_root or find_repo_root()
    return (root / DEFAULT_TEMPLATE_RELATIVE).resolve()


def format_workbook(
    input_path: Path,
    output_path: Path,
    template_path: Path | None = None,
) -> FormatWorkbookResult:
    """Copy ``input_path``, enrich, format, add analysis tabs, and save to ``output_path``."""
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    if input_path == output_path:
        raise ValueError("Output path must differ from input path")

    template = Path(template_path or default_template_path()).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if not template.is_file():
        raise FileNotFoundError(template)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix="format-workbook-",
        suffix=".xlsx",
        delete=False,
        dir=output_path.parent,
    )
    temporary_path = Path(temporary.name)
    temporary.close()

    try:
        shutil.copyfile(input_path, temporary_path)
        workbook = load_workbook(temporary_path)
        try:
            if SHEET_FUNDS not in workbook.sheetnames:
                raise KeyError(f"Workbook missing required sheet {SHEET_FUNDS!r}")
            if SHEET_D_TIMESERIES not in workbook.sheetnames:
                raise KeyError(
                    f"Workbook missing required sheet {SHEET_D_TIMESERIES!r}"
                )

            selection = enrich_funds_selection(workbook)
            format_data_sheets(workbook)
            _, formula_updates = copy_analysis_sheets(
                workbook,
                template,
                select_outcome_col=selection["select_outcome"],
                select_quality_col=selection["select_quality"],
            )
            sheet_states = apply_sheet_visibility(workbook)
            dts = workbook[SHEET_D_TIMESERIES]
            dts_last_col = get_column_letter(dts.max_column)
            dts_last_row = dts.max_row
            workbook.save(temporary_path)
        finally:
            workbook.close()

        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            try:
                os.remove(temporary_path)
            except OSError:
                pass

    funds_last_row = int(selection["funds_last_row"])
    return FormatWorkbookResult(
        output_path=output_path,
        input_path=input_path,
        template_path=template,
        sheet_states=sheet_states,
        formula_cells_updated=formula_updates,
        select_outcome_col=selection["select_outcome"],
        select_quality_col=selection["select_quality"],
        dts_last_col=dts_last_col,
        funds_last_row=funds_last_row,
        dts_last_row=dts_last_row,
    )


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Format a cleaned funds workbook.")
    parser.add_argument("input", type=Path, help="Input .xlsx under output-data/")
    parser.add_argument("output", type=Path, help="Output .xlsx path")
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Reference template (default: usefull-references/v2-funds-normalized-formatted-v3.xlsx)",
    )
    args = parser.parse_args(argv)
    result = format_workbook(args.input, args.output, template_path=args.template)
    print(f"Wrote {result.output_path}")
    print(f"Visible sheets: {[n for n, s in result.sheet_states.items() if s == 'visible']}")


if __name__ == "__main__":
    main()