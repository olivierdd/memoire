import sys
from pathlib import Path

import pandas as pd

def load_workbook(relative: Path, filename: str) -> pd.DataFrame:
    """Load the Timeseries sheet.

    ``relative`` is the directory that contains the workbook, for example
    ``Path("input-data-alix") / "clean"``. ``filename`` is the workbook name.
    """
    workbook = find_workbook(relative, filename)
    code = workbook.parent / "funds"
    if str(code) not in sys.path:
        sys.path.insert(0, str(code))
    return pd.read_excel(
        workbook,
        sheet_name="Timeseries",
        engine="openpyxl",
    )


def load_funds_sheet(relative: Path, filename: str) -> pd.DataFrame:
    """Load the Funds sheet (Lipper metadata and risk statistics)."""
    workbook = find_workbook(relative, filename)
    return pd.read_excel(workbook, sheet_name="Funds", engine="openpyxl")

def find_workbook(relative: Path, filename: str) -> Path:
    """Find the clean workbook whether the kernel cwd is code/ or notebooks/."""
    start = Path.cwd().resolve()
    target = Path(relative) / filename
    for directory in [start, *start.parents]:
        candidate = directory / target
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        f"Could not find {target}, starting from {start}"
    )
