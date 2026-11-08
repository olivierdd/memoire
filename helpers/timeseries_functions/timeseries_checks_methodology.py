"""Thesis-style documentation for the timeseries-checks export (Methodology sheet)."""

from __future__ import annotations

METHODOLOGY_SHEET_NAME = "Methodology"

METHODOLOGY_ROWS: list[tuple[str | None, str]] = [
    (
        "Purpose",
        "This workbook consolidates monthly return timeseries quality checks and "
        "index regressions produced by the fund timeseries notebook and batch runner. "
        "Each row on the Timeseries-checks sheet corresponds to one ISIN whose results "
        "were saved under output-data/timeseries-checks/<ISIN>/. The workbook is "
        "regenerated on each export; computed columns refresh and Decision fields "
        "reset to defaults.",
    ),
    (
        "Unit of observation",
        "One row per fund (ISIN) with a completed check folder (manifest.json). "
        "Funds not yet checked are omitted until the batch writes their cache folder.",
    ),
    (
        "Master and comparison series",
        "Lipper is the master monthly total-return series; Yahoo Finance is the "
        "comparison series. The Timeseries sheet has no per-fund NAV date, so "
        "observation dates start from the S&P 500 TR index calendar in "
        "cache-sp500-tr-indices.json. Before comparison, each fund-month may "
        "shift by up to six sessions when Yahoo reproduces Lipper's return only "
        "on a nearby date (parameters.json date_resolution). Fund, Yahoo, "
        "FinanceDatabase, and index returns on a row then share that resolved "
        "window. Month-to-month agreement uses a match tolerance of 0.0001 "
        "(1 basis point in decimal return units).",
    ),
    (
        "Check: Lipper vs Yahoo",
        "Counts of perfect, acceptable, and mismatching months come from "
        "source-comparison-summary.json. Shifted dates is the count of fund-months "
        "whose resolved Date differs from the index calendar (quality-summary.json "
        "shifted_months). When mismatches remain, worst-mismatch-summary.json "
        "records whether a nearby Yahoo session would still reconcile the Lipper "
        "return (typically not, after resolution). Result labels: Match (no "
        "mismatches), Date alignment (mismatches explained by session dating on "
        "legacy caches), Mismatch (unresolved gaps), Not comparable (no comparison "
        "data).",
    ),
    (
        "Check: series quality",
        "Gaps, abnormal spikes, lasting scale shifts, level jumps, and index divergence "
        "are recomputed from fund-timeseries.csv using the same rules as "
        "check_timeseries_consistency (thresholds in parameters.json). Lipper and Yahoo "
        "are checked separately. Quality Result is Match when gap, spike, scale, and "
        "level-jump counts are all zero; index divergence counts are diagnostic only.",
    ),
    (
        "Check: vs Lipper Funds",
        "Horizon deltas (3y, 5y, 10y) come from lipper-regression-comparison.csv. "
        "Export columns use percentage points: Δ Alpha mo is pp/mo; Δ TE is annualized pp "
        "(same units as the CSV after removing the % sign). Result is Match when |Δβ|≤0.05, "
        "|ΔR²|≤0.05, |Δ alpha mo|≤0.05 pp/mo, and |Δ TE|≤0.5 pp on every horizon with "
        "Lipper reference data; otherwise Mismatch. This compares notebook OLS to Lipper’s "
        "precomputed Funds-sheet stats (independent of the Consolidation tab).",
    ),
    (
        "Check: vs Consolidation",
        "Uses consolidation-regression-comparison.csv on the fixed Consolidation window "
        "(AE6–AE5) with the same Lipper returns as the Excel Timeseries tab. This confirms "
        "the Python pipeline reproduces the Consolidation sheet row; it does not validate "
        "Lipper against an external source. Result labels: Recreates sheet (within tight "
        "reproduction tolerances), Drifts from sheet (notebook OLS differs from the tab), "
        "Not comparable (no comparison file).",
    ),
    (
        "Check: regression",
        "Full-sample OLS of Lipper on the index is taken from regression.json (alpha in "
        "bp/mo on the main sheet). Lipper Funds and Consolidation comparisons are described "
        "in the sections above.",
    ),
    (
        "Result column colors",
        "Match and Recreates sheet (green), Mismatch and Drifts from sheet (red), "
        "Not comparable (grey), and Date alignment (same styling as Match on the Yahoo "
        "check) follow the Edgar-checks workbook.",
    ),
    (
        "Decision columns",
        "Include fund defaults to TRUE. Excluded months (summary) and Excluded month "
        "count are for manual review; they are blank or zero on export. Re-running the "
        "batch export clears any edits to Decision and Regression-exclusions.",
    ),
    (
        "Regression-exclusions sheet",
        "One row per fund month in the full-sample regression (regression-sample.csv). "
        "Set Exclude to TRUE to record months that should be dropped from a revised "
        "regression; the main sheet summary columns are maintained by the analyst.",
    ),
    (
        "Workbook size",
        "The exclusions sheet scales with the number of funds checked and regression "
        "months (~200 rows per fund). Large batch runs produce large but Excel-compatible "
        "workbooks.",
    ),
]
