import sys
from pathlib import Path

import pandas as pd

FILENAME = "CLEAN_RECOLTE DONNEES-EXCEL.xlsx"
RELATIVE = Path("input-data-alix") / "clean" / FILENAME


def find_workbook(relative: Path = RELATIVE, start: Path | None = None) -> Path:
    """Find the clean workbook whether the kernel cwd is code/ or notebooks/."""
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        candidate = directory / relative
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Could not find {relative}, starting from {origin}")


def load_workbook(workbook: Path | None = None) -> pd.DataFrame:
    """Load the Funds sheet and make ``workbook.parent / "funds"`` importable."""
    path = find_workbook() if workbook is None else Path(workbook)
    code = path.parent / "funds"
    if str(code) not in sys.path:
        sys.path.insert(0, str(code))
    return pd.read_excel(
        path,
        sheet_name="Funds",
        engine="openpyxl",
        dtype={"ISIN": "string", "RIC": "string"},
    )


def subgroup_counts(funds: pd.DataFrame) -> pd.DataFrame:
    """Count occurrences for each combination of fund_wrapper and fund_type."""
    return (
        funds.groupby(["fund_wrapper", "fund_type"])
        .size()
        .reset_index(name="count")
    )
