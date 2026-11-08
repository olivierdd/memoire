import io
import json
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from helpers.timeseries_functions.load_workbook import find_workbook

from helpers.timeseries_functions.check_timeseries_consistency import (
    check_timeseries_consistency,
)
from helpers.timeseries_functions.compute_fund_to_index_regression import (
    FundIndexRegressionResult,
)


def source_comparison_frame(
    compared: pd.DataFrame,
    master_column: str,
    comparison_column: str,
    gap: pd.Series,
    mismatch: pd.Series,
    match_tolerance: float,
) -> pd.DataFrame:
    """One row per month, with the match class used in the notebook."""
    required = {"Period", "Date", master_column, comparison_column}
    missing = required - set(compared.columns)
    if missing:
        raise KeyError(f"compared is missing {', '.join(sorted(missing))}")
    same_index = gap.index.equals(compared.index) and mismatch.index.equals(
        compared.index
    )
    if not same_index:
        raise ValueError("gap and mismatch must use the same index as compared")

    master = compared[master_column]
    other = compared[comparison_column]
    both_missing = master.isna() & other.isna()
    one_missing = master.isna() ^ other.isna()
    perfect = both_missing | gap.eq(0)
    acceptable = ~perfect & ~one_missing & gap.le(match_tolerance)
    status = np.select(
        [perfect.to_numpy(), acceptable.to_numpy()],
        ["perfect", "acceptable"],
        default="mismatch",
    )
    recorded = mismatch.fillna(False).to_numpy(dtype=bool)
    if not np.array_equal(status == "mismatch", recorded):
        raise ValueError("mismatch does not match the gaps in compared")

    frame = compared[["Period", "Date", master_column, comparison_column]].copy()
    frame["gap"] = gap.to_numpy()
    frame["gap_bp"] = (master - other).to_numpy() * 1e4
    frame["match"] = status
    return frame


def comparison_summary(
    comparison: pd.DataFrame,
    *,
    master_timeseries: str,
    comparison_timeseries: str,
    master_column: str,
    comparison_column: str,
    match_tolerance: float,
) -> dict:
    match = comparison["match"]
    one_missing = comparison[master_column].isna() ^ comparison[comparison_column].isna()
    return {
        "master_timeseries": master_timeseries,
        "comparison_timeseries": comparison_timeseries,
        "master_column": master_column,
        "comparison_column": comparison_column,
        "match_tolerance": float(match_tolerance),
        "n_months": int(len(comparison)),
        "perfect_matches": int(match.eq("perfect").sum()),
        "acceptable_matches": int(match.eq("acceptable").sum()),
        "mismatches": int(match.eq("mismatch").sum()),
        "one_side_missing": int(one_missing.sum()),
    }


def consistency_report(
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    comparison_column: str,
    *,
    master_timeseries: str,
    comparison_timeseries: str,
    spike_return: float,
    reversal_band: float,
    scale_factor: float,
    scale_window: int,
    level_jump: float,
    index_gap: float,
    date_gap_days: int,
) -> str:
    """The consistency cell's printed text, captured for the folder."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        check_timeseries_consistency(
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
    return buffer.getvalue()


_FUNDS_STATIC_FIELDS = {
    "Instrument Type": "instrument_type",
    "RIC": "ric",
    "Benchmark Name": "benchmark_name",
    "Total Expense Ratio": "total_expense_ratio",
    "Fund Inception Date": "fund_inception_date",
}


def fund_identity(isin: str, selected: pd.Series) -> dict:
    """Core identifiers used in overview and regression payloads."""
    return fund_static_description(
        isin,
        selected,
        relative=Path("input-data-alix") / "clean",
        filename="CLEAN_RECOLTE DONNEES-EXCEL.xlsx",
    )


def fund_static_description(
    isin: str,
    selected: pd.Series,
    *,
    relative: Path,
    filename: str,
) -> dict:
    """Static fund profile from the Timeseries fund list and the Funds sheet."""
    ticker = selected.get("market_identifier")
    payload: dict[str, object] = {
        "isin": isin,
        "name": str(selected["Name"]),
        "market_identifier": None if pd.isna(ticker) else str(ticker),
        "fund_wrapper": _optional_string(selected.get("fund_wrapper")),
        "fund_type": _optional_string(selected.get("fund_type")),
    }
    lipper = _funds_sheet_row(isin, relative, filename)
    if lipper is not None:
        for sheet_column, key in _FUNDS_STATIC_FIELDS.items():
            payload[key] = json_ready(lipper.get(sheet_column))
    return payload


def _funds_sheet_row(isin: str, relative: Path, filename: str) -> pd.Series | None:
    try:
        workbook = find_workbook(relative, filename)
    except FileNotFoundError:
        return None
    funds = pd.read_excel(
        workbook,
        sheet_name="Funds",
        engine="openpyxl",
        dtype={"ISIN": "string", "RIC": "string"},
    )
    match = funds.loc[funds["ISIN"].astype(str).eq(isin)]
    if match.empty:
        return None
    return match.iloc[0]


def _optional_string(value: object) -> str | None:
    if pd.isna(value):
        return None
    return str(value)


def check_parameters(**kwargs: object) -> dict:
    return {key: json_ready(value) for key, value in kwargs.items()}


def regression_payload(
    result: FundIndexRegressionResult,
    *,
    fund_name: str,
    master_timeseries: str,
    index_column: str,
) -> dict:
    sample = result.regression_sample
    start = pd.Timestamp(sample["Date"].min())
    end = pd.Timestamp(sample["Date"].max())
    alpha = float(result.alpha)
    beta = float(result.beta)
    return {
        "fund_name": fund_name,
        "master_timeseries": master_timeseries,
        "index_column": index_column,
        "equation": (
            f"{master_timeseries} = {alpha:+.2%} + {beta:.3f} × {index_column}"
        ),
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "alpha_bp_per_month": alpha * 1e4,
        "statistics": {
            key: json_ready(value) for key, value in result.regression.items()
        },
    }


def worst_mismatch_table(date_check: pd.DataFrame | None) -> pd.DataFrame | None:
    if date_check is None or date_check.empty:
        return None
    frame = date_check.copy()
    if "varied" not in frame.columns:
        frame = frame.reset_index()
    required = {"varied", "Date", "gap", "recorded"}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(
            f"worst-mismatch table is missing {', '.join(sorted(missing))}"
        )
    return frame.reset_index(drop=True)


def worst_mismatch_summary(
    drilldown: pd.DataFrame,
    *,
    master_timeseries: str,
    match_tolerance: float,
) -> dict:
    observation = _closest_session(drilldown, "observation date")
    start = _closest_session(drilldown, "start date")
    if float(observation["gap"]) <= float(start["gap"]):
        best = observation
        role = "observation date"
    else:
        best = start
        role = "start date"
    best_date = pd.Timestamp(best["Date"])
    best_gap = float(best["gap"])
    recorded = drilldown.loc[
        drilldown["varied"].eq(role) & drilldown["recorded"].astype(bool)
    ]
    if recorded.empty:
        raise ValueError(f"worst-mismatch table has no recorded {role}")
    recorded_date = pd.Timestamp(recorded.iloc[0]["Date"])
    date_mismatch = best_gap <= match_tolerance and best_date != recorded_date
    if date_mismatch:
        conclusion = (
            f"Using {best_date:%Y-%m-%d} as the {role} reproduces the "
            f"{master_timeseries} return (gap {best_gap:.6f}). "
            "The difference comes from a date mismatch."
        )
    else:
        conclusion = (
            f"No saved nearby session reproduces the {master_timeseries} return "
            f"within {match_tolerance:.4f}. "
            f"Closest is {best_date:%Y-%m-%d} as the {role} (gap {best_gap:.6f}). "
            "The difference does not come from a nearby date mismatch."
        )
    return {
        "best_role": role,
        "best_date": best_date.strftime("%Y-%m-%d"),
        "best_gap": best_gap,
        "recorded_date": recorded_date.strftime("%Y-%m-%d"),
        "within_tolerance": bool(best_gap <= match_tolerance),
        "date_mismatch": date_mismatch,
        "conclusion": conclusion,
    }


def charts_html(result: FundIndexRegressionResult) -> str:
    """Notebook charts as one HTML page. Vega is loaded from a CDN when opened."""
    chart = result.returns_chart & result.regression_chart
    return chart.to_html()


def frame_csv(frame: pd.DataFrame, *, index: bool = False) -> str:
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.strftime("%Y-%m-%d")
    return out.to_csv(index=index, lineterminator="\n")


def dumps(payload: dict) -> str:
    return json.dumps(payload, indent=2, allow_nan=False) + "\n"


def json_ready(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not np.isfinite(number):
            return None
        return number
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"Cannot store {type(value).__name__} in the check JSON")


def _closest_session(drilldown: pd.DataFrame, varied: str) -> pd.Series:
    group = drilldown.loc[drilldown["varied"].eq(varied)]
    if group.empty:
        raise ValueError(f"worst-mismatch table has no {varied!r} rows")
    return group.loc[group["gap"].idxmin()]
