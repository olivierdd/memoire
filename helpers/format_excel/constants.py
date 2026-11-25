"""Shared names and styling for formatted fund workbooks."""

from __future__ import annotations

SHEET_FUNDS = "Funds"
SHEET_FUNDS_FINAL = "Funds final"
SHEET_D_TIMESERIES = "D-Timeseries final"

ANALYSIS_SHEETS = (
    "Config",
    "Fund Analysis",
    "Consolidation",
    "Funds by AUM",
)

VISIBLE_SHEETS = (
    SHEET_FUNDS_FINAL,
    SHEET_D_TIMESERIES,
    *ANALYSIS_SHEETS,
)

COL_ISIN = "ds.isin"
COL_SELECT_OUTCOME = "select.outcome"
COL_SELECT_QUALITY = "select.has_quality_timeseries"
COL_SELECT_PRIMARY = "select.primary_share_class"

# Reference template dimensions (v3 formatted workbook).
TEMPLATE_FUNDS_LAST_ROW = 2611
TEMPLATE_DTS_LAST_ROW = 2877
TEMPLATE_DTS_LAST_COL = "BGI"
TEMPLATE_FUND_ANALYSIS_LAST_ROW = 2872
TEMPLATE_CONSOLIDATION_LAST_ROW = 551
TEMPLATE_SELECT_COL = "BN"
TEMPLATE_QUALITY_COL = "BM"

DEFAULT_TEMPLATE_RELATIVE = "usefull-references/v2-funds-normalized-formatted-v3.xlsx"
DEFAULT_INPUT_FILENAME = "v2-funds-normalized-cleaned.xlsx"
DEFAULT_OUTPUT_FILENAME = "v2-funds-normalized-formatted.xlsx"

HEADER_NAVY = "1F3864"
HEADER_WHITE = "FFFFFF"
LABEL_GRAY = "F2F2F2"
ZEBRA_BLUE = "EEF3FA"