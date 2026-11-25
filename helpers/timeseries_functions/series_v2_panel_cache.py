"""Parquet sidecar for the Step 1 working panel (catalog + observations).

The normalised Excel workbook remains the source of truth. When a fresh sidecar
exists under ``cache/series-v2-panel/``, Step 1 restores the filtered panel from
Parquet instead of re-parsing the workbook with openpyxl.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from helpers.timeseries_functions.replace_yahoo_tr import YAHOO_TR_REPLACEMENTS
from helpers.timeseries_functions.yahoo_tr_freeze import (
    resolve_yahoo_tr_freeze_dir,
)

DEFAULT_CACHE_DIR = Path("cache") / "series-v2-panel"
CACHE_VERSION = 1
META_NAME = "meta.json"
CATALOG_NAME = "catalog.parquet"
OBSERVATIONS_NAME = "observations.parquet"
YAHOO_LOG_NAME = "yahoo_tr_log.parquet"


def _code_root(start: Path | None = None) -> Path:
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        if (directory / "helpers").is_dir():
            return directory
    raise FileNotFoundError(f"Could not find helpers/, starting from {origin}")


def resolve_panel_cache_dir(cache_dir: Path | None = None) -> Path:
    relative = DEFAULT_CACHE_DIR if cache_dir is None else Path(cache_dir)
    if relative.is_absolute():
        return relative.resolve()
    try:
        return (_code_root() / relative).resolve()
    except FileNotFoundError:
        return (Path.cwd().resolve() / relative).resolve()


def panel_cache_paths(cache_dir: Path | None = None) -> dict[str, Path]:
    root = resolve_panel_cache_dir(cache_dir)
    return {
        "root": root,
        "meta": root / META_NAME,
        "catalog": root / CATALOG_NAME,
        "observations": root / OBSERVATIONS_NAME,
        "yahoo_tr_log": root / YAHOO_LOG_NAME,
    }


def _file_stamp(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "mtime_ns": int(stat.st_mtime_ns),
        "size": int(stat.st_size),
    }


def _replacements_fingerprint(
    replacements: dict[str, str] | None = None,
) -> list[list[str]]:
    mapping = replacements if replacements is not None else YAHOO_TR_REPLACEMENTS
    return [[isin, ticker] for isin, ticker in sorted(mapping.items())]


def panel_cache_fingerprint(
    workbook: Path,
    *,
    sheet_name: str,
    freeze_dir: Path | None = None,
    replacements: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Inputs that must match for a sidecar hit."""
    workbook = Path(workbook).resolve()
    freeze_root = resolve_yahoo_tr_freeze_dir(freeze_dir)
    manifest = freeze_root / "manifest.json"
    return {
        "cache_version": CACHE_VERSION,
        "sheet_name": sheet_name,
        "workbook": _file_stamp(workbook),
        "yahoo_freeze_manifest": (
            _file_stamp(manifest) if manifest.is_file() else None
        ),
        "yahoo_tr_replacements": _replacements_fingerprint(replacements),
    }


def _fingerprints_match(stored: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        stored.get("cache_version") == expected.get("cache_version")
        and stored.get("sheet_name") == expected.get("sheet_name")
        and stored.get("workbook") == expected.get("workbook")
        and stored.get("yahoo_freeze_manifest")
        == expected.get("yahoo_freeze_manifest")
        and stored.get("yahoo_tr_replacements")
        == expected.get("yahoo_tr_replacements")
    )


def panel_cache_is_fresh(
    fingerprint: dict[str, Any],
    *,
    cache_dir: Path | None = None,
) -> bool:
    paths = panel_cache_paths(cache_dir)
    required = (
        paths["meta"],
        paths["catalog"],
        paths["observations"],
        paths["yahoo_tr_log"],
    )
    if not all(path.is_file() for path in required):
        return False
    try:
        meta = json.loads(paths["meta"].read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(meta, dict):
        return False
    stored = meta.get("fingerprint")
    return isinstance(stored, dict) and _fingerprints_match(stored, fingerprint)


def _observations_for_parquet(observations: pd.DataFrame) -> pd.DataFrame:
    frame = observations.copy()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize(None)
    frame.index.name = "date"
    frame.columns = [str(int(col)) for col in frame.columns]
    return frame


def _observations_from_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        if "date" in out.columns:
            out = out.set_index("date")
        out.index = pd.to_datetime(out.index, errors="coerce")
    out.index = pd.DatetimeIndex(out.index).tz_localize(None)
    out.index.name = "date"
    out.columns = [int(col) for col in out.columns]
    return out


def save_panel_cache(
    *,
    catalog: pd.DataFrame,
    observations: pd.DataFrame,
    yahoo_tr_log: pd.DataFrame,
    fingerprint: dict[str, Any],
    meta_fields: dict[str, Any],
    cache_dir: Path | None = None,
) -> Path:
    """Write the Step 1 sidecar. Returns the cache directory."""
    paths = panel_cache_paths(cache_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    catalog.to_parquet(paths["catalog"], index=False)
    _observations_for_parquet(observations).to_parquet(paths["observations"])
    yahoo_tr_log.to_parquet(paths["yahoo_tr_log"], index=False)
    payload = {
        "fingerprint": fingerprint,
        **meta_fields,
    }
    paths["meta"].write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return paths["root"]


def load_panel_cache(
    fingerprint: dict[str, Any],
    *,
    cache_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Return restored Step 1 objects, or ``None`` when the sidecar is stale."""
    if not panel_cache_is_fresh(fingerprint, cache_dir=cache_dir):
        return None
    paths = panel_cache_paths(cache_dir)
    meta = json.loads(paths["meta"].read_text())
    catalog = pd.read_parquet(paths["catalog"])
    observations = _observations_from_parquet(pd.read_parquet(paths["observations"]))
    yahoo_tr_log = pd.read_parquet(paths["yahoo_tr_log"])
    sample_end = meta.get("sample_end_date")
    return {
        "catalog": catalog,
        "observations": observations,
        "yahoo_tr_log": yahoo_tr_log,
        "label_rows": int(meta["label_rows"]),
        "sheet_name": str(meta["sheet_name"]),
        "columns_on_sheet": int(meta["columns_on_sheet"]),
        "columns_loaded": int(meta["columns_loaded"]),
        "columns_skipped": int(meta["columns_skipped"]),
        "columns_skipped_tna": int(meta["columns_skipped_tna"]),
        "columns_skipped_composite_price": int(
            meta["columns_skipped_composite_price"]
        ),
        "sample_end_date": (
            pd.Timestamp(sample_end) if sample_end is not None else None
        ),
        "yahoo_tr_download_date": meta.get("yahoo_tr_download_date"),
        "loaded_from_cache": True,
        "cache_dir": paths["root"],
    }


def load_or_build_panel_cache(
    *,
    workbook: Path,
    sheet_name: str,
    build,
    freeze_dir: Path | None = None,
    replacements: dict[str, str] | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Restore from Parquet when fresh; otherwise call ``build`` and save.

    ``build`` must return a dict with the same keys as :func:`load_panel_cache`
    (except ``loaded_from_cache`` / ``cache_dir``).
    """
    fingerprint = panel_cache_fingerprint(
        workbook,
        sheet_name=sheet_name,
        freeze_dir=freeze_dir,
        replacements=replacements,
    )
    cached = load_panel_cache(fingerprint, cache_dir=cache_dir)
    if cached is not None:
        return cached

    built = build()
    meta_fields = {
        "label_rows": int(built["label_rows"]),
        "sheet_name": str(built["sheet_name"]),
        "columns_on_sheet": int(built["columns_on_sheet"]),
        "columns_loaded": int(built["columns_loaded"]),
        "columns_skipped": int(built["columns_skipped"]),
        "columns_skipped_tna": int(built["columns_skipped_tna"]),
        "columns_skipped_composite_price": int(
            built["columns_skipped_composite_price"]
        ),
        "sample_end_date": (
            None
            if built.get("sample_end_date") is None
            else str(pd.Timestamp(built["sample_end_date"]).date())
        ),
        "yahoo_tr_download_date": built.get("yahoo_tr_download_date"),
    }
    cache_root = save_panel_cache(
        catalog=built["catalog"],
        observations=built["observations"],
        yahoo_tr_log=built["yahoo_tr_log"],
        fingerprint=fingerprint,
        meta_fields=meta_fields,
        cache_dir=cache_dir,
    )
    return {
        **built,
        "loaded_from_cache": False,
        "cache_dir": cache_root,
    }
