"""Summarize locate_series_issues output for Excel export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from helpers.timeseries_functions.check_timeseries_consistency import (
    SeriesCheck,
    locate_timeseries_issues,
)

QUALITY_SUMMARY_FILENAME = "quality-summary.json"

__all__ = [
    "QUALITY_SUMMARY_FILENAME",
    "summarize_series_check",
    "quality_result_label",
    "compute_quality_summaries",
    "load_quality_summaries",
    "quality_summary_payload",
    "build_quality_summaries_from_cache",
]


def summarize_series_check(check: SeriesCheck) -> dict[str, Any]:
    """Counts and headline dates for one Lipper or Yahoo series."""
    frame = check.months
    gap_count = int(frame["gap"].sum())
    spike_count = int(frame["spike"].sum())
    level_jump_count = int(frame["level_jump"].sum())
    scale_shift = check.scale_at is not None
    scale_shift_date = None
    if check.scale_at is not None:
        scale_shift_date = pd.Timestamp(frame.at[check.scale_at, "Date"]).strftime(
            "%Y-%m-%d"
        )

    on_new_scale = frame["on_new_scale"]
    wide = frame["wide"]
    if check.scale_at is None:
        index_divergence_count = int(wide.sum())
    else:
        outside = wide & ~on_new_scale
        inside = wide & on_new_scale
        index_divergence_count = int(outside.sum() + inside.sum())

    largest_gap_bp = None
    largest_gap_date = None
    usable = frame["usable"]
    if usable.any():
        returns = frame["return"]
        market = frame["index_return"]
        distance = (returns - market).abs()
        gap_i = distance.where(usable).idxmax()
        largest_gap_bp = float((returns.at[gap_i] - market.at[gap_i]) * 1e4)
        largest_gap_date = pd.Timestamp(frame.at[gap_i, "Date"]).strftime("%Y-%m-%d")

    return {
        "gap_count": gap_count,
        "spike_count": spike_count,
        "scale_shift": scale_shift,
        "scale_shift_date": scale_shift_date,
        "level_jump_count": level_jump_count,
        "index_divergence_count": index_divergence_count,
        "largest_gap_bp": largest_gap_bp,
        "largest_gap_date": largest_gap_date,
    }


def quality_result_label(summary: dict[str, Any]) -> str:
    """Match if no gaps, spikes, scale shifts, or level jumps."""
    if (
        summary.get("gap_count", 0) == 0
        and summary.get("spike_count", 0) == 0
        and not summary.get("scale_shift")
        and summary.get("level_jump_count", 0) == 0
    ):
        return "Match"
    return "Mismatch"


def compute_quality_summaries(isin_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run series checks from cached CSV + parameters.json."""
    isin_dir = isin_dir.resolve()
    params_path = isin_dir / "inputs" / "parameters.json"
    ts_path = isin_dir / "inputs" / "fund-timeseries.csv"
    if not params_path.is_file() or not ts_path.is_file():
        empty = {
            "gap_count": None,
            "spike_count": None,
            "scale_shift": None,
            "scale_shift_date": None,
            "level_jump_count": None,
            "index_divergence_count": None,
            "largest_gap_bp": None,
            "largest_gap_date": None,
        }
        return empty, empty.copy()

    params = json.loads(params_path.read_text(encoding="utf-8"))
    fund_timeseries = pd.read_csv(ts_path, parse_dates=["Date"])

    checks = locate_timeseries_issues(
        fund_timeseries,
        params["index_column"],
        params["master_column"],
        params["comparison_column"],
        master_timeseries=params.get("master_timeseries", "Lipper"),
        comparison_timeseries=params.get("comparison_timeseries", "Yahoo"),
        spike_return=float(params["spike_return"]),
        reversal_band=float(params["reversal_band"]),
        scale_factor=float(params["scale_factor"]),
        scale_window=int(params["scale_window"]),
        level_jump=float(params["level_jump"]),
        index_gap=float(params["index_gap"]),
        date_gap_days=int(params["date_gap_days"]),
    )
    return summarize_series_check(checks[0]), summarize_series_check(checks[1])


def quality_summary_payload(
    lipper: dict[str, Any],
    yahoo: dict[str, Any],
    *,
    shifted_months: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"lipper": lipper, "yahoo": yahoo}
    if shifted_months is not None:
        payload["shifted_months"] = shifted_months
    return payload


def _quality_summary_path(isin_dir: Path) -> Path:
    return isin_dir / "outputs" / QUALITY_SUMMARY_FILENAME


def load_quality_summaries(
    isin_dir: Path,
    *,
    write_cache: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read cached quality-summary.json or compute (and optionally persist)."""
    path = _quality_summary_path(isin_dir)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        lipper = data.get("lipper") or {}
        yahoo = data.get("yahoo") or {}
        return lipper, yahoo

    lipper, yahoo = compute_quality_summaries(isin_dir)
    if write_cache and lipper.get("gap_count") is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(quality_summary_payload(lipper, yahoo), indent=2),
            encoding="utf-8",
        )
    return lipper, yahoo


def build_quality_summaries_from_cache(isin_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Backward-compatible alias for export row building."""
    return load_quality_summaries(isin_dir, write_cache=True)
