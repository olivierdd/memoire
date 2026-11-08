FILE_NOTES = {
    "overview.md": "Reading order, comparison counts, and the regression headline.",
    "manifest.json": "List of every file in this folder.",
    "inputs/fund-static.json": (
        "Static fund profile: ISIN, name, vehicle, management style, "
        "market identifier, benchmark, fees, and Lipper metadata from the Funds sheet."
    ),
    "inputs/parameters.json": "Which series were compared, and the thresholds used.",
    "inputs/fund-timeseries.csv": (
        "Monthly total returns on resolved observation dates (per fund-month), "
        "including index date, session shifts, index source, and every series column."
    ),
    "outputs/source-comparison.csv": (
        "Master and comparison return each month, the gap, and the match class."
    ),
    "outputs/source-comparison-summary.json": (
        "Counts of perfect matches, acceptable matches, and mismatches."
    ),
    "outputs/consistency-report.txt": (
        "Gaps, spikes, scale shifts, and index divergence. "
        "Same text as the consistency cell: master first, then comparison."
    ),
    "outputs/quality-summary.json": (
        "Structured Lipper and Yahoo quality counts for export (gaps, spikes, scale, index), "
        "plus shifted_months when observation dates were adjusted."
    ),
    "outputs/regression.json": "OLS of the master monthly return on the index.",
    "outputs/regression-coefficients.csv": "Coefficient table shown in the notebook.",
    "outputs/regression-fit.csv": "Fit statistics shown in the notebook.",
    "outputs/regression-sample.csv": "Months used in the full-sample regression.",
    "outputs/lipper-regression-comparison.csv": (
        "Notebook OLS against the Funds sheet, for the full sample and "
        "for 3-, 5-, and 10-year windows. Cells are formatted text."
    ),
    "outputs/consolidation-regression-comparison.csv": (
        "Notebook OLS on the Consolidation sheet window (AE6–AE5) "
        "compared to that sheet’s per-fund regression row."
    ),
    "outputs/worst-mismatch.csv": (
        "Nearby sessions tested for the largest master–comparison gap."
    ),
    "outputs/worst-mismatch-summary.json": (
        "Whether a nearby session reproduces the master return."
    ),
    "outputs/charts.html": "Monthly returns and the fitted regression line.",
    "outputs/llm-evaluation-openai.json": (
        "OpenAI review of the check: four scores (0–1), score basis, "
        "and qualitative readings of the quality checks and regression."
    ),
    "outputs/fund-timeseries-report.pptx": (
        "PowerPoint summary of the timeseries check: fund profile, "
        "source agreement, regression, quality bullets, and charts."
    ),
}


def overview_markdown(
    fund_static: dict,
    parameters: dict,
    summary: dict,
    regression: dict,
    drilldown_summary: dict | None,
    *,
    shifted_months: dict | None = None,
) -> str:
    """Guide an agent through the saved check."""
    ticker = fund_static.get("market_identifier") or "none"
    wrapper = fund_static.get("fund_wrapper") or "unknown"
    management = fund_static.get("fund_type") or "unknown"
    benchmark = fund_static.get("benchmark_name")
    tolerance = parameters["match_tolerance"]
    annualized = regression["statistics"]["alpha_annualized"]
    lines = [
        f"# {fund_static['name']} ({fund_static['isin']})",
        "",
        f"Market identifier: {ticker}",
        f"Vehicle: {wrapper}; management: {management}",
        "",
        "This folder is the timeseries check for one fund. "
        "Monthly figures are simple total returns between consecutive "
        "resolved observation dates, as decimals (`0.0276` is +2.76%). "
        "Dates default to the index-derived calendar unless Lipper's return "
        "required a nearby session shift (see `inputs/parameters.json` "
        "`date_resolution` and `outputs/quality-summary.json` `shifted_months`).",
        "",
        f"Master series: {parameters['master_timeseries']} "
        f"(`{parameters['master_column']}`)",
        f"Comparison series: {parameters['comparison_timeseries']} "
        f"(`{parameters['comparison_column']}`)",
        f"Index: {parameters['index_column']}",
        f"Match tolerance: {tolerance} ({tolerance * 1e4:.1f} bp)",
        *(
            [f"Lipper benchmark: {benchmark}", ""]
            if benchmark
            else []
        ),
        "## Reading order",
        "",
        "1. `inputs/fund-static.json` — static fund profile (vehicle, benchmark, fees).",
        "2. `outputs/source-comparison-summary.json` and "
        "`outputs/source-comparison.csv` — month-by-month agreement.",
        "3. `outputs/consistency-report.txt` — gaps, abnormal spikes, "
        "scale shifts, and months far from the index.",
        "4. `outputs/regression.json`, `outputs/regression-coefficients.csv`, "
        "and `outputs/regression-fit.csv` — OLS of the master return on the index.",
        "5. `outputs/lipper-regression-comparison.csv` — that OLS on the full "
        "sample and on 3-, 5-, and 10-year windows, next to the Funds sheet.",
        "6. `outputs/consolidation-regression-comparison.csv` — the same OLS "
        "on the Consolidation analysis window, next to the Consolidation sheet.",
        "7. `outputs/worst-mismatch-summary.json` and "
        "`outputs/worst-mismatch.csv` — nearby sessions for the largest gap, "
        "when that drill-down ran.",
        "8. `outputs/charts.html` — monthly returns and the fitted line. "
        "Open it in a browser; the page loads Vega from a CDN. "
        "The numbers are in the JSON and CSV files.",
        "9. `inputs/fund-timeseries.csv` — every aligned monthly series, "
        "including sources that were not the master or the comparison.",
        "10. `inputs/parameters.json` — series names and thresholds.",
        "",
        "## Source comparison",
        "",
        f"- Perfect matches (identical, or both missing): "
        f"{summary['perfect_matches']} of {summary['n_months']}",
        f"- Acceptable matches (absolute gap ≤ {tolerance}): "
        f"{summary['acceptable_matches']} of {summary['n_months']}",
        f"- Mismatches: {summary['mismatches']} of {summary['n_months']}",
        *(
            [
                f"- Observation dates shifted from index calendar: "
                f"{shifted_months.get('count', 0)} month(s)",
            ]
            if shifted_months
            else []
        ),
        "",
        "`match` is `perfect`, `acceptable`, or `mismatch`. "
        "`gap` is the absolute difference. "
        "`gap_bp` is signed, master minus comparison, in basis points. "
        "A mismatch includes a month where only one series is present "
        f"({summary['one_side_missing']} such months). "
        "Stale-NAV notes stay in the notebook output; copying them would "
        "download Yahoo prices again.",
        "",
        "## Regression",
        "",
        regression["equation"],
        "",
        f"{regression['statistics']['n_months']} months, "
        f"{regression['start']} to {regression['end']}. "
        f"Alpha is {regression['alpha_bp_per_month']:+.1f} bp per month "
        f"({annualized:+.2%} annualized, × 12).",
        "",
        "## Worst mismatch",
        "",
        (
            "This run has no worst-mismatch table."
            if drilldown_summary is None
            else drilldown_summary["conclusion"]
        ),
        "",
    ]
    return "\n".join(lines)


def manifest_payload(isin: str, name: str, paths: list[str]) -> dict:
    unknown = [path for path in paths if path not in FILE_NOTES]
    if unknown:
        raise KeyError(f"No description for {', '.join(unknown)}")
    return {
        "isin": isin,
        "name": name,
        "purpose": (
            "Inputs and outputs of one fund timeseries check, "
            "for an agent that reviews the check or drafts a report."
        ),
        "files": [{"path": path, "description": FILE_NOTES[path]} for path in paths],
    }
