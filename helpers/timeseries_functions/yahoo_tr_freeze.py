"""Frozen Yahoo Price / TR levels for the Step 1 fund replacements."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from helpers.funds_functions.map_yahoo_timeseries import (
    fetch_yahoo_price_levels,
    fetch_yahoo_total_return_levels,
)

DEFAULT_FREEZE_DIR = Path("cache") / "yahoo-tr-replacements"
MANIFEST_NAME = "manifest.json"


def _code_root(start: Path | None = None) -> Path:
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        if (directory / "helpers").is_dir():
            return directory
    raise FileNotFoundError(f"Could not find helpers/, starting from {origin}")


def resolve_yahoo_tr_freeze_dir(freeze_dir: Path | None = None) -> Path:
    relative = DEFAULT_FREEZE_DIR if freeze_dir is None else Path(freeze_dir)
    if relative.is_absolute():
        return relative.resolve()
    try:
        return (_code_root() / relative).resolve()
    except FileNotFoundError:
        return (Path.cwd().resolve() / relative).resolve()


def _series_path(freeze_dir: Path, ticker: str, kind: str) -> Path:
    return freeze_dir / f"{ticker}_{kind}.csv"


def _read_level_csv(path: Path, ticker: str) -> pd.Series | None:
    if not path.is_file():
        return None
    frame = pd.read_csv(path)
    if frame.empty or "date" not in frame.columns or "level" not in frame.columns:
        return None
    levels = pd.Series(
        pd.to_numeric(frame["level"], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame["date"], errors="coerce"),
        name=ticker,
        dtype="float64",
    )
    levels = levels[levels.index.notna() & levels.notna()]
    if levels.empty:
        return None
    levels.index = pd.DatetimeIndex(levels.index).tz_localize(None).normalize()
    levels = levels[~levels.index.duplicated(keep="last")].sort_index()
    return levels


def load_freeze_manifest(freeze_dir: Path | None = None) -> dict:
    path = resolve_yahoo_tr_freeze_dir(freeze_dir) / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def yahoo_tr_freeze_download_date(freeze_dir: Path | None = None) -> str | None:
    manifest = load_freeze_manifest(freeze_dir)
    value = manifest.get("download_date")
    return str(value) if value else None


def load_frozen_yahoo_levels(
    ticker: str,
    *,
    kind: str,
    freeze_dir: Path | None = None,
) -> pd.Series | None:
    """Load a frozen Yahoo level series (`kind` is ``price`` or ``tr``)."""
    if kind not in {"price", "tr"}:
        raise ValueError(f"kind must be 'price' or 'tr', got {kind!r}")
    directory = resolve_yahoo_tr_freeze_dir(freeze_dir)
    return _read_level_csv(_series_path(directory, ticker, kind), ticker)


def load_frozen_yahoo_price_levels(
    ticker: str, *, freeze_dir: Path | None = None
) -> pd.Series | None:
    return load_frozen_yahoo_levels(ticker, kind="price", freeze_dir=freeze_dir)


def load_frozen_yahoo_total_return_levels(
    ticker: str, *, freeze_dir: Path | None = None
) -> pd.Series | None:
    return load_frozen_yahoo_levels(ticker, kind="tr", freeze_dir=freeze_dir)


def fetch_yahoo_price_levels_prefer_freeze(
    ticker: str, *, freeze_dir: Path | None = None
) -> pd.Series | None:
    frozen = load_frozen_yahoo_price_levels(ticker, freeze_dir=freeze_dir)
    if frozen is not None:
        return frozen
    return fetch_yahoo_price_levels(ticker)


def fetch_yahoo_total_return_levels_prefer_freeze(
    ticker: str, *, freeze_dir: Path | None = None
) -> pd.Series | None:
    frozen = load_frozen_yahoo_total_return_levels(ticker, freeze_dir=freeze_dir)
    if frozen is not None:
        return frozen
    return fetch_yahoo_total_return_levels(ticker)


def _write_level_csv(path: Path, levels: pd.Series) -> None:
    frame = pd.DataFrame(
        {
            "date": pd.DatetimeIndex(levels.index).strftime("%Y-%m-%d"),
            "level": levels.to_numpy(),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def freeze_yahoo_tr_replacements(
    *,
    freeze_dir: Path | None = None,
    replacements: dict[str, str] | None = None,
    download_date: str | None = None,
    fetch_tr_levels=fetch_yahoo_total_return_levels,
    fetch_price_levels=fetch_yahoo_price_levels,
) -> dict:
    """Download Yahoo Price/TR for the replacement map and write a frozen extract.

    Returns the manifest that was written.
    """
    if replacements is None:
        from helpers.timeseries_functions.replace_yahoo_tr import YAHOO_TR_REPLACEMENTS

        mapping = dict(YAHOO_TR_REPLACEMENTS)
    else:
        mapping = dict(replacements)
    directory = resolve_yahoo_tr_freeze_dir(freeze_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamped = download_date or pd.Timestamp.now(tz="UTC").date().isoformat()
    tickers: dict[str, dict[str, str | int]] = {}

    for isin, ticker in mapping.items():
        tr_levels = fetch_tr_levels(ticker)
        price_levels = fetch_price_levels(ticker)
        if tr_levels is None or tr_levels.empty:
            raise RuntimeError(f"Yahoo TR empty for {ticker} ({isin})")
        if price_levels is None or price_levels.empty:
            raise RuntimeError(f"Yahoo Price empty for {ticker} ({isin})")
        tr_path = _series_path(directory, ticker, "tr")
        price_path = _series_path(directory, ticker, "price")
        _write_level_csv(tr_path, tr_levels)
        _write_level_csv(price_path, price_levels)
        tickers[ticker] = {
            "isin": isin,
            "tr_file": tr_path.name,
            "price_file": price_path.name,
            "tr_observations": int(tr_levels.notna().sum()),
            "price_observations": int(price_levels.notna().sum()),
            "tr_first_date": pd.Timestamp(tr_levels.index.min()).date().isoformat(),
            "tr_last_date": pd.Timestamp(tr_levels.index.max()).date().isoformat(),
            "price_first_date": pd.Timestamp(price_levels.index.min()).date().isoformat(),
            "price_last_date": pd.Timestamp(price_levels.index.max()).date().isoformat(),
        }

    manifest = {
        "download_date": stamped,
        "source": "yfinance",
        "price": "Close with auto_adjust=False (split-adjusted)",
        "total_return": "Close with auto_adjust=True (distributions reinvested)",
        "tickers": tickers,
    }
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
