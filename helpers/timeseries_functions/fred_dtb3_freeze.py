"""Frozen FRED DTB3 series for the US T-Bill 3M fill (Step 10)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULT_FREEZE_DIR = Path("cache") / "fred-dtb3"
MANIFEST_NAME = "manifest.json"
SERIES_FILE = "DTB3.csv"
SERIES_ID = "DTB3"


def _code_root(start: Path | None = None) -> Path:
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        if (directory / "helpers").is_dir():
            return directory
    raise FileNotFoundError(f"Could not find helpers/, starting from {origin}")


def resolve_fred_dtb3_freeze_dir(freeze_dir: Path | None = None) -> Path:
    relative = DEFAULT_FREEZE_DIR if freeze_dir is None else Path(freeze_dir)
    if relative.is_absolute():
        return relative.resolve()
    try:
        return (_code_root() / relative).resolve()
    except FileNotFoundError:
        return (Path.cwd().resolve() / relative).resolve()


def load_fred_dtb3_manifest(freeze_dir: Path | None = None) -> dict:
    path = resolve_fred_dtb3_freeze_dir(freeze_dir) / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def fred_dtb3_download_date(freeze_dir: Path | None = None) -> str | None:
    value = load_fred_dtb3_manifest(freeze_dir).get("download_date")
    return str(value) if value else None


def load_frozen_fred_dtb3(freeze_dir: Path | None = None) -> pd.Series:
    """Load frozen DTB3 (annualised bank discount rate, percent).

    Expects the FRED CSV layout: ``observation_date,DTB3``. Blank cells are
    treated as missing. Raises ``FileNotFoundError`` when the freeze file is
    absent or has no usable observations.
    """
    directory = resolve_fred_dtb3_freeze_dir(freeze_dir)
    path = directory / SERIES_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"Frozen FRED {SERIES_ID} file not found at {path}. "
            f"Place the FRED CSV download there and record download_date in "
            f"{MANIFEST_NAME}."
        )
    frame = pd.read_csv(path)
    if frame.empty:
        raise FileNotFoundError(f"Frozen FRED {SERIES_ID} file is empty: {path}")
    date_col = "observation_date" if "observation_date" in frame.columns else None
    value_col = SERIES_ID if SERIES_ID in frame.columns else None
    if date_col is None or value_col is None:
        raise ValueError(
            f"Expected columns observation_date and {SERIES_ID} in {path}; "
            f"got {list(frame.columns)}"
        )
    rates = pd.Series(
        pd.to_numeric(frame[value_col], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame[date_col], errors="coerce"),
        name=SERIES_ID,
        dtype="float64",
    )
    rates = rates[rates.index.notna()]
    if rates.empty:
        raise FileNotFoundError(f"No dated rows in frozen FRED {SERIES_ID}: {path}")
    rates.index = pd.DatetimeIndex(rates.index).tz_localize(None).normalize()
    rates = rates[~rates.index.duplicated(keep="last")].sort_index()
    if rates.notna().sum() == 0:
        raise FileNotFoundError(
            f"No numeric observations in frozen FRED {SERIES_ID}: {path}"
        )
    return rates
