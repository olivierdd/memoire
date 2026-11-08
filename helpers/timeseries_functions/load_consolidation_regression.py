from pathlib import Path

import pandas as pd
from openpyxl import load_workbook as openpyxl_load_workbook

from helpers.timeseries_functions.load_workbook import find_workbook

_CONSOLIDATION_SHEET = "Consolidation"
_CONSOLIDATION_WINDOW_START = "AE6"
_CONSOLIDATION_WINDOW_END = "AE5"

_CONSOLIDATION_REGRESSION_COLUMNS = (
    "Fund",
    "Months",
    "Beta",
    "Tracking error (%)",
    "Excess return (%/yr)",
    "Net alpha (%/yr)",
    "Gross alpha (%/yr)",
    "Information ratio",
    "Fees (%)",
)


def load_consolidation_regression_window(
    relative: Path,
    filename: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Start and end dates from Consolidation!AE6 and AE5 (analysis window)."""
    workbook = find_workbook(relative, filename)
    book = openpyxl_load_workbook(workbook, read_only=True, data_only=True)
    try:
        sheet = book[_CONSOLIDATION_SHEET]
        start = pd.Timestamp(sheet[_CONSOLIDATION_WINDOW_START].value)
        end = pd.Timestamp(sheet[_CONSOLIDATION_WINDOW_END].value)
    finally:
        book.close()
    if start > end:
        start, end = end, start
    return start, end


def load_consolidation_sheet(relative: Path, filename: str) -> pd.DataFrame:
    """Consolidation tab with formula cells read as last-calculated values."""
    workbook = find_workbook(relative, filename)
    book = openpyxl_load_workbook(workbook, read_only=True, data_only=True)
    try:
        sheet = book[_CONSOLIDATION_SHEET]
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        book.close()
    if not rows:
        return pd.DataFrame(columns=list(_CONSOLIDATION_REGRESSION_COLUMNS))
    headers = [
        str(value).strip() if value is not None else "" for value in rows[0]
    ]
    return pd.DataFrame(rows[1:], columns=headers)


def load_consolidation_fund_regression_reference(
    isin: str,
    relative: Path,
    filename: str,
    *,
    consolidation_sheet: pd.DataFrame | None = None,
) -> pd.Series:
    """One Consolidation-sheet row for ``isin`` (raises if missing)."""
    consolidation = (
        consolidation_sheet
        if consolidation_sheet is not None
        else load_consolidation_sheet(relative, filename)
    )
    match = consolidation.loc[consolidation["Fund"].astype(str).str.strip().eq(isin)]
    if match.empty:
        raise KeyError(f"ISIN {isin} not found on Consolidation sheet")
    row = match.iloc[0]
    return row.loc[list(_CONSOLIDATION_REGRESSION_COLUMNS)]
