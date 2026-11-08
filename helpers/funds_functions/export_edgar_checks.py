"""Backward-compatible entry point; implementation lives in write_edgar_checks_excel."""

from helpers.funds_functions.write_edgar_checks_excel import (
    OUTPUT_SUFFIX,
    SHEET_NAME,
    build_edgar_checks_frame,
    export_edgar_checks,
    write_edgar_checks_excel,
)

__all__ = [
    "OUTPUT_SUFFIX",
    "SHEET_NAME",
    "build_edgar_checks_frame",
    "export_edgar_checks",
    "write_edgar_checks_excel",
]
