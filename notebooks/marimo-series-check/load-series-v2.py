# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "altair>=6.3.0",
#     "marimo>=0.25.2",
#     "openpyxl>=3.1.5",
#     "pandas>=3.0.6",
#     "statsmodels>=0.15.0",
# ]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Load daily series (V2)")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Load the daily series (V2)

    Load `output-data/v2-d-timeseries-final.xlsx`. The sheet keeps six label rows, then one row per date.

    The first column is the date. Each other column is one series: an index, the risk-free rate, or a fund total return, price, or net assets.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 1. Load the workbook

    Read the sheet with no header. Rows 1–6 stay labels (`id`, `name`, `category`, `fee (%/year)`, `Note`, and the short header). The observations start on the next row.
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import pandas as pd

    label_rows = 6
    filename = "v2-d-timeseries-final.xlsx"

    def find_series_workbook() -> Path:
        relative = Path("output-data") / filename
        start = Path.cwd().resolve()
        for directory in [start, *start.parents]:
            candidate = directory / relative
            if candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError(f"Could not find {relative}, starting from {start}")

    workbook = find_series_workbook()
    raw = pd.read_excel(workbook, header=None, engine="openpyxl")
    if len(raw) <= label_rows or raw.shape[1] < 2:
        raise ValueError("The daily series sheet has no observations")
    return label_rows, pd, raw, workbook


@app.cell
def _(label_rows, pd, raw):
    labels = raw.iloc[:label_rows, 1:]
    catalog = pd.DataFrame(
        {
            "column": labels.columns.astype(int),
            "id": labels.iloc[0].astype("string").str.strip().to_numpy(),
            "name": labels.iloc[1].astype("string").str.strip().to_numpy(),
            "category": labels.iloc[2].astype("string").str.strip().to_numpy(),
            "fee": pd.to_numeric(labels.iloc[3], errors="coerce").to_numpy(),
            "note": labels.iloc[4].astype("string").str.strip().to_numpy(),
            "header": labels.iloc[5].astype("string").str.strip().to_numpy(),
        }
    ).reset_index(drop=True)

    dates = pd.to_datetime(raw.iloc[label_rows:, 0], errors="coerce")
    observations = raw.iloc[label_rows:, 1:].apply(pd.to_numeric, errors="coerce")
    observations.index = pd.Index(dates, name="date")
    observations.columns = catalog["column"].to_numpy()

    valid = observations.notna().to_numpy()
    has_value = valid.any(axis=0)
    first_idx = valid.argmax(axis=0)
    last_idx = valid.shape[0] - 1 - valid[::-1].argmax(axis=0)
    date_values = observations.index.to_numpy()
    first_date = pd.Series(pd.NaT, index=observations.columns, dtype="datetime64[ns]")
    last_date = pd.Series(pd.NaT, index=observations.columns, dtype="datetime64[ns]")
    first_date.iloc[has_value] = date_values[first_idx[has_value]]
    last_date.iloc[has_value] = date_values[last_idx[has_value]]
    catalog = catalog.assign(
        observations=valid.sum(axis=0),
        first_date=first_date.to_numpy(),
        last_date=last_date.to_numpy(),
    )
    return catalog, observations


@app.cell
def _(catalog, mo, observations, pd, workbook):
    parsed_dates = observations.index.dropna()
    missing_dates = int(observations.index.isna().sum())
    category_counts = (
        catalog.groupby("category", dropna=False)
        .agg(columns=("column", "size"), ids=("id", "nunique"))
        .reset_index()
        .sort_values(["columns", "category"], ascending=[False, True])
    )
    summary = mo.md(
        f"- **File:** `{workbook}` \n"
        f"- **{len(observations):,}** dates, from **{parsed_dates.min():%Y-%m-%d}** to **{parsed_dates.max():%Y-%m-%d}** \n"
        f"- **{missing_dates:,}** rows have no date \n"
        f"- **{len(catalog):,}** series columns, **{catalog['id'].nunique():,}** ids \n"
    )
    counts = mo.ui.table(
        category_counts,
        label="Columns by category",
        selection=None,
        pagination=False,
    )
    mo.vstack([summary, counts])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 2. Series catalog

    One row per column. `observations` counts the dates with a value. Filter the table, then pick the same series below to plot it.
    """)
    return


@app.cell
def _(catalog, mo):
    catalog_table = mo.ui.table(
        catalog,
        label="Daily series",
        selection=None,
        pagination=len(catalog) > 12,
        page_size=12,
        max_height=420,
    )
    catalog_table
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 3. Plot one series
    """)
    return


@app.cell
def _(catalog, mo):
    options = {
        f"{int(row.column):>4}  {row.header}  [{row.category}]": int(row.column)
        for row in catalog.itertuples(index=False)
    }
    series_picker = mo.ui.dropdown(
        options,
        value=next(iter(options)),
        label="Series",
        full_width=True,
    )
    series_picker
    return (series_picker,)


@app.cell
def _(catalog, mo, observations, pd, series_picker):
    import altair as alt

    column = int(series_picker.value)
    chosen = catalog.loc[catalog["column"] == column].iloc[0]
    series = observations[column].dropna().rename("value").reset_index()
    fee = f", fee {chosen.fee:g}%/year" if pd.notna(chosen.fee) else ""
    span = (
        f", from **{series['date'].min():%Y-%m-%d}** to **{series['date'].max():%Y-%m-%d}**"
        if len(series)
        else ""
    )
    detail = mo.md(
        f"- **{chosen.header}** \n"
        f"- **{chosen.id}** — {chosen.name} \n"
        f"- {chosen.category}{fee} \n"
        f"- {chosen.note} \n"
        f"- **{len(series):,}** observations{span} \n"
    )
    chart = (
        alt.Chart(series)
        .mark_line()
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("value:Q", title=str(chosen.header)),
            tooltip=[
                alt.Tooltip("date:T", title="Date"),
                alt.Tooltip("value:Q", title="Value", format=",.6g"),
            ],
        )
        .properties(height=320)
        if len(series)
        else mo.md("This series has no observations.")
    )
    mo.vstack([detail, chart])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 4. Check each total-return series

    Same controls as `old/check-fund-timeseries.ipynb`, applied to each daily **price total return** (`TR %`) rather than to a monthly return or to the price-only return. Each series is judged on its own against the daily **S&P 500 TR** return.

    A gap is a missing daily return inside the series, a skipped month, or more than 45 days between dates. A spike is a daily return of at least 10% that reverses the next day while the index does not, or that the index does not follow. A scale shift is a median absolute return that stays at least 5× higher or lower across 12 daily returns. A level jump is a move of at least 50% that does not come back. A day is far from the index when the absolute gap is at least 5%.
    """)
    return


@app.cell
def _(catalog, observations, pd):
    import pathlib
    import sys

    start = pathlib.Path.cwd().resolve()
    for directory in [start, *start.parents]:
        if (directory / "helpers").is_dir():
            root = str(directory)
            if root not in sys.path:
                sys.path.insert(0, root)
            break
    else:
        raise FileNotFoundError(f"Could not find helpers/, starting from {start}")

    from helpers.timeseries_functions.check_timeseries_consistency import (
        DEFAULT_DATE_GAP_DAYS,
        DEFAULT_INDEX_GAP,
        DEFAULT_LEVEL_JUMP,
        DEFAULT_REVERSAL_BAND,
        DEFAULT_SCALE_FACTOR,
        DEFAULT_SCALE_WINDOW,
        DEFAULT_SPIKE_RETURN,
        locate_series_issues,
    )

    def daily_frame(column_id, index_id):
        series = observations[column_id].dropna()
        if len(series) < 2:
            return None
        window = observations.loc[series.index[0] : series.index[-1]]
        dates = pd.to_datetime(window.index)
        fund = window[column_id]
        market = window[index_id]
        if isinstance(fund, pd.DataFrame):
            fund = fund.iloc[:, 0]
        if isinstance(market, pd.DataFrame):
            market = market.iloc[:, 0]
        return pd.DataFrame(
            {
                "Period": dates.strftime("%b %Y"),
                "Date": dates,
                "fund": fund.to_numpy(),
                "S&P 500 TR": market.to_numpy(),
            }
        )

    is_return = catalog["note"].astype("string").str.startswith("Daily simple return")
    levels = catalog.loc[~is_return].copy()
    level_by_header = {str(row.header): row for row in levels.itertuples(index=False)}
    index_return = catalog.loc[
        is_return & catalog["header"].eq("S&P 500 TR %")
    ].iloc[0]
    index_id = int(index_return.column)

    checks = {}
    rows = []
    controls = {
        "spike_return": DEFAULT_SPIKE_RETURN,
        "reversal_band": DEFAULT_REVERSAL_BAND,
        "scale_factor": DEFAULT_SCALE_FACTOR,
        "scale_window": DEFAULT_SCALE_WINDOW,
        "level_jump": DEFAULT_LEVEL_JUMP,
        "index_gap": DEFAULT_INDEX_GAP,
        "date_gap_days": DEFAULT_DATE_GAP_DAYS,
    }
    for return_row in catalog.loc[is_return].itertuples(index=False):
        if int(return_row.column) == index_id:
            continue
        level = level_by_header.get(str(return_row.header).removesuffix(" %"))
        if level is None or not str(level.note).startswith("Total return index"):
            continue
        series_days = daily_frame(int(return_row.column), index_id)
        record = {
            "column": int(return_row.column),
            "id": return_row.id,
            "header": return_row.header,
            "category": return_row.category,
            "kind": None if level is None else level.note,
            "days": 0,
            "gaps": 0,
            "spikes": 0,
            "level_jumps": 0,
            "scale_shift": False,
            "far_from_index": 0,
        }
        if series_days is not None:
            series_check = locate_series_issues(
                str(return_row.header),
                "fund",
                fund_timeseries=series_days,
                index_column="S&P 500 TR",
                **controls,
            )
            checks[int(return_row.column)] = series_check
            checked_months = series_check.months
            record["days"] = int(checked_months["return"].notna().sum())
            record["gaps"] = int(checked_months["gap"].sum())
            record["spikes"] = int(checked_months["spike"].sum())
            record["level_jumps"] = int(checked_months["level_jump"].sum())
            record["scale_shift"] = series_check.scale_at is not None
            record["far_from_index"] = int(checked_months["wide"].sum())
        rows.append(record)

    issue_summary = pd.DataFrame(rows)
    issue_summary["issues"] = (
        issue_summary["gaps"]
        + issue_summary["spikes"]
        + issue_summary["level_jumps"]
        + issue_summary["scale_shift"].astype(int)
        + issue_summary["far_from_index"]
    )
    issue_summary = issue_summary.sort_values(
        ["issues", "header"], ascending=[False, True]
    ).reset_index(drop=True)
    return checks, controls, issue_summary


@app.cell
def _(controls, issue_summary, mo):
    flagged_series = int((issue_summary["issues"] > 0).sum())
    check_summary = mo.md(
        f"- **{len(issue_summary):,}** price total-return series checked against S&P 500 TR \n"
        f"- **{flagged_series:,}** series have at least one gap, spike, scale shift, level jump, or day far from the index \n"
        f"- Spike **{controls['spike_return']:.0%}**, reversal band **{controls['reversal_band']:.0%}**, "
        f"scale factor **{controls['scale_factor']:g}** over **{controls['scale_window']}** daily returns, "
        f"level jump **{controls['level_jump']:.0%}**, index gap **{controls['index_gap']:.0%}**, "
        f"date gap **{controls['date_gap_days']}** days \n"
    )
    table = mo.ui.table(
        issue_summary,
        label="Total-return series checks",
        selection=None,
        pagination=len(issue_summary) > 12,
        page_size=12,
        max_height=420,
    )
    mo.vstack([check_summary, table])
    return


@app.cell
def _(catalog, checks, issue_summary, mo, series_picker):
    import importlib

    from helpers.timeseries_functions import plot_timeseries_issues as plot_module

    importlib.reload(plot_module)
    plot_timeseries_issues = plot_module.plot_timeseries_issues

    picked_column = int(series_picker.value)
    picked = catalog.loc[catalog["column"] == picked_column].iloc[0]
    tr_rows = catalog.loc[
        catalog["id"].eq(picked.id)
        & catalog["note"].astype("string").str.startswith("Daily simple return")
        & catalog["header"].astype("string").str.endswith("TR %")
        & catalog["column"].isin(checks)
    ]
    if tr_rows.empty:
        checked_column = None
        checked_note = f"**{picked.header}** has no checked price total-return series."
    else:
        checked_column = int(tr_rows.iloc[0]["column"])
        checked_header = str(tr_rows.iloc[0]["header"])
        checked_note = (
            f"**{picked.header}** is the total-return series in the plot above."
            if checked_column == picked_column
            else f"**{picked.header}** is not the series being checked. Issues are read from its price total return, **{checked_header}**."
        )

    selected_check = checks.get(checked_column)
    if selected_check is None:
        report = mo.md(checked_note)
    else:
        months = selected_check.months
        usable = months.loc[months["usable"]]
        lines = [checked_note, ""]
        if len(usable):
            move = usable["return"].abs().idxmax()
            distance = (usable["return"] - usable["index_return"]).abs()
            gap_i = distance.idxmax()
            lines.append(
                f"- Largest move: **{months.at[move, 'Period']}**  {months.at[move, 'return']:+.2%}  "
                f"S&P 500 TR {months.at[move, 'index_return']:+.2%}"
            )
            lines.append(
                f"- Largest gap versus S&P 500 TR: **{months.at[gap_i, 'Period']}**  "
                f"{(months.at[gap_i, 'return'] - months.at[gap_i, 'index_return']) * 1e4:+.1f} bp  "
                f"fund {months.at[gap_i, 'return']:+.2%}  index {months.at[gap_i, 'index_return']:+.2%}"
            )
        issue_counts = issue_summary.loc[issue_summary["column"] == checked_column].iloc[0]
        lines.append(
            f"- **{int(issue_counts.gaps)}** gaps, **{int(issue_counts.spikes)}** abnormal spikes, "
            f"**{int(issue_counts.level_jumps)}** level jumps, "
            f"**{'a scale shift' if issue_counts.scale_shift else 'no scale shift'}**, "
            f"**{int(issue_counts.far_from_index)}** days far from the S&P 500 TR"
        )
        flagged_months = months.loc[
            months["gap"] | months["spike"] | months["level_jump"] | months["wide"]
        ].copy()
        flagged_months["flags"] = ""
        flagged_months.loc[flagged_months["gap"], "flags"] = (
            flagged_months.loc[flagged_months["gap"], "flags"] + "gap"
        )
        flagged_months.loc[flagged_months["spike"], "flags"] = flagged_months.loc[
            flagged_months["spike"], "flags"
        ].apply(lambda text: f"{text}, spike" if text else "spike")
        flagged_months.loc[flagged_months["level_jump"], "flags"] = flagged_months.loc[
            flagged_months["level_jump"], "flags"
        ].apply(lambda text: f"{text}, level jump" if text else "level jump")
        flagged_months.loc[flagged_months["wide"], "flags"] = flagged_months.loc[
            flagged_months["wide"], "flags"
        ].apply(lambda text: f"{text}, far from index" if text else "far from index")
        view = flagged_months.loc[:, ["Date", "Period", "return", "index_return", "flags"]].rename(
            columns={"return": "fund", "index_return": "S&P 500 TR"}
        )
        report = mo.vstack(
            [
                mo.md("\n".join(lines)),
                mo.ui.table(
                    view,
                    label="Flagged days",
                    selection=None,
                    pagination=len(view) > 12,
                    page_size=12,
                    max_height=420,
                )
                if len(view)
                else mo.md("No flagged days."),
                plot_timeseries_issues(
                    [selected_check],
                    "S&P 500 TR",
                    period_name="day",
                    return_title="Daily return",
                ),
            ]
        )
    report
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 5. Carry prices across market holidays

    A holiday is a date where the **S&P 500 TR** level equals the previous close. On those dates each price and total-return series should stay at its previous close, and its daily return should be 0. A series that prints another value is rewritten: the holiday level is carried forward, the holiday return is set to 0, and the next session's return is recomputed from the corrected level.
    """)
    return


@app.cell
def _(catalog, mo, observations, pd):
    def values_match(left, right, tolerance):
        left_missing = left != left
        right_missing = right != right
        if left_missing and right_missing:
            return True
        if left_missing or right_missing:
            return False
        return abs(left - right) <= tolerance

    level_tolerance = 1e-6
    return_tolerance = 1e-10
    market = catalog.loc[
        catalog["header"].eq("S&P 500 TR")
        & catalog["note"].astype("string").str.startswith("Total return index")
    ].iloc[0]
    market_level = observations[int(market.column)]
    previous_close = market_level.shift(1)
    holiday_dates = market_level.index[
        market_level.notna()
        & previous_close.notna()
        & (market_level - previous_close).abs().le(level_tolerance)
    ]
    holiday_positions = observations.index.get_indexer(holiday_dates)

    return_ids = {
        row.header: int(row.column)
        for row in catalog.loc[
            catalog["note"].astype("string").str.startswith("Daily simple return")
        ].itertuples(index=False)
    }
    level_notes = ("Price, daily", "Total return index, daily", "Price index, daily")
    corrected_observations = observations.copy()
    correction_rows = []
    for level_row in catalog.loc[catalog["note"].astype("string").isin(level_notes)].itertuples(
        index=False
    ):
        return_id = return_ids.get(f"{level_row.header} %")
        if return_id is None:
            continue
        level_id = int(level_row.column)
        level_values = corrected_observations[level_id].to_numpy(dtype="float64", copy=True)
        return_values = corrected_observations[return_id].to_numpy(dtype="float64", copy=True)
        original_level = level_values.copy()
        original_return = return_values.copy()
        holidays_fixed = 0
        for position in holiday_positions:
            if position <= 0:
                continue
            previous = level_values[position - 1]
            current = level_values[position]
            if previous != previous or current != current:
                continue
            holiday_return = return_values[position]
            price_moved = not values_match(current, previous, level_tolerance)
            return_moved = not values_match(holiday_return, 0.0, return_tolerance)
            if not price_moved and not return_moved:
                continue
            level_values[position] = previous
            return_values[position] = 0.0
            holidays_fixed += 1
            following = position + 1
            if (
                price_moved
                and following < len(level_values)
                and level_values[following] == level_values[following]
                and previous != 0
            ):
                return_values[following] = level_values[following] / previous - 1.0
        if holidays_fixed == 0:
            continue
        corrected_observations[level_id] = level_values
        corrected_observations[return_id] = return_values
        cells_changed = 0
        for before, after in zip(original_level, level_values, strict=True):
            if not values_match(before, after, level_tolerance):
                cells_changed += 1
        for before, after in zip(original_return, return_values, strict=True):
            if not values_match(before, after, return_tolerance):
                cells_changed += 1
        correction_rows.append(
            {
                "id": level_row.id,
                "header": level_row.header,
                "category": level_row.category,
                "kind": level_row.note,
                "holidays_fixed": holidays_fixed,
                "cells_changed": cells_changed,
            }
        )

    correction_log = pd.DataFrame(correction_rows)
    if correction_log.empty:
        correction_log = pd.DataFrame(
            columns=["id", "header", "category", "kind", "holidays_fixed", "cells_changed"]
        )
    else:
        correction_log = correction_log.sort_values(
            ["cells_changed", "header"], ascending=[False, True]
        ).reset_index(drop=True)
    corrected_series = len(correction_log)
    corrected_funds = int(correction_log["id"].nunique()) if corrected_series else 0
    cells_changed = int(correction_log["cells_changed"].sum()) if corrected_series else 0
    holiday_count = len(holiday_dates)
    first_holiday = holiday_dates.min()
    last_holiday = holiday_dates.max()
    correction_summary = mo.md(
        f"- **{holiday_count:,}** holidays, from **{first_holiday:%Y-%m-%d}** to **{last_holiday:%Y-%m-%d}**, where the S&P 500 TR level equals the previous close \n"
        f"- **{corrected_series:,}** series corrected, across **{corrected_funds:,}** funds \n"
        f"- **{cells_changed:,}** cells changed: holiday levels carried forward, holiday returns set to 0, and the next session's return recomputed when the level changed \n"
    )
    correction_table = mo.ui.table(
        correction_log,
        label="Corrected series",
        selection=None,
        pagination=len(correction_log) > 12,
        page_size=12,
        max_height=420,
    )
    mo.vstack([correction_summary, correction_table])
    return corrected_observations, correction_log, holiday_dates


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 6. Rescale level breaks

    A level break is a daily move of at least 50% that is still there over the next sessions, while the S&P 500 does not make a comparable move. The break is removed by rescaling the side that does not match the published NAV. The level in use today stays as published, and only the return on the join date is recomputed.

    A price drop whose total return does not jump is a distribution. The total return already records that corporate action, so the price is left unchanged.
    """)
    return


@app.cell
def _(catalog, corrected_observations, mo, pd):
    def lasting_breaks(source, catalog_frame):
        is_return = catalog_frame["note"].astype("string").str.startswith("Daily simple return")
        index_id = int(
            catalog_frame.loc[is_return & catalog_frame["header"].eq("S&P 500 TR %"), "column"].iloc[0]
        )
        market_return = source[index_id]
        found = []
        for return_row in catalog_frame.loc[is_return].itertuples(index=False):
            header = str(return_row.header)
            if header.endswith("Price %"):
                side = "Price"
            elif header.endswith("TR %"):
                side = "TR"
            else:
                continue
            returns = source[int(return_row.column)]
            gap = (returns - market_return).abs()
            candidates = returns.index[
                returns.notna()
                & market_return.notna()
                & returns.abs().ge(0.50)
                & gap.ge(0.25)
            ]
            values = returns.to_numpy(dtype="float64")
            for day in candidates:
                position = source.index.get_loc(day)
                follow = [value for value in values[position : position + 4] if value == value]
                if len(follow) < 2:
                    continue
                stayed = 1.0
                for value in follow:
                    stayed *= 1.0 + value
                stayed -= 1.0
                jump = float(values[position])
                if abs(stayed) < abs(jump) / 2:
                    continue
                found.append(
                    {
                        "isin": str(return_row.id),
                        "date": pd.Timestamp(day),
                        "side": side,
                        "stored_return": jump,
                    }
                )
        return found, market_return

    def fund_label(catalog_frame, isin):
        names = catalog_frame.loc[catalog_frame["id"].eq(isin), "name"].astype("string")
        label = str(names.iloc[0]) if len(names) else isin
        for suffix in (" - TOT RETURN IND", " - PRICE", " - TOTAL NET ASSETS"):
            if label.endswith(suffix):
                return label[: -len(suffix)]
        return label

    def column_id(catalog_frame, header):
        match = catalog_frame.loc[catalog_frame["header"].eq(header), "column"]
        if match.empty:
            return None
        return int(match.iloc[0])

    def changed_cells(before, after, tolerance):
        count = 0
        for left, right in zip(before, after, strict=True):
            left_missing = left != left
            right_missing = right != right
            if left_missing and right_missing:
                continue
            if left_missing or right_missing or abs(left - right) > tolerance:
                count += 1
        return count

    def scale_series(frame, catalog_frame, isin, side, day, factor, mode):
        level_id = column_id(catalog_frame, f"{isin} {side}")
        return_id = column_id(catalog_frame, f"{isin} {side} %")
        if level_id is None or return_id is None:
            return 0, None, None
        levels = frame[level_id].to_numpy(dtype="float64", copy=True)
        returns = frame[return_id].to_numpy(dtype="float64", copy=True)
        original_levels = levels.copy()
        original_returns = returns.copy()
        position = frame.index.get_loc(pd.Timestamp(day))
        if mode == "history":
            levels[:position] *= factor
        else:
            levels[position:] *= factor
        previous = levels[position - 1]
        current = levels[position]
        if previous == previous and current == current and previous != 0:
            returns[position] = current / previous - 1.0
        frame[level_id] = levels
        frame[return_id] = returns
        edited = changed_cells(original_levels, levels, 1e-8) + changed_cells(
            original_returns, returns, 1e-12
        )
        return edited, float(original_returns[position]), float(returns[position])

    def history_factor(frame, catalog_frame, isin, day, market_return):
        level_id = column_id(catalog_frame, f"{isin} Price")
        levels = frame[level_id]
        position = frame.index.get_loc(pd.Timestamp(day))
        previous = float(levels.iloc[position - 1])
        current = float(levels.iloc[position])
        session = float(market_return.iloc[position])
        return current / (previous * (1.0 + session))

    def forward_factor(frame, catalog_frame, isin, day, market_return, anchor):
        price_id = column_id(catalog_frame, f"{isin} Price")
        tr_id = column_id(catalog_frame, f"{isin} TR")
        position = frame.index.get_loc(pd.Timestamp(day))
        tr_level = frame[tr_id]
        if anchor == "price":
            price_level = frame[price_id]
            carried = float(tr_level.iloc[position - 1]) / float(price_level.iloc[position - 1])
            target = float(price_level.iloc[position]) * carried
        else:
            target = float(tr_level.iloc[position - 1]) * (1.0 + float(market_return.iloc[position]))
        return target / float(tr_level.iloc[position])

    # History is multiplied by `factor`. A split that was applied twice is 1/ratio².
    # `anchor` "market" stitches an index fund to that day's S&P return.
    # `anchor` "price" puts the total-return index back on the price scale.
    level_actions = [
        {
            "isin": "US2562191062",
            "date": "2025-10-27",
            "sides": ("Price", "TR"),
            "mode": "history",
            "factor": 1 / 256,
            "why": "16-for-1 split on 27 Oct 2025. Stored history is already 16× the published NAV, so the level has to be divided by 16² = 256.",
        },
        {
            "isin": "US1888501012",
            "date": "2025-05-12",
            "sides": ("Price", "TR"),
            "mode": "history",
            "factor": 1 / 100,
            "why": "10-for-1 split effective 12 May 2025. The 9 May print is 1,394.60, exactly 10× the fund's published $139.46, so history is divided by 10² = 100.",
        },
        {
            "isin": "US8085098551",
            "date": "2025-08-15",
            "sides": ("Price", "TR"),
            "mode": "history",
            "factor": 1 / 36,
            "why": "6-for-1 split effective 15 Aug 2025, with the same double scaling. History is divided by 6² = 36.",
        },
        {
            "isin": "US78472P1093",
            "date": "2020-04-20",
            "sides": ("Price", "TR"),
            "mode": "history",
            "factor": 6,
            "why": "1-for-6 reverse split effective 17 Apr 2020, first priced on the 20th because the 17th was Good Friday. Price and total return were both multiplied by 6. History is multiplied by 6 so the split is not a return.",
        },
        {
            "isin": "US2571321007",
            "date": "2016-07-12",
            "sides": ("Price", "TR"),
            "mode": "history",
            "factor": 2,
            "why": "Price and total return both double on 12 Jul 2016. The fund's published split is a different date and is already smooth here. Today's NAV matches the later scale, so earlier history is doubled.",
        },
        {
            "isin": "US85749T7569",
            "date": "2020-04-20",
            "sides": ("Price", "TR"),
            "mode": "history",
            "anchor": "market",
            "why": "Master-portfolio history is quoted near $0.60 until 20 Apr 2020, then switches to the published NAV. History is rescaled so that day's return equals the S&P 500.",
        },
        {
            "isin": "US00774Q8740",
            "date": "2022-12-29",
            "sides": ("TR",),
            "mode": "forward",
            "anchor": "price",
            "why": "The price is a normal NAV. Only the total-return index is rebased, from about 167 to about 277,000. Later total-return levels are divided back onto the price scale.",
        },
        {
            "isin": "US3161841008",
            "date": "2017-12-01",
            "sides": ("TR",),
            "mode": "forward",
            "anchor": "market",
            "why": "The price drop fits a December distribution. The total-return index jumps +77% on a base near 10¹⁰. Later total-return levels are rescaled so that day's return equals the S&P 500.",
        },
    ]
    kept_distributions = [
        {
            "isin": "US00791R7807",
            "date": "2025-12-18",
            "sides": ("Price",),
            "why": "Long-term capital gain of $15.1441 on 18 Dec 2025. The price falls from 18.75 to 3.76 and the total return stays near 246, so the price is the ex-distribution NAV and is not rescaled.",
        },
        {
            "isin": "US3624014086",
            "date": "2026-10-28",
            "sides": ("Price",),
            "why": "The price falls from 14.51 to 6.10 and stays there. That level matches the fund's published NAV, and the 25 Apr 2025 price matches the published $12.92. The total return does not fall. The fund's liquidation was announced on 14 Oct 2026.",
        },
    ]

    def describe_factor(factor, when):
        if factor >= 1:
            rounded = round(factor)
            if abs(factor - rounded) < 1e-6:
                return f"× {rounded:.0f} {when}"
            return f"× {factor:.4f} {when}"
        inverse = 1.0 / factor
        rounded = round(inverse)
        if abs(inverse - rounded) < 1e-4:
            return f"÷ {rounded:.0f} {when}"
        if inverse >= 100:
            return f"÷ {inverse:,.1f} {when}"
        return f"÷ {inverse:.4f} {when}"

    breaks, market_return = lasting_breaks(corrected_observations, catalog)
    break_keys = {(item["isin"], item["date"].strftime("%Y-%m-%d"), item["side"]) for item in breaks}
    stored_returns = {
        (item["isin"], item["date"].strftime("%Y-%m-%d"), item["side"]): item["stored_return"]
        for item in breaks
    }
    adjusted_observations = corrected_observations.copy()
    action_rows = []
    for action in level_actions:
        mode = action["mode"]
        if "factor" in action:
            factor = action["factor"]
        elif mode == "history":
            factor = history_factor(
                adjusted_observations, catalog, action["isin"], action["date"], market_return
            )
        else:
            factor = forward_factor(
                adjusted_observations,
                catalog,
                action["isin"],
                action["date"],
                market_return,
                action["anchor"],
            )
        when = "from the break forward" if mode == "forward" else "before the break"
        adjustment = describe_factor(factor, when)
        for side in action["sides"]:
            edited, return_before, return_after = scale_series(
                adjusted_observations,
                catalog,
                action["isin"],
                side,
                action["date"],
                factor,
                mode,
            )
            action_rows.append(
                {
                    "isin": action["isin"],
                    "fund": fund_label(catalog, action["isin"]),
                    "date": action["date"],
                    "series": side,
                    "decision": "rescaled",
                    "detected": (action["isin"], action["date"], side) in break_keys,
                    "adjustment": adjustment,
                    "return_before": return_before,
                    "return_after": return_after,
                    "cells": edited,
                    "why": action["why"],
                }
            )
    for action in kept_distributions:
        for side in action["sides"]:
            key = (action["isin"], action["date"], side)
            action_rows.append(
                {
                    "isin": action["isin"],
                    "fund": fund_label(catalog, action["isin"]),
                    "date": action["date"],
                    "series": side,
                    "decision": "kept",
                    "detected": key in break_keys,
                    "adjustment": "price left unchanged",
                    "return_before": stored_returns.get(key),
                    "return_after": stored_returns.get(key),
                    "cells": 0,
                    "why": action["why"],
                }
            )
    covered = {
        (action["isin"], action["date"], side)
        for action in [*level_actions, *kept_distributions]
        for side in action["sides"]
    }
    for item in breaks:
        key = (item["isin"], item["date"].strftime("%Y-%m-%d"), item["side"])
        if key in covered:
            continue
        action_rows.append(
            {
                "isin": item["isin"],
                "fund": fund_label(catalog, item["isin"]),
                "date": key[1],
                "series": item["side"],
                "decision": "not adjusted",
                "detected": True,
                "adjustment": "",
                "return_before": item["stored_return"],
                "return_after": item["stored_return"],
                "cells": 0,
                "why": "Level break with no corporate-action rule.",
            }
        )

    action_log = pd.DataFrame(action_rows)
    if action_log.empty:
        action_log = pd.DataFrame(
            columns=[
                "isin",
                "fund",
                "date",
                "series",
                "decision",
                "detected",
                "adjustment",
                "return_before",
                "return_after",
                "cells",
                "why",
            ]
        )
    rescaled = action_log.loc[action_log["decision"].eq("rescaled")]
    kept = action_log.loc[action_log["decision"].eq("kept")]
    action_summary = mo.md(
        f"- **{len(breaks):,}** level breaks detected, across **{action_log['isin'].nunique():,}** funds \n"
        f"- **{len(rescaled):,}** series rescaled, **{int(rescaled['cells'].sum()):,}** cells changed \n"
        f"- **{len(kept):,}** price series kept, because the total return already accounts for the distribution \n"
    )
    action_table = mo.ui.table(
        action_log,
        label="Level breaks",
        selection=None,
        pagination=False,
        page_size=20,
    )
    mo.vstack([action_summary, action_table])
    return action_log, adjusted_observations


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 7. Repair distribution-day total returns

    A spike is repaired when the total return disagrees with the price. On a distribution day the price falls by the payout and the total return should stay near that day's investment return. The total-return level from that day forward is rescaled so the day's return matches the S&P 500, and every later daily return stays as it was. The price is left as published.

    One spike, American Growth on 1 Dec 2025, is a single bad total-return print. Only that level is replaced, using the day's price return, and the next session's return is recomputed from the level already stored.

    Where the price and the total return make the same move, the NAV itself moved and the series is left unchanged.
    """)
    return


@app.cell
def _(adjusted_observations, catalog, mo, pd):
    def repair_distribution_spikes(source, catalog_frame):
        def column_id(header):
            match = catalog_frame.loc[catalog_frame["header"].eq(header), "column"]
            return None if match.empty else int(match.iloc[0])

        def fund_label(isin):
            names = catalog_frame.loc[catalog_frame["id"].eq(isin), "name"].astype("string")
            label = str(names.iloc[0]) if len(names) else isin
            for suffix in (" - TOT RETURN IND", " - PRICE", " - TOTAL NET ASSETS"):
                if label.endswith(suffix):
                    return label[: -len(suffix)]
            return label

        def changed_cells(before, after, tolerance):
            count = 0
            for left, right in zip(before, after, strict=True):
                left_missing = left != left
                right_missing = right != right
                if left_missing and right_missing:
                    continue
                if left_missing or right_missing or abs(left - right) > tolerance:
                    count += 1
            return count

        market_id = column_id("S&P 500 TR %")
        # Forward: the bad return stays in every later total-return level.
        # One-day: only that print is wrong; the next level is already right.
        repairs = [
            ("US3161841008", "2015-12-04", "forward", "Distributions of $0.392. The price falls 2.1% and the total return jumps +36%. The repaired return is the S&P return."),
            ("US3161841008", "2016-12-02", "forward", "Distributions of $0.186. The price falls 2.1% and the total return jumps +18%."),
            ("US3161841008", "2017-05-12", "forward", "Distributions of $0.555. The price falls 5.5% and the total return jumps +50%."),
            ("US3161841008", "2018-05-11", "forward", "Distributions of $0.507. The price falls 4.5% and the total return jumps +39%."),
            ("US78472P1093", "2019-12-20", "forward", "S&P index fund. The price falls 4.1% and the total return jumps +24% on a day the S&P rose 0.5%."),
            ("US85749T7569", "2019-12-20", "forward", "S&P index portfolio. The price falls 1.8% and the total return jumps +45% on a day the S&P rose 0.5%."),
            ("US38141W6205", "2021-12-14", "forward", "The price falls 22% and the total return only 14%, so the distribution was partly omitted. The day's total return is set to the S&P return."),
            ("US38141W6205", "2024-12-12", "forward", "The price falls 14% and the total return 12%. Same partial distribution add-back."),
            ("US63872T4893", "2021-12-23", "forward", "The price falls 27% and the total return 13% while the S&P rose 0.6%."),
            ("US7839808240", "2021-12-16", "forward", "The price falls 23% and the total return 11% while the S&P fell 0.9%."),
            ("US8085098064", "2021-12-16", "forward", "The price falls 23% and the total return 10% while the S&P fell 0.9%."),
            ("US0263933063", "2025-12-01", "one-day", "The total return jumps +14.6% and reverses the next day. The price does not jump. Only that total-return print is replaced."),
        ]
        kept_spikes = [
            ("US46090A7054", "2020-03-16", "Price and total return both rise 11.5% while the S&P falls 12%. The hedge paid off."),
            ("US00777X6452", "2020-03-18", "Price and total return both fall 10.9% in the March 2020 crash. The next day does not restore a different path."),
            ("US66538H5919", "2020-03-23", "Price and total return both fall 13% and rebound 16% the next day. Both series match."),
            ("US62827L4923", "2026-02-02", "Price and total return both rise 12% after a 9% drop, and the new level stays."),
            ("US15136Y4070", "2018-01-02", "Price and total return both rise 14.5%, and the new level stays."),
            ("US77926Y8232", "2026-10-22", "Price and total return both fall 10% against an S&P decline of 1.2%."),
            ("US77926Y8232", "2026-10-30", "Price and total return both fall 12% against an S&P decline of 1.8%. This is the last print in the file."),
        ]

        repaired = source.copy()
        market = repaired[market_id]
        rows = []
        for isin, day, mode, why in repairs:
            level_id = column_id(f"{isin} TR")
            return_id = column_id(f"{isin} TR %")
            price_return_id = column_id(f"{isin} Price %")
            position = repaired.index.get_loc(pd.Timestamp(day))
            levels = repaired[level_id].to_numpy(dtype="float64", copy=True)
            returns = repaired[return_id].to_numpy(dtype="float64", copy=True)
            original_levels = levels.copy()
            original_returns = returns.copy()
            previous = levels[position - 1]
            target = float(market.iloc[position] if mode == "forward" else repaired[price_return_id].iloc[position])
            if mode == "forward":
                levels[position:] *= (previous * (1.0 + target)) / levels[position]
                returns[position] = levels[position] / previous - 1.0
                adjustment = "total return set to the S&P return; later levels rescaled"
            else:
                levels[position] = previous * (1.0 + target)
                returns[position] = target
                following = position + 1
                if (
                    following < len(levels)
                    and levels[following] == levels[following]
                    and levels[position] != 0
                ):
                    returns[following] = levels[following] / levels[position] - 1.0
                adjustment = "spike-day level replaced with the price return; next return recomputed"
            repaired[level_id] = levels
            repaired[return_id] = returns
            rows.append(
                {
                    "isin": isin,
                    "fund": fund_label(isin),
                    "date": day,
                    "decision": "repaired",
                    "adjustment": adjustment,
                    "return_before": float(original_returns[position]),
                    "return_after": float(returns[position]),
                    "next_return_before": float(original_returns[position + 1]),
                    "next_return_after": float(returns[position + 1]),
                    "cells": changed_cells(original_levels, levels, 1e-8)
                    + changed_cells(original_returns, returns, 1e-12),
                    "why": why,
                }
            )
        for isin, day, why in kept_spikes:
            return_id = column_id(f"{isin} TR %")
            position = repaired.index.get_loc(pd.Timestamp(day))
            stored = float(repaired[return_id].iloc[position])
            rows.append(
                {
                    "isin": isin,
                    "fund": fund_label(isin),
                    "date": day,
                    "decision": "kept",
                    "adjustment": "left unchanged",
                    "return_before": stored,
                    "return_after": stored,
                    "next_return_before": None,
                    "next_return_after": None,
                    "cells": 0,
                    "why": why,
                }
            )
        log = pd.DataFrame(rows)
        return repaired, log

    repaired_observations, distribution_log = repair_distribution_spikes(
        adjusted_observations, catalog
    )
    repaired_rows = distribution_log.loc[distribution_log["decision"].eq("repaired")]
    kept_rows = distribution_log.loc[distribution_log["decision"].eq("kept")]
    distribution_summary = mo.md(
        f"- **{len(repaired_rows):,}** distribution days repaired, on **{repaired_rows['isin'].nunique():,}** total-return series \n"
        f"- **{int(repaired_rows['cells'].sum()):,}** cells changed \n"
        f"- **{len(kept_rows):,}** spikes left unchanged, because the price and the total return agree \n"
    )
    distribution_table = mo.ui.table(
        distribution_log,
        label="Distribution-day spikes",
        selection=None,
        pagination=False,
        page_size=20,
    )
    mo.vstack([distribution_summary, distribution_table])
    return distribution_log, repaired_observations


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 8. Conclusion

    The total-return series are usable for performance measurement and for a regression against the S&P 500.

    Rescored on this repaired file, the 307 price total-return series have no gaps and no level jumps. The holiday placeholders, the split and unit breaks, and the distribution days where the total return disagreed with the price are corrected above.

    Fifty series are flagged only because a day differs from the S&P 500 by 5% or more. Thirty-four of those have a single such day in eleven years. That is active risk. Seven spikes remain because the price and the total return make the same move: Invesco Downside Hedged on 16 Mar 2020, Patient Opportunity Trust C on 18 Mar 2020, Main Sector Rotation on 23 Mar 2020, Copley on 2 Jan 2018, Catalyst Insider Buying A on 2 Feb 2026, and Roundhill S&P 500 Target 10000 2030 on 22 Oct 2026 and 30 Oct 2026.

    Three scale flags are explained and left as published. Principal Value ETF printed a flat NAV on most days from 2016 through 2018. Allspring Core Builder is flat for its first fortnight. Johnson Enhanced Return goes to cash after 18 Oct 2026 because the fund liquidates around 30 Nov 2026. The price drop on 26 Oct is the published $1.53 distribution, and the total return already includes it.

    Four series should be set aside before a statistic is computed. Fifth Third Equity Index A (US31678R6760), Large Cap Core A (US31678R6273) and Dividend Growth A (US3167865654) never move: price and total return stay at one number from November 2015 through October 2026. Fidelity Advisor Mega Cap (US31617F8178) is unchanged on 76% of days, so its volatility and beta would be too low. Principal Value ETF can be used from 2019, once the NAV is marked daily.

    On the Goldman, Natixis, SEI and Schwab distribution days where the dollar amount could not be confirmed, that single day's total return was set equal to the S&P 500. Across roughly 2,800 days this does not move a Sharpe ratio, an alpha, or a tracking error.

    Use the total-return column for the study. The price column still falls by the distribution, which is the published NAV.

    The corrected sheet is saved beside the source as `output-data/v2-d-timeseries-corrected.xlsx`. It keeps the six label rows and the same columns. The source file is left as it was, so running this notebook again does not apply the corrections a second time. Opening the notebook leaves the corrected file in place. The button below writes it again.
    """)
    return


@app.cell
def _(mo, workbook):
    import zipfile

    corrected_destination = workbook.parent / "v2-d-timeseries-corrected.xlsx"

    def corrected_workbook_ready(path) -> bool:
        if not path.is_file() or path.stat().st_size < 1_000_000:
            return False
        try:
            with zipfile.ZipFile(path) as book:
                return (
                    book.testzip() is None
                    and "xl/worksheets/sheet1.xml" in book.namelist()
                )
        except zipfile.BadZipFile:
            return False

    corrected_workbook_exists = corrected_workbook_ready(corrected_destination)
    save_corrected_button = mo.ui.run_button(
        label="Write the corrected workbook again"
        if corrected_workbook_exists
        else "Save the corrected workbook"
    )
    corrected_status = mo.md(
        f"- Corrected workbook: `{corrected_destination}` \n"
        + (
            "- The file is already saved. Opening this notebook does not rewrite it. \n"
            if corrected_workbook_exists
            else "- The file is not saved yet. \n"
        )
    )
    mo.vstack([corrected_status, save_corrected_button])
    return corrected_destination, save_corrected_button


@app.cell
def _(
    corrected_destination,
    label_rows,
    mo,
    observations,
    pd,
    raw,
    repaired_observations,
    save_corrected_button,
    workbook,
):
    def export_corrected_series():
        import os
        import tempfile

        if not repaired_observations.columns.equals(observations.columns):
            raise ValueError("Corrected columns do not match the loaded sheet")
        if not repaired_observations.index.equals(observations.index):
            raise ValueError("Corrected dates do not match the loaded sheet")
        if corrected_destination.resolve() == workbook.resolve():
            raise ValueError("Refusing to overwrite the source workbook")
        difference = observations.sub(repaired_observations).abs()
        changed = difference.gt(1e-12) | (
            observations.isna() ^ repaired_observations.isna()
        )
        sheet = raw.copy()
        block = sheet.iloc[label_rows:, 1:].to_numpy(copy=True)
        changed_positions = changed.to_numpy()
        block[changed_positions] = repaired_observations.to_numpy()[changed_positions]
        sheet.iloc[label_rows:, 1:] = block
        temporary_handle = tempfile.NamedTemporaryFile(
            prefix="v2-d-timeseries-corrected-",
            suffix=".xlsx",
            delete=False,
        )
        temporary_path = temporary_handle.name
        temporary_handle.close()
        try:
            # Local temp file: writing the zip straight into this folder times out.
            sheet.to_excel(
                temporary_path, index=False, header=False, engine="openpyxl"
            )
            try:
                os.replace(temporary_path, corrected_destination)
            except OSError:
                import shutil

                shutil.move(temporary_path, corrected_destination)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        return int(changed_positions.sum())

    corrected_export_note = None
    if save_corrected_button.value:
        corrected_cell_count = export_corrected_series()
        corrected_export_note = mo.md(
            f"- Wrote **{corrected_cell_count:,}** corrected cells to `{corrected_destination}` \n"
            f"- Source left unchanged: `{workbook}` \n"
        )
    corrected_export_note
    return


if __name__ == "__main__":
    app.run()
