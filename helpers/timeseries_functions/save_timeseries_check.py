import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.compute_fund_to_index_regression import (
    FundIndexRegressionResult,
)
from helpers.timeseries_functions.timeseries_check_bundle import (
    charts_html,
    check_parameters,
    comparison_summary,
    consistency_report,
    dumps,
    frame_csv,
    fund_static_description,
    regression_payload,
    source_comparison_frame,
    worst_mismatch_summary,
    worst_mismatch_table,
)
from helpers.timeseries_functions.check_timeseries_consistency import (
    locate_timeseries_issues,
)
from helpers.timeseries_functions.series_check_summary import (
    quality_summary_payload,
    summarize_series_check,
)
from helpers.timeseries_functions.timeseries_check_overview import (
    manifest_payload,
    overview_markdown,
)

_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")

_FILE_ORDER = (
    "manifest.json",
    "overview.md",
    "inputs/fund-static.json",
    "inputs/parameters.json",
    "inputs/fund-timeseries.csv",
    "outputs/source-comparison.csv",
    "outputs/source-comparison-summary.json",
    "outputs/consistency-report.txt",
    "outputs/quality-summary.json",
    "outputs/regression.json",
    "outputs/regression-coefficients.csv",
    "outputs/regression-fit.csv",
    "outputs/regression-sample.csv",
    "outputs/lipper-regression-comparison.csv",
    "outputs/consolidation-regression-comparison.csv",
    "outputs/worst-mismatch.csv",
    "outputs/worst-mismatch-summary.json",
    "outputs/charts.html",
    "outputs/llm-evaluation-openai.json",
)


def find_project_root() -> Path:
    """Project root, whether the kernel cwd is code/ or notebooks/."""
    start = Path.cwd().resolve()
    for directory in [start, *start.parents]:
        if (directory / "pyproject.toml").is_file():
            return directory
    raise FileNotFoundError(f"Could not find pyproject.toml, starting from {start}")


def save_timeseries_check(
    *,
    selected_fund: str,
    selected: pd.Series,
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_timeseries: str,
    comparison_timeseries: str,
    match_tolerance: float,
    compared: pd.DataFrame,
    master_column: str,
    comparison_column: str,
    gap: pd.Series,
    mismatch: pd.Series,
    regression_result: FundIndexRegressionResult,
    lipper_regression_comparison: pd.DataFrame,
    consolidation_regression_comparison: pd.DataFrame,
    date_check: pd.DataFrame | None,
    spike_return: float,
    reversal_band: float,
    scale_factor: float,
    scale_window: int,
    level_jump: float,
    index_gap: float,
    date_gap_days: int,
    date_resolution: dict | None = None,
    shifted_months: dict | None = None,
    output_dir: Path | None = None,
    workbook_relative: Path = Path("input-data-alix") / "clean",
    workbook_filename: str = "CLEAN_RECOLTE DONNEES-EXCEL.xlsx",
    openai_llm_evaluation: dict | None = None,
) -> Path:
    """Write this fund's check under ``output-data/timeseries-checks/<ISIN>/``.

    The folder is replaced on each run. It holds the series that were checked
    and the tables, text, and chart the notebook produced, so a later agent
    can review the check or draft a report without reloading the workbook.
    """
    isin = _require_isin(selected_fund)
    comparison = source_comparison_frame(
        compared,
        master_column,
        comparison_column,
        gap,
        mismatch,
        match_tolerance,
    )
    summary = comparison_summary(
        comparison,
        master_timeseries=master_timeseries,
        comparison_timeseries=comparison_timeseries,
        master_column=master_column,
        comparison_column=comparison_column,
        match_tolerance=match_tolerance,
    )
    drilldown = worst_mismatch_table(date_check)
    drilldown_summary = None
    if drilldown is not None:
        drilldown_summary = worst_mismatch_summary(
            drilldown,
            master_timeseries=master_timeseries,
            match_tolerance=match_tolerance,
        )
    fund_static = fund_static_description(
        isin,
        selected,
        relative=workbook_relative,
        filename=workbook_filename,
    )
    parameters = check_parameters(
        master_timeseries=master_timeseries,
        comparison_timeseries=comparison_timeseries,
        index_column=index_column,
        master_column=master_column,
        comparison_column=comparison_column,
        match_tolerance=match_tolerance,
        spike_return=spike_return,
        reversal_band=reversal_band,
        scale_factor=scale_factor,
        scale_window=scale_window,
        level_jump=level_jump,
        index_gap=index_gap,
        date_gap_days=date_gap_days,
    )
    if date_resolution is not None:
        parameters["date_resolution"] = {
            key: json_ready(value) for key, value in date_resolution.items()
        }
    regression = regression_payload(
        regression_result,
        fund_name=str(fund_static["name"]),
        master_timeseries=master_timeseries,
        index_column=index_column,
    )
    series_checks = locate_timeseries_issues(
        fund_timeseries,
        index_column,
        master_column,
        comparison_column,
        master_timeseries=master_timeseries,
        comparison_timeseries=comparison_timeseries,
        spike_return=spike_return,
        reversal_band=reversal_band,
        scale_factor=scale_factor,
        scale_window=scale_window,
        level_jump=level_jump,
        index_gap=index_gap,
        date_gap_days=date_gap_days,
    )
    quality_summary = quality_summary_payload(
        summarize_series_check(series_checks[0]),
        summarize_series_check(series_checks[1]),
        shifted_months=shifted_months,
    )
    files = {
        "overview.md": overview_markdown(
            fund_static,
            parameters,
            summary,
            regression,
            drilldown_summary,
            shifted_months=shifted_months,
        ),
        "inputs/fund-static.json": dumps(fund_static),
        "inputs/parameters.json": dumps(parameters),
        "inputs/fund-timeseries.csv": frame_csv(fund_timeseries),
        "outputs/source-comparison.csv": frame_csv(comparison),
        "outputs/source-comparison-summary.json": dumps(summary),
        "outputs/consistency-report.txt": consistency_report(
            fund_timeseries,
            index_column,
            master_column,
            comparison_column,
            master_timeseries=master_timeseries,
            comparison_timeseries=comparison_timeseries,
            spike_return=spike_return,
            reversal_band=reversal_band,
            scale_factor=scale_factor,
            scale_window=scale_window,
            level_jump=level_jump,
            index_gap=index_gap,
            date_gap_days=date_gap_days,
        ),
        "outputs/quality-summary.json": dumps(quality_summary),
        "outputs/regression.json": dumps(regression),
        "outputs/regression-coefficients.csv": frame_csv(
            regression_result.coefficient_table, index=True
        ),
        "outputs/regression-fit.csv": frame_csv(
            regression_result.fit_table.to_frame(), index=True
        ),
        "outputs/regression-sample.csv": frame_csv(regression_result.regression_sample),
        "outputs/lipper-regression-comparison.csv": frame_csv(
            lipper_regression_comparison
        ),
        "outputs/consolidation-regression-comparison.csv": frame_csv(
            consolidation_regression_comparison
        ),
        "outputs/charts.html": charts_html(regression_result),
    }
    if openai_llm_evaluation is not None:
        files["outputs/llm-evaluation-openai.json"] = dumps(openai_llm_evaluation)
    if drilldown is not None and drilldown_summary is not None:
        files["outputs/worst-mismatch.csv"] = frame_csv(drilldown)
        files["outputs/worst-mismatch-summary.json"] = dumps(drilldown_summary)
    ordered = [path for path in _FILE_ORDER if path == "manifest.json" or path in files]
    document = manifest_payload(isin, str(fund_static["name"]), ordered)
    document["saved_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    files["manifest.json"] = dumps(document)
    ordered_files = {path: files[path] for path in ordered}

    folder = _replace_fund_dir(_checks_dir(output_dir), isin)
    for relative, content in ordered_files.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _announce(folder, list(ordered_files))
    return folder


def _require_isin(selected_fund: str) -> str:
    isin = str(selected_fund).strip()
    if not _ISIN.fullmatch(isin):
        raise ValueError(f"{selected_fund!r} is not a fund ISIN")
    return isin


def _checks_dir(output_dir: Path | None) -> Path:
    if output_dir is not None:
        return Path(output_dir)
    return find_project_root() / "output-data" / "timeseries-checks"


def _replace_fund_dir(parent: Path, isin: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    folder = parent / isin
    if folder.is_symlink():
        raise ValueError(f"Refusing to replace symlink {folder}")
    resolved = folder.resolve()
    if not resolved.is_relative_to(parent.resolve()):
        raise ValueError(f"Refusing to write outside {parent.resolve()}: {resolved}")
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    return folder


def _announce(folder: Path, relative_paths: list[str]) -> None:
    try:
        shown = folder.relative_to(find_project_root())
    except ValueError:
        shown = folder
    print(f"Saved timeseries check to {shown}")
    for relative in relative_paths:
        print(f"- {relative}")
