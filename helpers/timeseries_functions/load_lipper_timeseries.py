from pathlib import Path

import pandas as pd

META_LABELS = {"name", "category", "fee (%/year)", "Note", "Date"}


def find_sp_cache(cache_relative: Path) -> Path:
    """Find the S&P 500 TR cache whether the kernel cwd is code/ or notebooks/."""
    start = Path.cwd().resolve()
    for directory in [start, *start.parents]:
        candidate = directory / cache_relative
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        f"Could not find {cache_relative}, starting from {start}"
    )


def load_lipper_timeseries(
    timeseries_df: pd.DataFrame,
    funds: pd.DataFrame,
    selected_fund: str,
    cache_relative: Path,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load one fund's Lipper monthly total return on the S&P observation dates."""
    selected = funds.loc[funds["ISIN"].eq(selected_fund)]
    if selected.empty:
        raise KeyError(f"{selected_fund} is not a fund column of the Timeseries sheet")
    selected = selected.iloc[0]
    lipper_column = f"{selected_fund} (Lipper)"

    # Same layout as sp500_indices: Period, the exact Lipper observation Date,
    # Time, then the series. Fund columns in this sheet are monthly total returns.
    fund_timeseries = (
        timeseries_df.loc[~timeseries_df["id"].isin(META_LABELS), ["id", selected_fund]]
        .rename(columns={"id": "month_start", selected_fund: lipper_column})
        .assign(month_start=lambda frame: pd.to_datetime(frame["month_start"]))
    )
    fund_timeseries[lipper_column] = pd.to_numeric(
        fund_timeseries[lipper_column], errors="coerce"
    )
    fund_timeseries["Period"] = fund_timeseries["month_start"].dt.strftime("%b %Y")

    # Every series on this sheet shares the observation dates already resolved
    # for the S&P 500 TR frame (1st of the month, or the nearby session Lipper used).
    observation = pd.read_json(find_sp_cache(cache_relative))[["Period", "Date", "Time"]]
    observation["Date"] = pd.to_datetime(observation["Date"])
    fund_timeseries = fund_timeseries.merge(observation, on="Period", how="left")
    missing_dates = fund_timeseries.loc[fund_timeseries["Date"].isna(), "Period"]
    if not missing_dates.empty:
        raise ValueError(
            f"No S&P observation date for: {missing_dates.tolist()}"
        )

    fund_timeseries = fund_timeseries[
        ["Period", "Date", "Time", lipper_column]
    ].reset_index(drop=True)

    print(f"Loaded fund time series (Lipper) for: {selected['Name']} ({selected_fund} ")

    return fund_timeseries, selected
