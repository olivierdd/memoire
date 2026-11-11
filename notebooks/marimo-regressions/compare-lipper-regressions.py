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
app = marimo.App(width="full", app_title="Daily regressions vs Lipper")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Daily regressions vs Lipper

    Load `output-data/v2-funds-normalized.xlsx`. For each fund on the sheet `Funds final`,
    compound daily total returns to calendar months, regress the fund on its Lipper reference
    benchmark over 3, 5, and 10 years, and compare alpha, beta, R², and annualized tracking error
    with Lipper’s precomputed Funds columns.

    The daily series are read from `D-Timeseries final`, the cleaned series written by
    `load-series-v2.py`.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Method

    - Daily `… TR %` columns only. Month return compounds within the calendar month.
    - Regression windows end on **30 September 2026**, the last month Lipper uses on the Funds sheet.
    - Benchmark mapping: `.SPXTR` → `S&P 500 TR %`, `.INX` → `S&P 500 C Price %`.
    - OLS: fund monthly return on benchmark monthly return (no risk-free subtraction).
    - Lipper alpha is percent per month; tracking error is annualized percent.
    - **Total return** compounds fund monthly returns over the horizon (%); compared to Lipper `{N} Year Performance to Last Month End`. The section below takes that comparison on its own for 3, 5, and 10 years.
    - **Sharpe** is annualized mean ÷ std of monthly returns (excess over 3M T-bill when that series is present on the daily sheet; otherwise raw monthly returns).
    - A horizon **matches** when |Δα| ≤ 0.05 pp/mo, |Δβ| ≤ 0.05, |ΔR²| ≤ 0.05, |ΔTE| ≤ 0.5 pp.
    """)
    return


@app.cell
def _():
    import pathlib
    import sys

    import altair as alt

    import pandas as pd

    start = pathlib.Path.cwd().resolve()
    for directory in [start, *start.parents]:
        if (directory / "helpers").is_dir():
            root = str(directory)
            if root not in sys.path:
                sys.path.insert(0, root)
            break
    else:
        raise FileNotFoundError(f"Could not find helpers/, starting from {start}")

    from helpers.timeseries_functions.regress_daily_to_benchmark import (
        DEFAULT_WORKBOOK_FILENAME,
        FUNDS_SHEET,
        compare_daily_sheets_to_lipper,
        find_output_data_file,
        load_funds_reference,
        fit_monthly_regression,
        fund_lipper_match_summary,
        match_rate_by_horizon,
        index_total_return_check,
        monthly_scatter_frame,
        total_return_lipper_report,
    )

    workbook = find_output_data_file(DEFAULT_WORKBOOK_FILENAME)
    funds = load_funds_reference(workbook)
    comparison, monthly_panels, series_sheets, level_identity = compare_daily_sheets_to_lipper(
        workbook, funds=funds
    )
    # The scatter below uses the cleaned series when there is one.
    primary_source = next(iter(series_sheets))
    return (
        FUNDS_SHEET,
        alt,
        comparison,
        fit_monthly_regression,
        fund_lipper_match_summary,
        funds,
        level_identity,
        match_rate_by_horizon,
        monthly_panels,
        index_total_return_check,
        monthly_scatter_frame,
        pd,
        primary_source,
        series_sheets,
        total_return_lipper_report,
        workbook,
    )


@app.cell
def _(FUNDS_SHEET, comparison, funds, mo, pd, series_sheets, workbook):
    ticker_counts = (
        funds.groupby("Benchmark Ticker", dropna=False)
        .size()
        .reset_index(name="funds")
        .sort_values("funds", ascending=False)
    )
    last_month = comparison.loc[
        comparison["status"].eq("ok"), "window_end"
    ].dropna().max()
    comparable = comparison.loc[comparison["status"].eq("ok"), "isin"].nunique()
    sheet_lines = "".join(
        f"- **Daily series:** sheet `{sheet}` \n"
        for sheet in series_sheets.values()
    )
    summary = mo.md(
        f"- **Workbook:** `{workbook}` \n"
        f"- **Funds:** sheet `{FUNDS_SHEET}` ({len(funds):,} rows) \n"
        + sheet_lines
        + f"- **Comparable regressions:** {comparable:,} funds with a mapped benchmark on the sheet \n"
        + f"- **Regression window ends:** {last_month} \n"
    )
    tickers = mo.ui.table(
        ticker_counts,
        label="Funds by Lipper benchmark ticker",
        selection=None,
        pagination=False,
    )
    mo.vstack([summary, tickers])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Match rates

    Share of funds-with-Lipper-beta whose horizon lies within the tolerances above.
    """)
    return


@app.cell
def _(comparison, fund_lipper_match_summary, match_rate_by_horizon, mo, pd):
    horizon_rates = match_rate_by_horizon(comparison)
    horizon_rates = horizon_rates.assign(
        match_rate_pct=(horizon_rates["match_rate"] * 100).round(1)
    )
    fund_summary = fund_lipper_match_summary(comparison)
    all_horizons = (
        fund_summary.groupby("series_source", as_index=False)
        .agg(
            funds=("isin", "count"),
            all_horizons_match=("lipper_match", "sum"),
        )
        .assign(
            match_rate=lambda frame: (
                frame["all_horizons_match"] / frame["funds"]
            ).round(3)
        )
    )
    mo.vstack(
        [
            mo.ui.table(
                horizon_rates[
                    [
                        "series_source",
                        "horizon",
                        "funds",
                        "match",
                        "match_rate_pct",
                    ]
                ],
                label="Match rate by horizon",
                selection=None,
                pagination=False,
            ),
            mo.ui.table(
                all_horizons,
                label="Funds matching Lipper on every horizon with reference data",
                selection=None,
                pagination=False,
            ),
        ]
    )
    return (fund_summary, horizon_rates)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Comparison table

    One row per fund and horizon, from `D-Timeseries final`.
    """)
    return


@app.cell
def _(comparison, mo):
    display_cols = [
        "isin",
        "name",
        "series_source",
        "horizon",
        "benchmark_ticker",
        "months",
        "alpha_pct_per_month",
        "lipper_alpha_pct_per_month",
        "delta_alpha_pp_per_month",
        "beta",
        "lipper_beta",
        "delta_beta",
        "r_squared",
        "lipper_r_squared",
        "delta_r_squared",
        "tracking_error_ann_pct",
        "lipper_tracking_error_ann_pct",
        "delta_tracking_error_pp",
        "total_return_pct",
        "lipper_total_return_pct",
        "delta_total_return_pct",
        "sharpe_ratio",
        "lipper_sharpe",
        "delta_sharpe",
        "lipper_match",
        "status",
    ]
    table_frame = comparison.loc[:, display_cols].copy()
    for col in table_frame.columns:
        if table_frame[col].dtype.kind in "fc":
            table_frame[col] = table_frame[col].round(4)
    comparison_table = mo.ui.table(
        table_frame,
        label="Notebook vs Lipper",
        selection=None,
        page_size=25,
    )
    comparison_table
    return (comparison_table, display_cols, table_frame)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## One fund: monthly scatter

    Pick a fund and horizon. Points are monthly total returns from `D-Timeseries final`; the line is the OLS fit.
    """)
    return


@app.cell
def _(comparison, mo, pd, primary_source):
    pickable = (
        comparison.loc[
            comparison["status"].eq("ok") & comparison["series_source"].eq(primary_source)
        ][["isin", "name"]]
        .drop_duplicates()
        .sort_values("name")
    )
    labels = {
        f"{row.isin}": f"{row.name} ({row.isin})"
        for row in pickable.itertuples(index=False)
    }
    fund_picker = mo.ui.dropdown(
        options=labels,
        value=next(iter(labels)) if labels else None,
        label="Fund",
        searchable=True,
    )
    horizon_picker = mo.ui.dropdown(
        options=["3y", "5y", "10y"],
        value="10y",
        label="Horizon",
    )
    mo.hstack([fund_picker, horizon_picker])
    return fund_picker, horizon_picker, labels, pickable


@app.cell
def _(
    alt,
    comparison,
    fit_monthly_regression,
    fund_picker,
    horizon_picker,
    labels,
    mo,
    monthly_panels,
    monthly_scatter_frame,
    pd,
    primary_source,
):
    horizon_months = {"3y": 36, "5y": 60, "10y": 120}
    horizon_labels = {"3 years": "3y", "5 years": "5y", "10 years": "10y"}
    picked_fund = fund_picker.value
    isin = picked_fund if picked_fund in labels else next(
        (key for key, text in labels.items() if text == picked_fund),
        picked_fund,
    )
    picked_horizon = horizon_picker.value
    horizon = horizon_labels.get(picked_horizon, picked_horizon)
    n_months = horizon_months[horizon]
    row = comparison.loc[
        comparison["isin"].eq(isin)
        & comparison["series_source"].eq(primary_source)
        & comparison["horizon"].eq(horizon)
    ]
    mo.stop(not isin or row.empty, mo.md("Choose a fund with a completed regression."))
    row = row.iloc[0]
    bench_header = row["benchmark_header"]
    monthly = monthly_panels[primary_source]
    scatter = monthly_scatter_frame(
        monthly, isin, bench_header, last_n_months=n_months
    )
    fit = fit_monthly_regression(
        monthly[f"{isin} TR %"],
        monthly[bench_header],
        horizon=horizon,
        last_n_months=n_months,
    )
    mo.stop(fit is None, mo.md("Not enough months for this horizon."))
    line = pd.DataFrame(
        {
            "benchmark": [
                scatter["benchmark"].min(),
                scatter["benchmark"].max(),
            ],
            "fund": [
                fit.alpha_pct_per_month / 100 + fit.beta * scatter["benchmark"].min(),
                fit.alpha_pct_per_month / 100 + fit.beta * scatter["benchmark"].max(),
            ],
        }
    )
    points = (
        alt.Chart(scatter)
        .mark_circle(size=50, opacity=0.75)
        .encode(
            x=alt.X("benchmark:Q", title=bench_header, axis=alt.Axis(format="%")),
            y=alt.Y("fund:Q", title=f"{isin} TR %", axis=alt.Axis(format="%")),
            tooltip=[
                alt.Tooltip("month:N", title="Month"),
                alt.Tooltip("benchmark:Q", format=".2%"),
                alt.Tooltip("fund:Q", format=".2%"),
            ],
        )
    )
    rule = (
        alt.Chart(line)
        .mark_line(color="#C2410C", strokeWidth=2)
        .encode(x="benchmark:Q", y="fund:Q")
    )
    def _annualized_alpha(monthly_pct: object) -> str:
        # Lipper and the OLS intercept are percent per month; ×12 matches the sheet.
        if pd.isna(monthly_pct):
            return "n/a"
        return f"{float(monthly_pct) * 12:+.2f}%/yr"

    def _coef(value: object) -> str:
        if pd.isna(value):
            return "n/a"
        return f"{float(value):.3f}"

    ours = (
        f"α = {_annualized_alpha(fit.alpha_pct_per_month)}, "
        f"β = {_coef(fit.beta)}, "
        f"R² = {_coef(fit.r_squared)}"
    )
    lipper = (
        f"Lipper α = {_annualized_alpha(row['lipper_alpha_pct_per_month'])}, "
        f"β = {_coef(row['lipper_beta'])}, "
        f"R² = {_coef(row['lipper_r_squared'])}"
    )
    chart = (points + rule).properties(
        width=720,
        height=380,
        title=alt.Title(
            f"{row['name']}",
            subtitle=f"{horizon}: {ours} ({lipper})",
        ),
    )
    chart
    return bench_header, chart, fit, horizon, horizon_months, isin, line, n_months, points, row, rule, scatter


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Lipper metrics, one at a time

    The comparison table carries every statistic on the same row. Each section below takes one Lipper column and sets it next to the same figure computed from `D-Timeseries final`.

    ## Total return

    The computed total return compounds the fund's own monthly total returns over the last 36, 60, or 120 months. It does not use the benchmark. The horizon return is the product of `(1 + monthly return)`, minus 1, in percent.

    Lipper's column is `{N} Year Performance to Last Month End`, also a cumulative percent, as of 30 September 2026. The charts keep a fund when that column is filled and the cleaned series has every month of the horizon. The gap is the computed return minus Lipper, in percentage points. A fund is marked close when the absolute gap is within 1 percentage point.

    Three 10-year performance cells store the decimal mark as a comma (`314,26` and two others). Those cells are read as decimals.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Index

    The same compounding, applied to `S&P 500 TR %`. That is the daily series behind Lipper's `.SPXTR` benchmark. Lipper does not publish the index return as its own column. For each fund it is the performance column minus `Relative Performance for {N} Years to Last Month End, (%)`. The print in the table is the one shared by the most funds on `.SPXTR`. The wider count adds the neighbouring hundredth, because both Lipper inputs are stored to 0.01.
    """)
    return


@app.cell
def _(funds, index_total_return_check, mo, monthly_panels, primary_source):
    index_returns = index_total_return_check(
        monthly_panels[primary_source], funds
    )
    index_matched = bool(index_returns["delta_pp"].abs().le(0.01).all())
    if index_matched:
        index_note = mo.md(
            "The compounded S&P 500 total return matches Lipper's index print on 3, 5, and 10 years, to the hundredth of a percent. The fund gaps below are not produced by the window or by the compounding."
        )
    else:
        index_note = mo.md(
            "The compounded S&P 500 total return does not match Lipper's index print on every horizon. The gap is computed minus Lipper."
        )
    index_shown = index_returns.assign(
        computed_pct=lambda frame: frame["computed_pct"].round(4),
        lipper_pct=lambda frame: frame["lipper_pct"].round(2),
        delta_pp=lambda frame: frame["delta_pp"].round(4),
    )[
        [
            "horizon",
            "window_start",
            "window_end",
            "months",
            "computed_pct",
            "lipper_pct",
            "delta_pp",
            "funds_on_print",
            "funds_within_cent",
            "funds_with_both",
        ]
    ].rename(
        columns={
            "horizon": "Horizon",
            "window_start": "Window start",
            "window_end": "Window end",
            "months": "Months",
            "computed_pct": "Computed (%)",
            "lipper_pct": "Lipper index (%)",
            "delta_pp": "Gap (pp)",
            "funds_on_print": "Funds on the print",
            "funds_within_cent": "Funds within 0.01",
            "funds_with_both": "Funds with both figures",
        }
    )
    index_table = mo.ui.table(
        index_shown,
        label="S&P 500 TR against the Lipper index print",
        selection=None,
        pagination=False,
    )
    mo.vstack([index_note, index_table])
    return (index_matched, index_returns, index_shown, index_table)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Funds
    """)
    return


@app.cell
def _(comparison, mo, total_return_lipper_report):
    total_return = total_return_lipper_report(comparison)
    total_return_summary = total_return.summary
    gap_bits = []
    for horizon_row in total_return_summary.itertuples(index=False):
        if horizon_row.compared == 0 or horizon_row.median_gap_pp != horizon_row.median_gap_pp:
            continue
        if horizon_row.same_window == horizon_row.compared:
            window_note = f"{horizon_row.window_start} to {horizon_row.window_end}"
        else:
            window_note = (
                f"{horizon_row.window_start} to {horizon_row.window_end} "
                f"for {int(horizon_row.same_window)} of {int(horizon_row.compared)} funds"
            )
        gap_bits.append(
            f"- **{horizon_row.horizon}** ({window_note}): "
            f"median gap **{horizon_row.median_gap_pp:+.2f} pp** "
            f"across {horizon_row.compared:,} funds, "
            f"{horizon_row.within_close_share:.0%} within 1 pp, "
            f"correlation {horizon_row.correlation:.3f}"
        )
    below = (total_return_summary["median_gap_pp"] < 0).all()
    direction = (
        "The computed return sits below Lipper on every horizon. The gap widens as the window gets longer."
        if below
        else "The median gap changes sign across horizons."
    )
    coverage = mo.md(direction + "\n\n" + "\n".join(gap_bits))
    shown = total_return_summary.assign(
        median_gap_pp=lambda frame: frame["median_gap_pp"].round(2),
        median_abs_gap_pp=lambda frame: frame["median_abs_gap_pp"].round(2),
        max_abs_gap_pp=lambda frame: frame["max_abs_gap_pp"].round(2),
        within_1pp_pct=lambda frame: (frame["within_close_share"] * 100).round(1),
        below_lipper_pct=lambda frame: (frame["negative_share"] * 100).round(1),
        correlation=lambda frame: frame["correlation"].round(3),
    )[
        [
            "horizon",
            "computed",
            "full_window",
            "lipper_present",
            "compared",
            "window_start",
            "window_end",
            "same_window",
            "median_gap_pp",
            "median_abs_gap_pp",
            "max_abs_gap_pp",
            "within_close",
            "within_1pp_pct",
            "below_lipper_pct",
            "correlation",
        ]
    ].rename(
        columns={
            "horizon": "Horizon",
            "computed": "Computed",
            "full_window": "Full window",
            "lipper_present": "Lipper published",
            "compared": "Compared",
            "window_start": "Window start",
            "window_end": "Window end",
            "same_window": "Funds on that window",
            "median_gap_pp": "Median gap (pp)",
            "median_abs_gap_pp": "Median |gap| (pp)",
            "max_abs_gap_pp": "Largest |gap| (pp)",
            "within_close": "Within 1 pp",
            "within_1pp_pct": "Share within 1 pp",
            "below_lipper_pct": "Share below Lipper",
            "correlation": "Correlation",
        }
    )
    summary_table = mo.ui.table(
        shown,
        label="Total return by horizon",
        selection=None,
        pagination=False,
    )
    mo.vstack([coverage, summary_table])
    return (total_return,)


@app.cell
def _(alt, mo, pd, total_return):
    compared = total_return.comparable.copy()
    compared["agreement"] = compared["within_close"].map(
        {True: "within 1 pp", False: "beyond 1 pp"}
    )
    agreement_scale = alt.Scale(
        domain=["within 1 pp", "beyond 1 pp"],
        range=["#1D4E89", "#C2410C"],
    )
    scatters = []
    gaps = []
    for horizon_name in ["3y", "5y", "10y"]:
        group = compared.loc[compared["horizon"].eq(horizon_name)]
        if group.empty:
            continue
        low = float(
            min(group["total_return_pct"].min(), group["lipper_total_return_pct"].min())
        )
        high = float(
            max(group["total_return_pct"].max(), group["lipper_total_return_pct"].max())
        )
        identity_frame = pd.DataFrame(
            {
                "total_return_pct": [low, high],
                "lipper_total_return_pct": [low, high],
            }
        )
        return_points = (
            alt.Chart(group)
            .mark_circle(size=36, opacity=0.75)
            .encode(
                x=alt.X("total_return_pct:Q", title="Computed (%)"),
                y=alt.Y("lipper_total_return_pct:Q", title="Lipper (%)"),
                color=alt.Color(
                    "agreement:N",
                    title=None,
                    scale=agreement_scale,
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("name:N", title="Fund"),
                    alt.Tooltip("isin:N", title="ISIN"),
                    alt.Tooltip("total_return_pct:Q", title="Computed", format=".2f"),
                    alt.Tooltip("lipper_total_return_pct:Q", title="Lipper", format=".2f"),
                    alt.Tooltip("delta_total_return_pct:Q", title="Gap (pp)", format="+.2f"),
                ],
            )
        )
        identity = (
            alt.Chart(identity_frame)
            .mark_line(strokeDash=[4, 4], color="#78716C")
            .encode(x="total_return_pct:Q", y="lipper_total_return_pct:Q")
        )
        scatters.append(
            (return_points + identity).properties(width=240, height=240, title=horizon_name)
        )
        bars = (
            alt.Chart(group)
            .mark_bar(color="#1D4E89")
            .encode(
                x=alt.X(
                    "delta_total_return_pct:Q",
                    bin=alt.Bin(maxbins=24),
                    title="Computed − Lipper (pp)",
                ),
                y=alt.Y("count()", title="Funds"),
            )
        )
        zero_rule = (
            alt.Chart(pd.DataFrame({"delta_total_return_pct": [0.0]}))
            .mark_rule(color="#C2410C", strokeWidth=1.5)
            .encode(x="delta_total_return_pct:Q")
        )
        gaps.append(
            (bars + zero_rule).properties(width=240, height=160, title=horizon_name)
        )
    scatter_by_horizon = alt.hconcat(*scatters).resolve_scale(color="shared")
    gap_by_horizon = alt.hconcat(*gaps)
    mo.vstack(
        [
            mo.md(
                "Each point is one fund. The dashed line is equality. "
                "The orange line on the histograms is a gap of zero."
            ),
            scatter_by_horizon,
            gap_by_horizon,
        ]
    )
    return (compared, gap_by_horizon, scatter_by_horizon)


@app.cell
def _(mo):
    total_return_horizon = mo.ui.dropdown(
        options=["all", "3y", "5y", "10y"],
        value="all",
        label="Horizon",
    )
    total_return_horizon
    return (total_return_horizon,)


@app.cell
def _(compared, mo, total_return, total_return_horizon):
    picked_return_horizon = total_return_horizon.value
    detail = compared if picked_return_horizon == "all" else compared.loc[
        compared["horizon"].eq(picked_return_horizon)
    ]
    detail = detail.sort_values("abs_delta_total_return_pct", ascending=False)
    detail_shown = detail[
        [
            "name",
            "isin",
            "horizon",
            "window_start",
            "window_end",
            "months",
            "total_return_pct",
            "lipper_total_return_pct",
            "delta_total_return_pct",
            "agreement",
        ]
    ].copy()
    for return_col in (
        "total_return_pct",
        "lipper_total_return_pct",
        "delta_total_return_pct",
    ):
        detail_shown[return_col] = detail_shown[return_col].round(2)
    detail_shown["months"] = detail_shown["months"].astype(int)
    detail_shown = detail_shown.rename(
        columns={
            "name": "Fund",
            "isin": "ISIN",
            "horizon": "Horizon",
            "window_start": "Window start",
            "window_end": "Window end",
            "months": "Months",
            "total_return_pct": "Computed (%)",
            "lipper_total_return_pct": "Lipper (%)",
            "delta_total_return_pct": "Gap (pp)",
            "agreement": "Agreement",
        }
    )
    detail_table = mo.ui.table(
        detail_shown,
        label="Largest total-return gaps first",
        selection=None,
        page_size=15,
    )
    short = total_return.short_window
    short_shown = None
    if short.empty:
        short_note = mo.md(
            "Every fund with a Lipper total return has the full month count for that horizon."
        )
        short_table = None
    else:
        short_shown = short[
            [
                "name",
                "isin",
                "horizon",
                "months",
                "window_start",
                "window_end",
                "total_return_pct",
                "lipper_total_return_pct",
                "delta_total_return_pct",
            ]
        ].copy()
        for return_col in (
            "total_return_pct",
            "lipper_total_return_pct",
            "delta_total_return_pct",
        ):
            short_shown[return_col] = short_shown[return_col].round(2)
        short_shown["months"] = short_shown["months"].astype(int)
        short_shown = short_shown.rename(
            columns={
                "name": "Fund",
                "isin": "ISIN",
                "horizon": "Horizon",
                "months": "Months",
                "window_start": "Window start",
                "window_end": "Window end",
                "total_return_pct": "Computed (%)",
                "lipper_total_return_pct": "Lipper (%)",
                "delta_total_return_pct": "Gap (pp)",
            }
        )
        short_note = mo.md(
            "These funds have a Lipper performance and fewer months than the horizon, so they are left off the charts. A short series uses the same months for every longer horizon, and that number is not a 5-year or a 10-year return."
        )
        short_table = mo.ui.table(
            short_shown,
            label="Shorter than the horizon",
            selection=None,
            pagination=False,
        )
    blocks = [detail_table, short_note]
    if short_table is not None:
        blocks.append(short_table)
    mo.vstack(blocks)
    return (detail, detail_shown, detail_table, picked_return_horizon, short, short_note, short_shown, short_table)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Where the gap comes from

    The compounded return is the change in the fund's own total-return level between the same two dates used for the index. Checked across every fund and horizon, that level change equals the compounded daily return, no session inside the window is blank, and no stored return disagrees with the level. The calendar and the compounding are not the source of the gap. The gap is Lipper's published performance versus this Datastream total-return index.

    Two patterns account for most of the difference.

    **December.** A missed year-end distribution leaves the total return lagging the S&P in December and too low after that. Over 10 years the median gap is **−2.3 pp** when those Decembers stay within 1% of the S&P, and **−11.2 pp** when they lag by 2% or more. December accounts for about half of the variation (R² 0.48). S&P 500 ETFs, which distribute little capital gain, stay within about 1 pp. Several S&P 500 mutual funds do not, and an index fund cannot lose tens of percent to the S&P unless the series dropped a distribution.

    **Repairs.** A few series were rescaled by hand in `load-series-v2.py`. When the repaired date sits inside the horizon, that horizon moves and the shorter ones do not. State Street S&P 500 Index Fund N is the clear case: the April 2020 rescaling is inside the 10-year window only.

    The expense ratio does not line up with the gap. Lipper's relative-performance column implies more than one benchmark return, but the performance gap is about the same size inside each of those groups, so that column is not the cause.
    """)
    return


@app.cell
def _(
    alt,
    funds,
    level_identity,
    mo,
    monthly_panels,
    pd,
    primary_source,
    total_return,
):
    import numpy as np

    from helpers.timeseries_functions.total_return_gap import (
        return_gap_attribution,
        return_gap_cause_summary,
    )

    checked_levels = level_identity.dropna(subset=["abs_diff_pp"])
    level_gap = float(checked_levels["abs_diff_pp"].max()) if len(checked_levels) else np.nan
    level_note = mo.md(
        f"Level against compounded return, {len(checked_levels):,} fund-horizons: "
        f"largest absolute difference **{level_gap:.4f} pp**, "
        f"**{int(checked_levels['n_missing'].sum()):,}** missing sessions, "
        f"**{int(checked_levels['n_breaks'].sum()):,}** days where the stored return disagrees with the level."
    )
    gap_attribution = return_gap_attribution(
        monthly_panels[primary_source], total_return.comparable, funds
    )
    cause_summary = return_gap_cause_summary(gap_attribution)
    cause_shown = cause_summary.assign(
        corr_gap_december=lambda frame: frame["corr_gap_december"].round(2),
        r_squared_december=lambda frame: frame["r_squared_december"].round(2),
        median_gap_quiet_december=lambda frame: frame["median_gap_quiet_december"].round(2),
        median_gap_large_december=lambda frame: frame["median_gap_large_december"].round(2),
        corr_gap_expense=lambda frame: frame["corr_gap_expense"].round(2),
    )[
        [
            "horizon",
            "funds",
            "corr_gap_december",
            "r_squared_december",
            "n_quiet_december",
            "median_gap_quiet_december",
            "n_large_december",
            "median_gap_large_december",
            "corr_gap_expense",
        ]
    ].rename(
        columns={
            "horizon": "Horizon",
            "funds": "Funds",
            "corr_gap_december": "Corr. with December",
            "r_squared_december": "R²",
            "n_quiet_december": "Quiet Decembers",
            "median_gap_quiet_december": "Median gap, quiet (pp)",
            "n_large_december": "December lags",
            "median_gap_large_december": "Median gap, December lag (pp)",
            "corr_gap_expense": "Corr. with expense ratio",
        }
    )
    cause_table = mo.ui.table(
        cause_shown,
        label="Gap against the December shortfall and the expense ratio",
        selection=None,
        pagination=False,
    )
    ten_year = gap_attribution.loc[gap_attribution["horizon"].eq("10y")].dropna(
        subset=["december_log_excess", "gap_pp"]
    ).copy()
    ten_year_line = pd.DataFrame(
        {
            "december_log_excess": [
                ten_year["december_log_excess"].min(),
                ten_year["december_log_excess"].max(),
            ]
        }
    )
    slope, intercept = np.polyfit(
        ten_year["december_log_excess"], ten_year["gap_pp"], 1
    )
    ten_year_line["gap_pp"] = intercept + slope * ten_year_line["december_log_excess"]
    december_points = (
        alt.Chart(ten_year)
        .mark_circle(size=36, opacity=0.75, color="#1D4E89")
        .encode(
            x=alt.X(
                "december_log_excess:Q",
                title="Sum of December log excess versus the S&P",
            ),
            y=alt.Y("gap_pp:Q", title="Computed − Lipper (pp)"),
            tooltip=[
                alt.Tooltip("name:N", title="Fund"),
                alt.Tooltip("gap_pp:Q", title="Gap (pp)", format="+.2f"),
                alt.Tooltip("december_log_excess:Q", title="December", format="+.3f"),
                alt.Tooltip("other_log_excess:Q", title="Other months", format="+.3f"),
            ],
        )
    )
    december_line = (
        alt.Chart(ten_year_line)
        .mark_line(color="#C2410C", strokeDash=[4, 4])
        .encode(x="december_log_excess:Q", y="gap_pp:Q")
    )
    december_chart = (december_points + december_line).properties(
        width=720,
        height=360,
        title="10-year gap against the December lag versus the S&P",
    )
    mo.vstack([level_note, cause_table, december_chart])
    return (cause_summary, cause_table, december_chart, gap_attribution, level_note, ten_year)


@app.cell
def _(gap_attribution, mo):
    index_like = gap_attribution.loc[
        gap_attribution["horizon"].eq("10y")
        & gap_attribution["name"].str.contains(
            r"S&P 500|500 Index|Index Fund", case=False, regex=True
        )
    ].sort_values("gap_pp")
    index_like_shown = index_like[
        ["name", "gap_pp", "december_log_excess", "other_log_excess", "worst_month", "worst_active"]
    ].copy()
    index_like_shown["gap_pp"] = index_like_shown["gap_pp"].round(2)
    index_like_shown["december_log_excess"] = index_like_shown["december_log_excess"].round(3)
    index_like_shown["other_log_excess"] = index_like_shown["other_log_excess"].round(3)
    index_like_shown["worst_active"] = (index_like_shown["worst_active"] * 100).round(2)
    index_like_shown = index_like_shown.rename(
        columns={
            "name": "Fund",
            "gap_pp": "Gap (pp)",
            "december_log_excess": "December log excess",
            "other_log_excess": "Other months log excess",
            "worst_month": "Worst month",
            "worst_active": "Worst month vs S&P (pp)",
        }
    )
    index_like_table = mo.ui.table(
        index_like_shown,
        label="S&P 500 and index funds, 10-year gap",
        selection=None,
        page_size=15,
    )
    repair_notes = {
        "US78472P1093": "20 Apr 2020 reverse split: history multiplied by 6. The date is inside the 10-year window only.",
        "US8085098551": "15 Aug 2025 split: history divided by 36.",
        "US1888501012": "12 May 2025 split: history divided by 100.",
        "US2562191062": "27 Oct 2025 split: history divided by 256.",
        "US2571321007": "12 Jul 2016: history doubled.",
        "US85749T7569": "20 Apr 2020: history rescaled to that day's S&P return.",
        "US00774Q8740": "29 Dec 2022: later total-return levels put back on the price scale.",
        "US3161841008": "Distribution days in 2015–2018 set to the S&P return.",
        "US38141W6205": "14 Dec 2021 and 12 Dec 2024 distributions set to the S&P return.",
        "US63872T4893": "23 Dec 2021 distribution set to the S&P return.",
        "US7839808240": "16 Dec 2021 distribution set to the S&P return.",
        "US8085098064": "16 Dec 2021 distribution set to the S&P return.",
        "US0263933063": "1 Dec 2025: one total-return print replaced.",
    }
    repairs = gap_attribution.loc[gap_attribution["isin"].isin(repair_notes)].copy()
    repairs["note"] = repairs["isin"].map(repair_notes)
    repairs = repairs.sort_values(["isin", "horizon"])
    repair_shown = repairs[
        ["name", "horizon", "gap_pp", "december_log_excess", "note"]
    ].copy()
    repair_shown["gap_pp"] = repair_shown["gap_pp"].round(2)
    repair_shown["december_log_excess"] = repair_shown["december_log_excess"].round(3)
    repair_shown = repair_shown.rename(
        columns={
            "name": "Fund",
            "horizon": "Horizon",
            "gap_pp": "Gap (pp)",
            "december_log_excess": "December log excess",
            "note": "What was changed",
        }
    )
    repair_table = mo.ui.table(
        repair_shown,
        label="Series that were rescaled by hand",
        selection=None,
        pagination=False,
    )
    mo.vstack([index_like_table, repair_table])
    return (index_like, index_like_shown, index_like_table, repair_shown, repair_table, repairs)


if __name__ == "__main__":
    app.run()
