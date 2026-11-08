"""Resolve Lipper observation dates per fund-month from Yahoo total-return levels."""

from __future__ import annotations

import pandas as pd

INDEX_DATE_COLUMN = "Index Date"
DATE_SHIFT_COLUMN = "Date shift (sessions)"


def _session_loc(sessions: pd.DatetimeIndex, date: pd.Timestamp) -> int | None:
    ts = pd.Timestamp(date)
    if ts in sessions:
        loc = sessions.get_loc(ts)
        return int(loc) if isinstance(loc, int) else None
    pos = sessions.searchsorted(ts)
    if pos >= len(sessions):
        pos = len(sessions) - 1
    return int(pos)


def _session_shift(
    index_date: pd.Timestamp,
    resolved_date: pd.Timestamp,
    sessions: pd.DatetimeIndex,
) -> int:
    i0 = _session_loc(sessions, index_date)
    i1 = _session_loc(sessions, resolved_date)
    if i0 is None or i1 is None:
        return 0
    return i1 - i0


def _candidate_end_dates(
    recorded: pd.Timestamp,
    sessions: pd.DatetimeIndex,
    max_shift_sessions: int,
) -> list[pd.Timestamp]:
    recorded = pd.Timestamp(recorded)
    loc = _session_loc(sessions, recorded)
    if loc is None:
        return [recorded]
    start_i = max(0, loc - max_shift_sessions)
    end_i = min(len(sessions) - 1, loc + max_shift_sessions)
    candidates = {pd.Timestamp(d) for d in sessions[start_i : end_i + 1]}
    candidates.add(recorded)
    return sorted(candidates, key=pd.Timestamp)


def _yahoo_window_return(
    start: pd.Timestamp,
    end: pd.Timestamp,
    yahoo_level: pd.Series,
) -> float:
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if start not in yahoo_level.index or end not in yahoo_level.index:
        return float("nan")
    return float(yahoo_level.loc[end] / yahoo_level.loc[start] - 1)


def shifted_months_summary(frame: pd.DataFrame) -> dict:
    """Count and list rows where observation dates were shifted from the index."""
    if DATE_SHIFT_COLUMN not in frame.columns:
        return {"count": 0, "months": []}
    shifted = frame.loc[frame[DATE_SHIFT_COLUMN].fillna(0).astype(int) != 0]
    months: list[dict] = []
    for _, row in shifted.iterrows():
        months.append(
            {
                "period": str(row["Period"]),
                "index_date": pd.Timestamp(row[INDEX_DATE_COLUMN]).strftime("%Y-%m-%d"),
                "resolved_date": pd.Timestamp(row["Date"]).strftime("%Y-%m-%d"),
                "shift_sessions": int(row[DATE_SHIFT_COLUMN]),
            }
        )
    return {"count": len(months), "months": months}


def resolve_fund_observation_dates(
    fund_timeseries: pd.DataFrame,
    lipper_column: str,
    yahoo_level: pd.Series,
    *,
    match_tolerance: float = 1e-4,
    max_shift_sessions: int = 6,
) -> pd.DataFrame:
    """Align each row's ``Date`` to the window Lipper used for that fund-month."""
    frame = fund_timeseries.copy()
    sessions = pd.DatetimeIndex(yahoo_level.index.sort_values())
    frame[INDEX_DATE_COLUMN] = pd.to_datetime(frame["Date"])
    resolved_dates: list[pd.Timestamp] = []

    for i in range(len(frame)):
        index_date = pd.Timestamp(frame.iloc[i][INDEX_DATE_COLUMN])
        if i == 0:
            resolved_dates.append(index_date)
            continue

        lipper_return = frame.iloc[i][lipper_column]
        start = resolved_dates[i - 1]
        if pd.isna(lipper_return):
            resolved_dates.append(index_date)
            continue

        lipper_return = float(lipper_return)
        recorded_return = _yahoo_window_return(start, index_date, yahoo_level)
        if (
            pd.notna(recorded_return)
            and abs(recorded_return - lipper_return) <= match_tolerance
        ):
            resolved_dates.append(index_date)
            continue

        best_date = index_date
        best_gap = abs(recorded_return - lipper_return) if pd.notna(recorded_return) else float("inf")
        for candidate in _candidate_end_dates(index_date, sessions, max_shift_sessions):
            if pd.Timestamp(candidate) <= pd.Timestamp(start):
                continue
            yahoo_return = _yahoo_window_return(start, candidate, yahoo_level)
            if pd.isna(yahoo_return):
                continue
            gap = abs(yahoo_return - lipper_return)
            if gap < best_gap:
                best_gap = gap
                best_date = pd.Timestamp(candidate)

        if best_gap <= match_tolerance and best_date != index_date:
            resolved_dates.append(best_date)
        elif (
            pd.notna(recorded_return)
            and abs(recorded_return - lipper_return) <= match_tolerance
        ):
            resolved_dates.append(index_date)
        else:
            resolved_dates.append(index_date)

    frame["Date"] = pd.to_datetime(resolved_dates)
    shifts = [
        _session_shift(
            frame.iloc[i][INDEX_DATE_COLUMN],
            frame.iloc[i]["Date"],
            sessions,
        )
        for i in range(len(frame))
    ]
    frame[DATE_SHIFT_COLUMN] = shifts

    summary = shifted_months_summary(frame)
    if summary["count"]:
        parts = [
            f"{m['period']} → {m['resolved_date']} ({m['shift_sessions']:+d})"
            for m in summary["months"]
        ]
        print(
            f"Resolved observation dates: {summary['count']} month(s) shifted — "
            + ", ".join(parts)
        )
    else:
        print("Resolved observation dates: no shifts (index dates match Lipper returns)")

    return frame
