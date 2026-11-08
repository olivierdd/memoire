import pandas as pd

from helpers.timeseries_functions.compare_timeseries_sources import (
    DEFAULT_COMPARISON_TIMESERIES,
    DEFAULT_MASTER_TIMESERIES,
    DEFAULT_MATCH_TOLERANCE,
)
from helpers.timeseries_functions.yahoo_daily_levels import yahoo_daily_levels

DEFAULT_NEARBY_SESSIONS = 6


def diagnose_worst_mismatch(
    fund_timeseries: pd.DataFrame,
    compared: pd.DataFrame,
    gap: pd.Series,
    mismatch: pd.Series,
    master_column: str,
    comparison_column: str,
    selected: pd.Series,
    selected_fund: str,
    *,
    master_timeseries: str = DEFAULT_MASTER_TIMESERIES,
    comparison_timeseries: str = DEFAULT_COMPARISON_TIMESERIES,
    match_tolerance: float = DEFAULT_MATCH_TOLERANCE,
    nearby_sessions: int = DEFAULT_NEARBY_SESSIONS,
    yahoo_level: pd.Series | None = None,
) -> pd.DataFrame | None:
    """Drill into the largest master–comparison gap with nearby Yahoo sessions."""
    if not mismatch.any():
        print("No mismatches to diagnose.")
        return None

    if comparison_timeseries != "Yahoo":
        print(
            "Worst-mismatch drill-down uses Yahoo daily levels; "
            f"comparison is {comparison_timeseries}, skipping."
        )
        return None

    picked_index = gap.loc[mismatch].idxmax()
    picked = compared.loc[picked_index]
    picked_date = pd.Timestamp(picked["Date"])
    master_return = float(picked[master_column])
    start_date = fund_timeseries.loc[
        fund_timeseries["Date"] < picked_date, "Date"
    ].max()
    if pd.isna(start_date):
        print("Cannot diagnose the first observation (no prior date).")
        return None

    if yahoo_level is None:
        _, _, yahoo_level = yahoo_daily_levels(
            fund_timeseries,
            selected,
            selected_fund,
        )
    closes = yahoo_level

    def nearby(center):
        loc = closes.index.get_loc(pd.Timestamp(center))
        if isinstance(loc, slice):
            raise ValueError(f"Ambiguous Yahoo session for {center}")
        start = max(loc - nearby_sessions, 0)
        return closes.iloc[start : loc + nearby_sessions + 1]

    def recomputed(center, fixed, varying):
        """Move one endpoint across nearby sessions and keep the other fixed."""
        prices = nearby(center)
        fixed_ts = pd.Timestamp(fixed)
        if varying == "observation date":
            returns = prices / closes.loc[fixed_ts] - 1
        else:
            returns = closes.loc[fixed_ts] / prices - 1
        frame = pd.DataFrame({"Level": prices, "return": returns})
        frame["gap"] = (frame["return"] - master_return).abs()
        frame["recorded"] = frame.index == pd.Timestamp(center)
        return frame

    start_check = recomputed(start_date, picked_date, "start date")
    end_check = recomputed(picked_date, start_date, "observation date")
    best_end = end_check["gap"].idxmin()
    best_start = start_check["gap"].idxmin()
    best_is_end = end_check.loc[best_end, "gap"] <= start_check.loc[best_start, "gap"]
    best_date = best_end if best_is_end else best_start
    best_role = "observation date" if best_is_end else "start date"
    best_gap = float(
        end_check.loc[best_end, "gap"]
        if best_is_end
        else start_check.loc[best_start, "gap"]
    )
    recorded_date = picked_date if best_is_end else start_date

    print(
        f"{picked['Period']} ({picked_date:%Y-%m-%d}): "
        f"{master_timeseries} {master_return:.6f}, "
        f"{comparison_timeseries} {float(picked[comparison_column]):.6f}"
    )
    print(f"Return from {start_date:%Y-%m-%d} to {picked_date:%Y-%m-%d}")
    if best_gap <= match_tolerance and best_date == recorded_date:
        print(
            f"The {master_timeseries} return already matches Yahoo on the resolved "
            f"observation date within {match_tolerance:.4f} (already resolved). "
            "Any remaining gap is not a nearby date mismatch."
        )
    elif best_gap <= match_tolerance and best_date != recorded_date:
        print(
            f"Using {best_date:%Y-%m-%d} as the {best_role} reproduces the "
            f"{master_timeseries} return (gap {best_gap:.6f}). "
            "The difference comes from a date mismatch."
        )
    else:
        print(
            f"No session within {nearby_sessions} trading days reproduces the "
            f"{master_timeseries} return within {match_tolerance:.4f}. "
            f"Closest is {best_date:%Y-%m-%d} as the {best_role} "
            f"(gap {best_gap:.6f}). "
            "The difference does not come from a nearby date mismatch."
        )

    return pd.concat(
        {"start date": start_check, "observation date": end_check},
        names=["varied", "Date"],
    )
