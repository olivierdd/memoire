import re
import sys
import unicodedata
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


def normalize_columns(frame: pd.DataFrame, prefix: str = "ds.") -> pd.DataFrame:
    """Return a copy with snake_case column names, each starting with ``prefix``.

    Lowercase, accents removed, every run of other characters becomes one
    underscore. A repeated name gets a numeric suffix.
    """
    names: list[str] = []
    seen: dict[str, int] = {}
    for column in frame.columns:
        text = unicodedata.normalize("NFKD", str(column))
        text = text.encode("ascii", "ignore").decode("ascii").lower()
        text = re.sub(r"[^a-z0-9]+", "_", text).strip("_") or "column"
        count = seen.get(text, 0)
        seen[text] = count + 1
        names.append(f"{prefix}{text}" if count == 0 else f"{prefix}{text}_{count + 1}")
    result = frame.copy()
    result.columns = names
    return result


def subgroup_counts(funds: pd.DataFrame) -> pd.DataFrame:
    """Count occurrences for each combination of fund_wrapper and fund_type."""
    return (
        funds.groupby(["fund_wrapper", "fund_type"])
        .size()
        .reset_index(name="count")
    )


def _drop_prefix(name: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def add_prefixed_columns(
    base: pd.DataFrame,
    enriched: pd.DataFrame,
    prefix: str,
    *,
    source_columns: pd.Index | list,
    source_prefix: str | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Append the columns of ``enriched`` that ``source_columns`` does not have.

    ``source_columns`` are the column names of the frame that went into the
    enrichment step. ``base`` has different (normalized) names, so it cannot be
    used to tell which columns are new.

    ``base`` and ``enriched`` are matched on their index. Each new column is
    normalized like ``normalize_columns`` and given ``prefix`` (for example
    ``openfigi.``). A leading ``source_prefix`` (for example ``openfigi_``) is
    dropped first so the prefix is not repeated. Rows of ``base`` missing from
    ``enriched`` get blanks. The new columns go at the end.
    """
    new_columns = [c for c in enriched.columns if c not in set(source_columns)]
    added = enriched.loc[:, new_columns].copy()
    if source_prefix:
        prefixes = (source_prefix,) if isinstance(source_prefix, str) else source_prefix
        added.columns = [_drop_prefix(str(c), prefixes) for c in added.columns]
    added = normalize_columns(added, prefix=prefix)
    out = base.drop(columns=[c for c in added.columns if c in base.columns])
    return out.join(added)
