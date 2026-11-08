import json
from pathlib import Path

import pandas as pd

from helpers.timeseries_functions.compute_fund_to_index_regression import (
    FundIndexRegressionResult,
)
from helpers.timeseries_functions.save_timeseries_check import find_project_root
from helpers.timeseries_functions.timeseries_check_bundle import (
    check_parameters,
    comparison_summary,
    consistency_report,
    fund_static_description,
    regression_payload,
    source_comparison_frame,
    worst_mismatch_summary,
    worst_mismatch_table,
)

SYSTEM_PROMPT = """\
You are an experienced financial analyst who reviews mutual-fund and ETF data quality and index-tracking behaviour.

You answer only from the dossier in the user message. Do not use the fund's name, brand, or any outside knowledge of the product. Do not invent prices, dates, or statistics. The dossier does not include the fund's declared management style; do not infer it from the name or from memory.

Lipper is the master monthly total-return series. Yahoo is the comparison series. Both are aligned to the same observation dates as the S&P 500 total return. A return is the simple total return from the previous observation date to this one. The regression is ordinary least squares of the fund's monthly total return on the S&P 500 total return. Alpha is the intercept. No risk-free rate is subtracted. Alpha times 12 is a linear annualization, not a compound return. Lipper's published alpha is a monthly percent; its tracking error is an annualized percent. The figures in the dossier are already in the units stored by the check (decimal returns in the JSON, formatted text in the CSV tables).

Separate a data defect from an investment conclusion. A series can be reliable and still not be a passive S&P 500 tracker. A high R-squared shows that the fund moves with the market; it does not by itself show that the fund is an index fund. Index funds typically have a beta extremely close to 1 and an annualized tracking error well under 1 percent. A beta around 0.9 and a tracking error of a few percent can be a diversified active large-cap fund.

Score each of the four numeric questions from 0 to 1 inclusive. Use the interior of the scale. Reserve 0 and 1 for evidence that is unambiguous. For active management, 0 means the return behaviour is that of a passive fund tracking the index, and 1 means the return behaviour is that of an actively managed fund. A value near 0.5 means the evidence does not distinguish the two.

Every numeric answer must be justified by figures that appear in the dossier. If a figure is missing, say so and lower only the score that figure would have supported."""

USER_QUESTIONS = """\
Answer the following from the dossier only.

1. Is the price timeseries of the fund reliable? Score from 0 to 1.
2. Does the outcome demonstrate that the fund is tracking the S&P 500 total-return index? Score from 0 to 1.
3. Does the fund's return behaviour, compared with the index, indicate a passive or an actively managed fund? Score from 0 (passive) to 1 (active).
4. Are the computed regression parameters of good quality and consistent with the Lipper Funds sheet? Score from 0 to 1.
5. How should the timeseries quality checks be interpreted?
6. How should the regression be interpreted?

Return only JSON matching this shape (no markdown fences):

{
  "price_timeseries_reliable": 0.0,
  "tracks_sp500_tr": 0.0,
  "active_management": 0.0,
  "regression_quality": 0.0,
  "score_basis": {
    "price_timeseries_reliable": "one or two sentences citing dossier figures",
    "tracks_sp500_tr": "one or two sentences citing dossier figures",
    "active_management": "one or two sentences citing dossier figures",
    "regression_quality": "one or two sentences citing dossier figures"
  },
  "timeseries_interpretation": "short qualitative reading of the quality checks",
  "regression_interpretation": "short qualitative reading of the regression"
}"""

_JSON_RESPONSE_KEYS = (
    "price_timeseries_reliable",
    "tracks_sp500_tr",
    "active_management",
    "regression_quality",
)


def timeseries_check_dir(isin: str, *, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    path = root / "output-data" / "timeseries-checks" / isin
    if not path.is_dir():
        raise FileNotFoundError(f"No saved check folder at {path}")
    return path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv_records(path: Path) -> list[dict[str, object]]:
    frame = pd.read_csv(path)
    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            frame[column] = frame[column].dt.strftime("%Y-%m-%d")
    return frame.to_dict(orient="records")


def _fit_table(path: Path) -> dict[str, str]:
    frame = pd.read_csv(path, index_col=0)
    return {str(index): str(value) for index, value in frame["Value"].items()}


def _fund_profile_for_prompt(path: Path) -> dict:
    profile = _read_json(path)
    return _profile_for_prompt(profile)


def _profile_for_prompt(fund_static: dict) -> dict:
    profile = dict(fund_static)
    profile.pop("name", None)
    profile.pop("fund_type", None)
    return profile


def _dataframe_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.strftime("%Y-%m-%d")
    return out.to_dict(orient="records")


def _fit_table_from_series(fit_table: pd.Series) -> dict[str, str]:
    return {str(index): str(value) for index, value in fit_table.items()}


def _largest_index_gaps_from_sample(
    sample: pd.DataFrame,
    *,
    index_column: str,
    master_column: str,
    n: int = 8,
) -> list[dict[str, object]]:
    gap = sample[master_column] - sample[index_column]
    ranked = sample.assign(
        gap_vs_index=gap,
        gap_vs_index_bp=gap * 1e4,
    )
    ranked = ranked.loc[gap.abs().sort_values(ascending=False).index].head(n)
    columns = ["Period", "Date", index_column, master_column, "gap_vs_index", "gap_vs_index_bp"]
    return _dataframe_records(ranked[columns])


def _largest_index_gaps(
    sample_path: Path,
    *,
    index_column: str,
    master_column: str,
    n: int = 8,
) -> list[dict[str, object]]:
    sample = pd.read_csv(sample_path)
    return _largest_index_gaps_from_sample(
        sample,
        index_column=index_column,
        master_column=master_column,
        n=n,
    )


def build_dossier_from_run(
    *,
    selected_fund: str,
    selected: pd.Series,
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    comparison_column: str,
    master_timeseries: str,
    comparison_timeseries: str,
    match_tolerance: float,
    compared: pd.DataFrame,
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
    workbook_relative: Path,
    workbook_filename: str,
    shifted_months: dict | None = None,
) -> dict:
    """Same dossier shape as ``build_dossier``, from live notebook variables."""
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
    fund_static = fund_static_description(
        str(selected_fund),
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
    regression = regression_payload(
        regression_result,
        fund_name=str(fund_static["name"]),
        master_timeseries=master_timeseries,
        index_column=index_column,
    )
    mismatches = comparison.loc[comparison["match"].eq("mismatch")]

    dossier: dict[str, object] = {
        "parameters": parameters,
        "fund_profile": _profile_for_prompt(fund_static),
        "observation_date_shifts": shifted_months or {"count": 0, "months": []},
        "source_comparison_summary": summary,
        "source_comparison_mismatches": _dataframe_records(mismatches),
        "consistency_report": consistency_report(
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
        "regression": regression,
        "regression_coefficients": _dataframe_records(
            regression_result.coefficient_table.reset_index()
        ),
        "regression_fit": _fit_table_from_series(regression_result.fit_table),
        "largest_index_gaps_months": _largest_index_gaps_from_sample(
            regression_result.regression_sample,
            index_column=index_column,
            master_column=master_column,
        ),
        "lipper_regression_comparison": _dataframe_records(lipper_regression_comparison),
        "consolidation_regression_comparison": _dataframe_records(
            consolidation_regression_comparison
        ),
    }

    drilldown = worst_mismatch_table(date_check)
    if drilldown is not None:
        dossier["worst_mismatch"] = worst_mismatch_summary(
            drilldown,
            master_timeseries=master_timeseries,
            match_tolerance=match_tolerance,
        )

    return dossier


def build_dossier(check_dir: Path) -> dict:
    """Structured context for LLM evaluation from a saved timeseries-check folder."""
    params = _read_json(check_dir / "inputs/parameters.json")
    index_column = str(params["index_column"])
    master_column = str(params["master_column"])

    comparison = pd.read_csv(check_dir / "outputs/source-comparison.csv")
    mismatches = comparison.loc[comparison["match"].eq("mismatch")].copy()
    for column in mismatches.columns:
        if pd.api.types.is_datetime64_any_dtype(mismatches[column]):
            mismatches[column] = mismatches[column].dt.strftime("%Y-%m-%d")

    quality = _read_json(check_dir / "outputs/quality-summary.json")
    shifted = (quality or {}).get("shifted_months") or {"count": 0, "months": []}

    dossier: dict[str, object] = {
        "parameters": params,
        "fund_profile": _fund_profile_for_prompt(check_dir / "inputs/fund-static.json"),
        "observation_date_shifts": shifted,
        "source_comparison_summary": _read_json(
            check_dir / "outputs/source-comparison-summary.json"
        ),
        "source_comparison_mismatches": mismatches.to_dict(orient="records"),
        "consistency_report": (
            check_dir / "outputs/consistency-report.txt"
        ).read_text(encoding="utf-8"),
        "regression": _read_json(check_dir / "outputs/regression.json"),
        "regression_coefficients": _csv_records(
            check_dir / "outputs/regression-coefficients.csv"
        ),
        "regression_fit": _fit_table(check_dir / "outputs/regression-fit.csv"),
        "largest_index_gaps_months": _largest_index_gaps(
            check_dir / "outputs/regression-sample.csv",
            index_column=index_column,
            master_column=master_column,
        ),
        "lipper_regression_comparison": _csv_records(
            check_dir / "outputs/lipper-regression-comparison.csv"
        ),
    }
    consolidation_path = check_dir / "outputs/consolidation-regression-comparison.csv"
    if consolidation_path.is_file():
        dossier["consolidation_regression_comparison"] = _csv_records(consolidation_path)

    worst_path = check_dir / "outputs/worst-mismatch-summary.json"
    if worst_path.is_file():
        dossier["worst_mismatch"] = _read_json(worst_path)

    return dossier


def dossier_json(dossier: dict) -> str:
    return json.dumps(dossier, indent=2, ensure_ascii=False)


def build_user_prompt(dossier: dict) -> str:
    return f"{USER_QUESTIONS}\n\n## Dossier\n\n{dossier_json(dossier)}"


def parse_generative_response(text: str) -> dict:
    """Parse model JSON, tolerating optional markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Response JSON must be an object")
    return payload
