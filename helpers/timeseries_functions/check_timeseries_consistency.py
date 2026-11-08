from dataclasses import dataclass

import pandas as pd

DEFAULT_SPIKE_RETURN = 0.10
DEFAULT_REVERSAL_BAND = 0.15
DEFAULT_SCALE_FACTOR = 5
DEFAULT_SCALE_WINDOW = 12
DEFAULT_LEVEL_JUMP = 0.50
DEFAULT_INDEX_GAP = 0.05
DEFAULT_DATE_GAP_DAYS = 45
DEFAULT_MASTER_TIMESERIES = "Lipper"
DEFAULT_COMPARISON_TIMESERIES = "Yahoo"


@dataclass
class SeriesCheck:
    """One source, with a row per month and the flags the report prints."""

    label: str
    column: str
    months: pd.DataFrame
    scale_at: int | None
    index_gap: float


def locate_series_issues(
    label: str,
    column: str,
    *,
    fund_timeseries: pd.DataFrame,
    index_column: str,
    spike_return: float,
    reversal_band: float,
    scale_factor: float,
    scale_window: int,
    level_jump: float,
    index_gap: float,
    date_gap_days: int,
) -> SeriesCheck:
    """Flag gaps, spikes, scale changes, and index gaps for one series."""
    frame = fund_timeseries[["Period", "Date", column, index_column]].reset_index(
        drop=True
    )
    returns = frame[column]
    market = frame[index_column]
    usable = returns.notna() & market.notna()

    parsed = pd.to_datetime(frame["Period"], format="%b %Y")
    ordinal = parsed.dt.year * 12 + parsed.dt.month
    missing = returns.isna().copy()
    missing.iloc[0] = False
    skipped = ordinal.diff().gt(1).fillna(False)
    long_gap = frame["Date"].diff().dt.days.gt(date_gap_days).fillna(False)
    gap_rows = missing | skipped | long_gap

    scale_at = None
    sharpest = 0.0
    absolute = returns.abs()
    last_split = len(frame) - scale_window
    for end in range(scale_window, last_split + 1):
        before = absolute.iloc[end - scale_window : end].median()
        after = absolute.iloc[end : end + scale_window].median()
        prefix = absolute.iloc[:end].median()
        suffix = absolute.iloc[end:].median()
        bounds = (before, after, prefix, suffix)
        if any(pd.isna(bound) or bound <= 0 for bound in bounds):
            continue
        local = after / before
        ratio = suffix / prefix
        stays_up = local >= scale_factor and ratio >= scale_factor
        stays_down = local <= 1 / scale_factor and ratio <= 1 / scale_factor
        if not stays_up and not stays_down:
            continue
        strength = max(local, 1 / local)
        if strength > sharpest:
            sharpest = float(strength)
            scale_at = end

    jumps = []
    for i in range(len(returns)):
        value = returns.iloc[i]
        index_value = market.iloc[i]
        if pd.isna(value) or pd.isna(index_value):
            continue
        if abs(value) < level_jump or abs(value - index_value) < level_jump / 2:
            continue
        if scale_at is not None and i >= scale_at:
            continue
        follow = returns.iloc[i : i + 4].dropna()
        if len(follow) < 2:
            continue
        stayed = float((1 + follow).prod() - 1)
        if abs(stayed) >= abs(float(value)) / 2:
            jumps.append(i)

    undone = (1 + returns) * (1 + returns.shift(-1)) - 1
    gave_back = (
        returns.shift(-1).notna()
        & returns.abs().ge(spike_return)
        & (returns * returns.shift(-1) < 0)
        & undone.abs().le(reversal_band)
    ).fillna(False)
    market_undone = (1 + market) * (1 + market.shift(-1)) - 1
    market_gave_back = (
        market.shift(-1).notna()
        & market.abs().ge(spike_return / 2)
        & (market * market.shift(-1) < 0)
        & market_undone.abs().le(reversal_band)
    ).fillna(False)
    reversal = (usable & gave_back & ~market_gave_back).fillna(False)
    distance = (returns - market).abs()
    isolated = (
        usable & returns.abs().ge(spike_return) & distance.ge(returns.abs() / 2)
    ).fillna(False)
    on_new_scale = pd.Series(False, index=frame.index)
    if scale_at is not None:
        on_new_scale.iloc[scale_at:] = True
    level_shift = pd.Series(False, index=frame.index)
    if jumps:
        level_shift.iloc[jumps] = True
    spike = (
        (reversal | isolated)
        & ~on_new_scale
        & ~level_shift
        & ~reversal.shift(1, fill_value=False)
    )
    spike = spike.fillna(False)
    wide = (usable & distance.ge(index_gap)).fillna(False)

    months = frame[["Period", "Date"]].copy()
    months["return"] = returns.to_numpy()
    months["index_return"] = market.to_numpy()
    months["missing"] = missing.to_numpy(dtype=bool)
    months["skipped"] = skipped.to_numpy(dtype=bool)
    months["long_gap"] = long_gap.to_numpy(dtype=bool)
    months["gap"] = gap_rows.to_numpy(dtype=bool)
    months["reversal"] = reversal.to_numpy(dtype=bool)
    months["spike"] = spike.to_numpy(dtype=bool)
    months["level_jump"] = level_shift.to_numpy(dtype=bool)
    months["on_new_scale"] = on_new_scale.to_numpy(dtype=bool)
    months["wide"] = wide.to_numpy(dtype=bool)
    months["usable"] = usable.to_numpy(dtype=bool)
    return SeriesCheck(
        label=label,
        column=column,
        months=months,
        scale_at=scale_at,
        index_gap=index_gap,
    )


def locate_timeseries_issues(
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    comparison_column: str,
    *,
    master_timeseries: str = DEFAULT_MASTER_TIMESERIES,
    comparison_timeseries: str = DEFAULT_COMPARISON_TIMESERIES,
    spike_return: float = DEFAULT_SPIKE_RETURN,
    reversal_band: float = DEFAULT_REVERSAL_BAND,
    scale_factor: float = DEFAULT_SCALE_FACTOR,
    scale_window: int = DEFAULT_SCALE_WINDOW,
    level_jump: float = DEFAULT_LEVEL_JUMP,
    index_gap: float = DEFAULT_INDEX_GAP,
    date_gap_days: int = DEFAULT_DATE_GAP_DAYS,
) -> list[SeriesCheck]:
    """Flag both series the same way the consistency report does, without printing."""
    kwargs = {
        "fund_timeseries": fund_timeseries,
        "index_column": index_column,
        "spike_return": spike_return,
        "reversal_band": reversal_band,
        "scale_factor": scale_factor,
        "scale_window": scale_window,
        "level_jump": level_jump,
        "index_gap": index_gap,
        "date_gap_days": date_gap_days,
    }
    return [
        locate_series_issues(label, column, **kwargs)
        for label, column in (
            (master_timeseries, master_column),
            (comparison_timeseries, comparison_column),
        )
    ]


def _print_series_check(check: SeriesCheck) -> None:
    """Print gaps, spikes, lasting scale changes, and index gaps for one series."""
    frame = check.months
    returns = frame["return"]
    market = frame["index_return"]
    usable = frame["usable"]
    missing = frame["missing"]
    skipped = frame["skipped"]
    long_gap = frame["long_gap"]
    gap_rows = frame["gap"]
    scale_at = check.scale_at
    reversal = frame["reversal"]
    spike = frame["spike"]
    wide = frame["wide"]
    on_new_scale = frame["on_new_scale"]
    index_gap = check.index_gap
    jumps = list(frame.index[frame["level_jump"]])

    def when(i):
        return f"{frame.at[i, 'Date']:%Y-%m-%d}  {frame.at[i, 'Period']}"

    print(check.label)

    if not gap_rows.any():
        print("    Gaps: none")
    else:
        print(f"    Gaps: {int(gap_rows.sum())}")
        for i in frame.index[gap_rows]:
            reasons = []
            if missing.iloc[i]:
                reasons.append("missing return")
            if skipped.iloc[i]:
                reasons.append("skipped month")
            if long_gap.iloc[i]:
                reasons.append(
                    f"{int(frame['Date'].diff().dt.days.iloc[i])} days since the previous date"
                )
            print(f"        {when(i)}  {', '.join(reasons)}")

    if not spike.any():
        print("    Abnormal spikes: none")
    else:
        spike_rows = list(frame.index[spike])
        print(f"    Abnormal spikes: {len(spike_rows)}")
        for i in spike_rows[:12]:
            if reversal.iloc[i]:
                note = "reverses the next month, the index does not"
            else:
                note = "the index does not follow"
            print(
                f"        {when(i)}  {returns.at[i]:+.2%}  "
                f"S&P 500 TR {market.at[i]:+.2%}  {note}"
            )
        if len(spike_rows) > 12:
            print(f"        ... and {len(spike_rows) - 12} more")

    if scale_at is None and not jumps:
        print("    Scale shifts: none")
    else:
        print("    Scale shifts:")
        if scale_at is not None:
            absolute = returns.abs()
            before = absolute.iloc[:scale_at].median()
            after = absolute.iloc[scale_at:].median()
            print(
                f"        {when(scale_at)}  median |return| goes from "
                f"{before:.2%} to {after:.2%} and stays there"
            )
        for i in jumps:
            print(
                f"        {when(i)}  {returns.at[i]:+.2%}  "
                "level does not come back over the next months"
            )

    outside_scale = wide if scale_at is None else wide & ~on_new_scale
    inside_scale = (
        pd.Series(False, index=frame.index) if scale_at is None else wide & on_new_scale
    )
    if not outside_scale.any() and not inside_scale.any():
        print(f"    Differences with S&P 500 TR above {index_gap:.0%}: none")
    else:
        count = int(outside_scale.sum() + inside_scale.sum())
        print(f"    Differences with S&P 500 TR above {index_gap:.0%}: {count}")
        shown = list(frame.index[outside_scale])[:12]
        for i in shown:
            print(
                f"        {when(i)}  {(returns.at[i] - market.at[i]) * 1e4:+.1f} bp  "
                f"fund {returns.at[i]:+.2%}  index {market.at[i]:+.2%}"
            )
        hidden = int(outside_scale.sum()) - len(shown)
        if hidden:
            print(f"        ... and {hidden} more")
        if inside_scale.any():
            print(
                f"        {when(scale_at)} onward, {int(inside_scale.sum())} months "
                "differ from the index by that much because the scale has changed"
            )

    if usable.any():
        move = returns.abs().where(usable).idxmax()
        distance = (returns - market).abs()
        gap_i = distance.where(usable).idxmax()
        print(
            f"    Largest move: {when(move)}  {returns.at[move]:+.2%}  "
            f"S&P 500 TR {market.at[move]:+.2%}"
        )
        print(
            f"    Largest gap versus S&P 500 TR: {when(gap_i)}  "
            f"{(returns.at[gap_i] - market.at[gap_i]) * 1e4:+.1f} bp  "
            f"fund {returns.at[gap_i]:+.2%}  index {market.at[gap_i]:+.2%}"
        )
    print()


def check_timeseries_consistency(
    fund_timeseries: pd.DataFrame,
    index_column: str,
    master_column: str,
    comparison_column: str,
    *,
    master_timeseries: str = DEFAULT_MASTER_TIMESERIES,
    comparison_timeseries: str = DEFAULT_COMPARISON_TIMESERIES,
    spike_return: float = DEFAULT_SPIKE_RETURN,
    reversal_band: float = DEFAULT_REVERSAL_BAND,
    scale_factor: float = DEFAULT_SCALE_FACTOR,
    scale_window: int = DEFAULT_SCALE_WINDOW,
    level_jump: float = DEFAULT_LEVEL_JUMP,
    index_gap: float = DEFAULT_INDEX_GAP,
    date_gap_days: int = DEFAULT_DATE_GAP_DAYS,
) -> list[SeriesCheck]:
    """Check gaps, spikes, scale changes, and index divergence for two series."""
    checks = locate_timeseries_issues(
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
    for check in checks:
        _print_series_check(check)
    return checks
