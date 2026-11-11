# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "altair>=6.3.0",
#     "marimo>=0.25.2",
#     "numpy==2.5.4",
#     "openpyxl>=3.1.5",
#     "pandas>=3.0.6",
#     "statsmodels>=0.15.0",
#     "yfinance>=1.7.0",
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
    - **Alpha** is the monthly OLS intercept in percent; compared to Lipper `Alpha for {N} Years to Last Month End`.
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
        ALPHA_CLOSE_PP,
        DEFAULT_WORKBOOK_FILENAME,
        FUNDS_SHEET,
        alpha_lipper_report,
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
        ALPHA_CLOSE_PP,
        FUNDS_SHEET,
        alpha_lipper_report,
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

    The computed total return compounds the fund's own monthly total returns over the last 36, 60, or 120 months. It does not use the benchmark. The horizon return is the product of `(1 + monthly return)`, minus 1, in percent. Those daily returns come from `D-Timeseries final` after the distribution rebuild in `load-series-v2.py` (NAV plus cash distributions, kept when closer to Lipper).

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
    ### Where the remaining gaps come from

    After rebuilding total return from the published NAV and cash distributions, about **94–95%** of funds sit within 1 pp of Lipper on every horizon. The median gap is near zero. December no longer explains the cross-section (correlation with the December lag is about 0.1–0.3).

    The leftover gaps fall into a few small groups.

    **Horizon-specific series breaks.** John Hancock US Sector Rotation matches Lipper on 3y and 5y and sits about **−30 pp** on 10y only. AB Select US Equity and Nationwide BNY Mellon Dynamic Core are a few points high on 10y only. Something early in the series, or a one-off repair, moves the long window without touching the short ones.

    **Active funds with a smooth shortfall.** Morgan Stanley Permanence, Artisan Focus, Nationwide Fund, Magellan K6, and the GQG share classes sit several points below Lipper on 3y and 5y. Most of their active return is outside December. Expense ratio does not line up with these gaps.

    **Index ETFs with a small residual.** SPY, IVV, and SPDR Portfolio S&P 500 stay quiet in December and still miss Lipper by about 1–3 pp over 10 years. That is far smaller than the old distribution misses, but it is not gone.

    The tables below keep only funds whose absolute gap exceeds 1 pp. The chart plots those outliers against the non-December log excess versus the S&P.
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
        OUTLIER_GAP_PP,
        return_gap_attribution,
        return_gap_outlier_summary,
        return_gap_outliers,
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
    outlier_summary = return_gap_outlier_summary(gap_attribution)
    outlier_rows = return_gap_outliers(gap_attribution)
    outlier_summary_shown = outlier_summary.assign(
        within_share=lambda frame: (100 * frame["within_share"]).round(1),
        median_abs_gap_outliers=lambda frame: frame["median_abs_gap_outliers"].round(2),
        max_abs_gap_pp=lambda frame: frame["max_abs_gap_pp"].round(2),
        worst_gap_pp=lambda frame: frame["worst_gap_pp"].round(2),
        corr_gap_december=lambda frame: frame["corr_gap_december"].round(2),
        corr_gap_other=lambda frame: frame["corr_gap_other"].round(2),
    )[
        [
            "horizon",
            "funds",
            "n_within_threshold",
            "within_share",
            "n_outliers",
            "median_abs_gap_outliers",
            "max_abs_gap_pp",
            "worst_name",
            "worst_gap_pp",
            "corr_gap_december",
            "corr_gap_other",
        ]
    ].rename(
        columns={
            "horizon": "Horizon",
            "funds": "Funds",
            "n_within_threshold": f"Within {OUTLIER_GAP_PP:g} pp",
            "within_share": "Within share (%)",
            "n_outliers": "Outliers",
            "median_abs_gap_outliers": "Median |gap|, outliers (pp)",
            "max_abs_gap_pp": "Max |gap| (pp)",
            "worst_name": "Largest outlier",
            "worst_gap_pp": "Its gap (pp)",
            "corr_gap_december": "Corr. with December",
            "corr_gap_other": "Corr. with other months",
        }
    )
    outlier_summary_table = mo.ui.table(
        outlier_summary_shown,
        label=f"Funds still beyond {OUTLIER_GAP_PP:g} pp of Lipper",
        selection=None,
        pagination=False,
    )
    outlier_shown = outlier_rows[
        [
            "horizon",
            "name",
            "gap_pp",
            "december_log_excess",
            "other_log_excess",
            "worst_month",
            "worst_active",
            "expense",
        ]
    ].copy()
    outlier_shown["gap_pp"] = outlier_shown["gap_pp"].round(2)
    outlier_shown["december_log_excess"] = outlier_shown["december_log_excess"].round(3)
    outlier_shown["other_log_excess"] = outlier_shown["other_log_excess"].round(3)
    outlier_shown["worst_active"] = (outlier_shown["worst_active"] * 100).round(2)
    outlier_shown["expense"] = outlier_shown["expense"].round(2)
    outlier_shown = outlier_shown.rename(
        columns={
            "horizon": "Horizon",
            "name": "Fund",
            "gap_pp": "Gap (pp)",
            "december_log_excess": "December log excess",
            "other_log_excess": "Other months log excess",
            "worst_month": "Worst month",
            "worst_active": "Worst month vs S&P (pp)",
            "expense": "Expense (%)",
        }
    )
    outlier_table = mo.ui.table(
        outlier_shown,
        label="Remaining outliers by horizon",
        selection=None,
        page_size=15,
    )
    plot_outliers = outlier_rows.loc[outlier_rows["horizon"].eq("10y")].copy()
    if plot_outliers.empty:
        plot_outliers = outlier_rows.copy()
    outlier_chart = (
        alt.Chart(plot_outliers)
        .mark_circle(size=70, opacity=0.85)
        .encode(
            x=alt.X(
                "other_log_excess:Q",
                title="Sum of non-December log excess versus the S&P",
            ),
            y=alt.Y("gap_pp:Q", title="Computed − Lipper (pp)"),
            color=alt.Color("horizon:N", title="Horizon"),
            tooltip=[
                alt.Tooltip("name:N", title="Fund"),
                alt.Tooltip("horizon:N", title="Horizon"),
                alt.Tooltip("gap_pp:Q", title="Gap (pp)", format="+.2f"),
                alt.Tooltip("other_log_excess:Q", title="Other months", format="+.3f"),
                alt.Tooltip("december_log_excess:Q", title="December", format="+.3f"),
            ],
        )
        .properties(
            width=720,
            height=360,
            title="Remaining outliers against the non-December lag versus the S&P",
        )
    )
    mo.vstack([level_note, outlier_summary_table, outlier_table, outlier_chart])
    return (
        gap_attribution,
        level_note,
        outlier_chart,
        outlier_rows,
        outlier_shown,
        outlier_summary,
        outlier_summary_table,
        outlier_table,
    )


@app.cell
def _(gap_attribution, mo, outlier_rows):
    repair_notes = {
        "US78472P1093": "20 Apr 2020 reverse split: history multiplied by 6. Inside the 10-year window only.",
        "US8085098551": "15 Aug 2025 split: history divided by 36.",
        "US1888501012": "12 May 2025 split: history divided by 100.",
        "US2562191062": "27 Oct 2025 split: history divided by 256.",
        "US2571321007": "12 Jul 2016: history doubled.",
        "US85749T7569": "20 Apr 2020: history rescaled to that day's S&P return.",
        "US00774Q8740": "29 Dec 2022: later total-return levels put back on the price scale.",
        "US3161841008": "Distribution days in 2015–2018 set to the S&P return.",
        "US38141W6205": "14 Dec 2021 and 12 Dec 2024 distributions set to the S&P return.",
        "US63872T4893": "23 Dec 2021 distribution set to the S&P return.",
        "US0263933063": "1 Dec 2025: one total-return print replaced.",
    }
    repaired_outliers = outlier_rows.loc[outlier_rows["isin"].isin(repair_notes)].copy()
    repaired_outliers["note"] = repaired_outliers["isin"].map(repair_notes)
    repaired_outliers = repaired_outliers.sort_values(["abs_gap_pp"], ascending=False)
    repaired_shown = repaired_outliers[
        ["name", "horizon", "gap_pp", "other_log_excess", "note"]
    ].copy()
    repaired_shown["gap_pp"] = repaired_shown["gap_pp"].round(2)
    repaired_shown["other_log_excess"] = repaired_shown["other_log_excess"].round(3)
    repaired_shown = repaired_shown.rename(
        columns={
            "name": "Fund",
            "horizon": "Horizon",
            "gap_pp": "Gap (pp)",
            "other_log_excess": "Other months log excess",
            "note": "Manual repair still in the series",
        }
    )
    repaired_table = mo.ui.table(
        repaired_shown,
        label="Outliers that still carry a manual series repair",
        selection=None,
        pagination=False,
    )
    horizon_specific = (
        gap_attribution.pivot_table(
            index=["isin", "name"], columns="horizon", values="gap_pp", aggfunc="first"
        )
        .reset_index()
    )
    for column in ("3y", "5y", "10y"):
        if column not in horizon_specific.columns:
            horizon_specific[column] = float("nan")
    horizon_specific["max_abs"] = horizon_specific[["3y", "5y", "10y"]].abs().max(axis=1)
    horizon_specific = horizon_specific.loc[horizon_specific["max_abs"] > 1].copy()
    # Large on 10y, near zero on both short windows.
    only_10y = horizon_specific.loc[
        horizon_specific["10y"].abs().gt(2)
        & horizon_specific["3y"].abs().lt(0.5)
        & horizon_specific["5y"].abs().lt(0.5)
    ].sort_values("10y")
    only_10y_shown = only_10y[["name", "3y", "5y", "10y"]].copy()
    for column in ("3y", "5y", "10y"):
        only_10y_shown[column] = only_10y_shown[column].round(2)
    only_10y_shown = only_10y_shown.rename(
        columns={
            "name": "Fund",
            "3y": "3y gap (pp)",
            "5y": "5y gap (pp)",
            "10y": "10y gap (pp)",
        }
    )
    only_10y_table = mo.ui.table(
        only_10y_shown,
        label="Horizon-specific: large 10y gap, 3y and 5y within 0.5 pp",
        selection=None,
        pagination=False,
    )
    mo.vstack([only_10y_table, repaired_table])
    return (
        horizon_specific,
        only_10y,
        only_10y_shown,
        only_10y_table,
        repaired_outliers,
        repaired_shown,
        repaired_table,
        repair_notes,
    )


@app.cell(hide_code=True)
def _(ALPHA_CLOSE_PP, mo):
    mo.md(f"""
    ## Alpha

    The computed alpha is the intercept of the monthly fund-on-benchmark OLS, in **percent per month**. Lipper's column is `Alpha for {{N}} Years to Last Month End`, in the same units. The charts keep a fund when that column is filled and the cleaned series has every month of the horizon. The gap is computed minus Lipper. A fund is marked close when the absolute gap is within **{ALPHA_CLOSE_PP:g} pp** per month (the same band as the Lipper match tolerance).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Funds
    """)
    return


@app.cell
def _(ALPHA_CLOSE_PP, alpha_lipper_report, comparison, mo):
    alpha_report = alpha_lipper_report(comparison)
    alpha_summary = alpha_report.summary
    alpha_gap_bits = []
    for alpha_horizon_row in alpha_summary.itertuples(index=False):
        if (
            alpha_horizon_row.compared == 0
            or alpha_horizon_row.median_gap_pp != alpha_horizon_row.median_gap_pp
        ):
            continue
        if alpha_horizon_row.same_window == alpha_horizon_row.compared:
            alpha_window_note = (
                f"{alpha_horizon_row.window_start} to {alpha_horizon_row.window_end}"
            )
        else:
            alpha_window_note = (
                f"{alpha_horizon_row.window_start} to {alpha_horizon_row.window_end} "
                f"for {int(alpha_horizon_row.same_window)} of {int(alpha_horizon_row.compared)} funds"
            )
        alpha_gap_bits.append(
            f"- **{alpha_horizon_row.horizon}** ({alpha_window_note}): "
            f"median gap **{alpha_horizon_row.median_gap_pp:+.3f} pp/month** "
            f"across {alpha_horizon_row.compared:,} funds, "
            f"{alpha_horizon_row.within_close_share:.0%} within {ALPHA_CLOSE_PP:g} pp, "
            f"correlation {alpha_horizon_row.correlation:.3f}"
        )
    alpha_below = (alpha_summary["median_gap_pp"] < 0).all()
    alpha_direction = (
        "The computed alpha sits below Lipper on every horizon."
        if alpha_below
        else "The median alpha gap changes sign across horizons."
    )
    alpha_coverage = mo.md(alpha_direction + "\n\n" + "\n".join(alpha_gap_bits))
    alpha_shown = alpha_summary.assign(
        median_gap_pp=lambda frame: frame["median_gap_pp"].round(3),
        median_abs_gap_pp=lambda frame: frame["median_abs_gap_pp"].round(3),
        max_abs_gap_pp=lambda frame: frame["max_abs_gap_pp"].round(3),
        within_close_pct=lambda frame: (frame["within_close_share"] * 100).round(1),
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
            "within_close_pct",
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
            "median_gap_pp": "Median gap (pp/mo)",
            "median_abs_gap_pp": "Median |gap| (pp/mo)",
            "max_abs_gap_pp": "Largest |gap| (pp/mo)",
            "within_close": f"Within {ALPHA_CLOSE_PP:g} pp",
            "within_close_pct": f"Share within {ALPHA_CLOSE_PP:g} pp",
            "below_lipper_pct": "Share below Lipper",
            "correlation": "Correlation",
        }
    )
    alpha_summary_table = mo.ui.table(
        alpha_shown,
        label="Alpha by horizon",
        selection=None,
        pagination=False,
    )
    mo.vstack([alpha_coverage, alpha_summary_table])
    return (alpha_report,)


@app.cell
def _(ALPHA_CLOSE_PP, alpha_report, alt, mo, pd):
    alpha_compared = alpha_report.comparable.copy()
    alpha_compared["agreement"] = alpha_compared["within_close"].map(
        {
            True: f"within {ALPHA_CLOSE_PP:g} pp",
            False: f"beyond {ALPHA_CLOSE_PP:g} pp",
        }
    )
    alpha_agreement_scale = alt.Scale(
        domain=[f"within {ALPHA_CLOSE_PP:g} pp", f"beyond {ALPHA_CLOSE_PP:g} pp"],
        range=["#1D4E89", "#C2410C"],
    )
    alpha_scatters = []
    alpha_gaps = []
    for alpha_horizon_name in ["3y", "5y", "10y"]:
        alpha_group = alpha_compared.loc[alpha_compared["horizon"].eq(alpha_horizon_name)]
        if alpha_group.empty:
            continue
        alpha_low = float(
            min(
                alpha_group["alpha_pct_per_month"].min(),
                alpha_group["lipper_alpha_pct_per_month"].min(),
            )
        )
        alpha_high = float(
            max(
                alpha_group["alpha_pct_per_month"].max(),
                alpha_group["lipper_alpha_pct_per_month"].max(),
            )
        )
        alpha_identity_frame = pd.DataFrame(
            {
                "alpha_pct_per_month": [alpha_low, alpha_high],
                "lipper_alpha_pct_per_month": [alpha_low, alpha_high],
            }
        )
        alpha_points = (
            alt.Chart(alpha_group)
            .mark_circle(size=36, opacity=0.75)
            .encode(
                x=alt.X("alpha_pct_per_month:Q", title="Computed (% / month)"),
                y=alt.Y("lipper_alpha_pct_per_month:Q", title="Lipper (% / month)"),
                color=alt.Color(
                    "agreement:N",
                    title=None,
                    scale=alpha_agreement_scale,
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("name:N", title="Fund"),
                    alt.Tooltip("isin:N", title="ISIN"),
                    alt.Tooltip("alpha_pct_per_month:Q", title="Computed", format=".3f"),
                    alt.Tooltip(
                        "lipper_alpha_pct_per_month:Q", title="Lipper", format=".3f"
                    ),
                    alt.Tooltip(
                        "delta_alpha_pp_per_month:Q", title="Gap (pp)", format="+.3f"
                    ),
                ],
            )
        )
        alpha_identity = (
            alt.Chart(alpha_identity_frame)
            .mark_line(strokeDash=[4, 4], color="#78716C")
            .encode(x="alpha_pct_per_month:Q", y="lipper_alpha_pct_per_month:Q")
        )
        alpha_scatters.append(
            (alpha_points + alpha_identity).properties(
                width=240, height=240, title=alpha_horizon_name
            )
        )
        alpha_bars = (
            alt.Chart(alpha_group)
            .mark_bar(color="#1D4E89")
            .encode(
                x=alt.X(
                    "delta_alpha_pp_per_month:Q",
                    bin=alt.Bin(maxbins=24),
                    title="Computed − Lipper (pp / month)",
                ),
                y=alt.Y("count()", title="Funds"),
            )
        )
        alpha_zero_rule = (
            alt.Chart(pd.DataFrame({"delta_alpha_pp_per_month": [0.0]}))
            .mark_rule(color="#C2410C", strokeWidth=1.5)
            .encode(x="delta_alpha_pp_per_month:Q")
        )
        alpha_gaps.append(
            (alpha_bars + alpha_zero_rule).properties(
                width=240, height=160, title=alpha_horizon_name
            )
        )
    alpha_scatter_by_horizon = alt.hconcat(*alpha_scatters).resolve_scale(color="shared")
    alpha_gap_by_horizon = alt.hconcat(*alpha_gaps)
    mo.vstack(
        [
            mo.md(
                "Each point is one fund. The dashed line is equality. "
                "The orange line on the histograms is a gap of zero."
            ),
            alpha_scatter_by_horizon,
            alpha_gap_by_horizon,
        ]
    )
    return (alpha_compared, alpha_gap_by_horizon, alpha_scatter_by_horizon)


@app.cell
def _(mo):
    alpha_horizon = mo.ui.dropdown(
        options=["all", "3y", "5y", "10y"],
        value="all",
        label="Horizon",
    )
    alpha_horizon
    return (alpha_horizon,)


@app.cell
def _(alpha_compared, alpha_horizon, alpha_report, mo):
    picked_alpha_horizon = alpha_horizon.value
    alpha_detail = (
        alpha_compared
        if picked_alpha_horizon == "all"
        else alpha_compared.loc[alpha_compared["horizon"].eq(picked_alpha_horizon)]
    )
    alpha_detail = alpha_detail.sort_values(
        "abs_delta_alpha_pp_per_month", ascending=False
    )
    alpha_detail_shown = alpha_detail[
        [
            "name",
            "isin",
            "horizon",
            "window_start",
            "window_end",
            "months",
            "alpha_pct_per_month",
            "lipper_alpha_pct_per_month",
            "delta_alpha_pp_per_month",
            "agreement",
        ]
    ].copy()
    for alpha_col in (
        "alpha_pct_per_month",
        "lipper_alpha_pct_per_month",
        "delta_alpha_pp_per_month",
    ):
        alpha_detail_shown[alpha_col] = alpha_detail_shown[alpha_col].round(3)
    alpha_detail_shown["months"] = alpha_detail_shown["months"].astype(int)
    alpha_detail_shown = alpha_detail_shown.rename(
        columns={
            "name": "Fund",
            "isin": "ISIN",
            "horizon": "Horizon",
            "window_start": "Window start",
            "window_end": "Window end",
            "months": "Months",
            "alpha_pct_per_month": "Computed (% / mo)",
            "lipper_alpha_pct_per_month": "Lipper (% / mo)",
            "delta_alpha_pp_per_month": "Gap (pp / mo)",
            "agreement": "Agreement",
        }
    )
    alpha_detail_table = mo.ui.table(
        alpha_detail_shown,
        label="Largest alpha gaps first",
        selection=None,
        page_size=15,
    )
    alpha_short = alpha_report.short_window
    alpha_short_shown = None
    if alpha_short.empty:
        alpha_short_note = mo.md(
            "Every fund with a Lipper alpha has the full month count for that horizon."
        )
        alpha_short_table = None
    else:
        alpha_short_shown = alpha_short[
            [
                "name",
                "isin",
                "horizon",
                "months",
                "window_start",
                "window_end",
                "alpha_pct_per_month",
                "lipper_alpha_pct_per_month",
                "delta_alpha_pp_per_month",
            ]
        ].copy()
        for alpha_col in (
            "alpha_pct_per_month",
            "lipper_alpha_pct_per_month",
            "delta_alpha_pp_per_month",
        ):
            alpha_short_shown[alpha_col] = alpha_short_shown[alpha_col].round(3)
        alpha_short_shown["months"] = alpha_short_shown["months"].astype(int)
        alpha_short_shown = alpha_short_shown.rename(
            columns={
                "name": "Fund",
                "isin": "ISIN",
                "horizon": "Horizon",
                "months": "Months",
                "window_start": "Window start",
                "window_end": "Window end",
                "alpha_pct_per_month": "Computed (% / mo)",
                "lipper_alpha_pct_per_month": "Lipper (% / mo)",
                "delta_alpha_pp_per_month": "Gap (pp / mo)",
            }
        )
        alpha_short_note = mo.md(
            "These funds have a Lipper alpha and fewer months than the horizon, so they are left off the charts."
        )
        alpha_short_table = mo.ui.table(
            alpha_short_shown,
            label="Shorter than the horizon",
            selection=None,
            pagination=False,
        )
    alpha_blocks = [alpha_detail_table, alpha_short_note]
    if alpha_short_table is not None:
        alpha_blocks.append(alpha_short_table)
    mo.vstack(alpha_blocks)
    return (
        alpha_detail,
        alpha_detail_shown,
        alpha_detail_table,
        alpha_short,
        alpha_short_note,
        alpha_short_shown,
        alpha_short_table,
        picked_alpha_horizon,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Why the alpha gaps appear

    After the total-return rebuild, the **median** fund is close to Lipper on alpha (a few hundredths of a pp per month),
    but a minority sit far below Lipper on monthly alpha while total return still matches. That tail is not a missing-distribution problem.

    **Alpha and beta move together.** The computed alpha gap correlates strongly with the beta gap (about −0.7 on 3y).
    With similar mean fund and benchmark returns, OLS implies α ≈ ȳ − β·x̄, so a lower Lipper beta mechanically implies a higher Lipper alpha.

    **On the large-gap tail, Lipper’s risk stats look misaligned with `.SPXTR`.** For those funds, Lipper relative performance also diverges while absolute TR matches,
    and our beta lines up with **Yahoo** (and issuer factsheets vs S&P 500) while Lipper beta does not.

    **Not the main drivers for the typical fund:** Jensen alpha on excess returns over T-bills (beta barely moves), or treating Lipper alpha as annualized while ours is monthly
    (when beta is close, alpha is usually close too).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Independent check (Yahoo risk statistics)

    Yahoo publishes Morningstar-style **annualized** alpha and beta in `fundPerformance.riskOverviewStatistics`
    (3y, 5y, 10y). We fetch them by `openfigi_market_id`, cache under `cache/yahoo-risk-stats.json`, and compare:

    - **Ours:** monthly OLS intercept × 12 vs `.SPXTR` (annualized %)
    - **Yahoo:** annualized % from Yahoo
    - **Lipper:** Lipper monthly alpha × 12

    Yahoo’s index is not guaranteed to be S&P 500 TR for every fund. Use Yahoo as a cross-check on **large Lipper disagreements**, not as a wholesale Lipper replacement.
    """)
    return


@app.cell
def _(comparison, funds):
    from helpers.timeseries_functions.yahoo_fund_risk_stats import (
        LARGE_LIPPER_ALPHA_PP_PER_MONTH,
        refresh_yahoo_risk_stats_cache,
        tickers_from_funds_for_comparison,
        yahoo_alpha_beta_comparison,
        yahoo_vs_lipper_summary,
    )

    yahoo_tickers = tickers_from_funds_for_comparison(funds, comparison)
    yahoo_cache = refresh_yahoo_risk_stats_cache(yahoo_tickers, pause_seconds=0.35)
    return (
        LARGE_LIPPER_ALPHA_PP_PER_MONTH,
        refresh_yahoo_risk_stats_cache,
        tickers_from_funds_for_comparison,
        yahoo_alpha_beta_comparison,
        yahoo_vs_lipper_summary,
        yahoo_cache,
        yahoo_tickers,
    )


@app.cell
def _(
    LARGE_LIPPER_ALPHA_PP_PER_MONTH,
    alpha_report,
    comparison,
    funds,
    mo,
    pd,
    yahoo_alpha_beta_comparison,
    yahoo_cache,
    yahoo_tickers,
    yahoo_vs_lipper_summary,
):
    yahoo_compare = yahoo_alpha_beta_comparison(comparison, funds, yahoo_cache)
    yahoo_summary = yahoo_vs_lipper_summary(yahoo_compare)
    n_tickers = len(yahoo_tickers)
    n_rows = len(yahoo_compare)
    fund_count = int(yahoo_compare["isin"].nunique()) if n_rows else 0
    comparable_n = len(alpha_report.comparable)
    yahoo_coverage = mo.md(
        f"Yahoo returned risk statistics for **{n_rows:,}** fund-horizon rows "
        f"({fund_count:,} funds) after looking up **{n_tickers:,}** tickers "
        f"among **{comparable_n:,}** Lipper-comparable fund-horizons."
    )
    yahoo_summary_shown = yahoo_summary.assign(
        median_abs_gap_alpha_ours_yahoo_ann=lambda frame: frame[
            "median_abs_gap_alpha_ours_yahoo_ann"
        ].round(2),
        median_abs_gap_alpha_ours_lipper_ann=lambda frame: frame[
            "median_abs_gap_alpha_ours_lipper_ann"
        ].round(2),
        median_abs_gap_beta_ours_yahoo=lambda frame: frame[
            "median_abs_gap_beta_ours_yahoo"
        ].round(3),
        median_abs_gap_beta_ours_lipper=lambda frame: frame[
            "median_abs_gap_beta_ours_lipper"
        ].round(3),
        share_yahoo_closer_alpha=lambda frame: (frame["share_yahoo_closer_alpha"] * 100).round(
            1
        ),
        share_yahoo_closer_beta=lambda frame: (frame["share_yahoo_closer_beta"] * 100).round(1),
        share_yahoo_agrees_beta_when_large_alpha_gap=lambda frame: (
            frame["share_yahoo_agrees_beta_when_large_alpha_gap"] * 100
        ).round(1),
    ).rename(
        columns={
            "horizon": "Horizon",
            "n_with_yahoo": "With Yahoo",
            "median_abs_gap_alpha_ours_yahoo_ann": "Med |α ours−Yahoo| (ann %)",
            "median_abs_gap_alpha_ours_lipper_ann": "Med |α ours−Lipper| (ann %)",
            "median_abs_gap_beta_ours_yahoo": "Med |β ours−Yahoo|",
            "median_abs_gap_beta_ours_lipper": "Med |β ours−Lipper|",
            "share_yahoo_closer_alpha": "Yahoo closer on α (%)",
            "share_yahoo_closer_beta": "Yahoo closer on β (%)",
            "n_large_lipper_alpha_gap": f"|Lipper α gap| > {LARGE_LIPPER_ALPHA_PP_PER_MONTH:g} pp/mo",
            "share_yahoo_agrees_beta_when_large_alpha_gap": "β agree w/ Yahoo (%)",
        }
    )
    yahoo_summary_table = mo.ui.table(
        yahoo_summary_shown,
        label="Yahoo vs Lipper (closer to our OLS)",
        selection=None,
        pagination=False,
    )
    yahoo_verdict_bits = []
    if not yahoo_summary.empty:
        for yahoo_row in yahoo_summary.itertuples(index=False):
            if yahoo_row.n_with_yahoo == 0:
                continue
            agrees = yahoo_row.share_yahoo_agrees_beta_when_large_alpha_gap
            agrees_text = (
                f"{agrees:.0%} with |our β − Yahoo β| ≤ 0.15"
                if agrees == agrees
                else "n/a"
            )
            yahoo_verdict_bits.append(
                f"- **{yahoo_row.horizon}**: Yahoo closer than Lipper on α for only "
                f"**{yahoo_row.share_yahoo_closer_alpha:.0%}** of all funds "
                f"(med |ours−Yahoo| α {yahoo_row.median_abs_gap_alpha_ours_yahoo_ann:.2f} ann % vs "
                f"|ours−Lipper| {yahoo_row.median_abs_gap_alpha_ours_lipper_ann:.2f}). "
                f"Among large Lipper α gaps (n={int(yahoo_row.n_large_lipper_alpha_gap)}): "
                f"Yahoo β agrees on {agrees_text}."
            )
    yahoo_verdict = mo.md(
        (
            "### Conclusion from the Yahoo check\n\n"
            "**Lipper α/β are fine for most funds.** Across the full sample, median |ours−Lipper| "
            "is smaller than |ours−Yahoo| for both alpha and beta, so Yahoo is **not** a better "
            "default Lipper replacement (different windows / index assignment).\n\n"
            "**The large alpha gaps are a concentrated tail.** There Yahoo backs **our** SPXTR OLS—"
            "especially beta—while Lipper often shows a lower beta and the wrong-signed alpha. "
            "Most of those names still match Lipper on total return, so this is a risk-stat issue, "
            "not a broken TR series.\n\n"
            "**Practical use:** keep Lipper for total return; for α/β validation trust the OLS "
            "(and Yahoo as a cross-check) when Lipper diverges sharply; do not discard Lipper α/β "
            "for the typical fund.\n\n"
            + "\n".join(yahoo_verdict_bits)
        )
        if yahoo_verdict_bits
        else "No Yahoo risk statistics were available for this run."
    )
    mo.vstack([yahoo_coverage, yahoo_summary_table, yahoo_verdict])
    return (yahoo_compare, yahoo_summary, yahoo_verdict)


@app.cell
def _(alt, mo, pd, yahoo_compare):
    yahoo_3y = yahoo_compare.loc[yahoo_compare["horizon"].eq("3y")].copy()
    if yahoo_3y.empty:
        yahoo_scatter_panel = mo.md("No 3y Yahoo risk statistics to chart.")
    else:
        yahoo_3y["lipper_gap_band"] = yahoo_3y["lipper_alpha_large_gap"].map(
            {
                True: "Large Lipper α gap",
                False: "Other",
            }
        )
        _alpha_low = float(
            min(yahoo_3y["alpha_ann_pct"].min(), yahoo_3y["yahoo_alpha_ann_pct"].min())
        )
        _alpha_high = float(
            max(yahoo_3y["alpha_ann_pct"].max(), yahoo_3y["yahoo_alpha_ann_pct"].max())
        )
        _alpha_identity = pd.DataFrame(
            {
                "alpha_ann_pct": [_alpha_low, _alpha_high],
                "yahoo_alpha_ann_pct": [_alpha_low, _alpha_high],
            }
        )
        _yahoo_alpha_points = (
            alt.Chart(yahoo_3y)
            .mark_circle(size=40, opacity=0.8)
            .encode(
                x=alt.X("alpha_ann_pct:Q", title="Our α (annualized %)"),
                y=alt.Y("yahoo_alpha_ann_pct:Q", title="Yahoo α (annualized %)"),
                color=alt.Color(
                    "lipper_gap_band:N",
                    title="Lipper α gap",
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("name:N", title="Fund"),
                    alt.Tooltip("yahoo_ticker:N", title="Ticker"),
                    alt.Tooltip("alpha_ann_pct:Q", title="Our α", format=".2f"),
                    alt.Tooltip("yahoo_alpha_ann_pct:Q", title="Yahoo α", format=".2f"),
                    alt.Tooltip("lipper_alpha_ann_pct:Q", title="Lipper α", format=".2f"),
                    alt.Tooltip("delta_alpha_pp_per_month:Q", title="Δα vs Lipper (pp/mo)", format="+.3f"),
                ],
            )
        )
        _yahoo_alpha_identity = (
            alt.Chart(_alpha_identity)
            .mark_line(strokeDash=[4, 4], color="#78716C")
            .encode(x="alpha_ann_pct:Q", y="yahoo_alpha_ann_pct:Q")
        )
        _yahoo_alpha_scatter = (_yahoo_alpha_points + _yahoo_alpha_identity).properties(
            width=300, height=280, title="3y annualized α: our OLS vs Yahoo"
        )
        _beta_low = float(min(yahoo_3y["beta"].min(), yahoo_3y["yahoo_beta"].min()))
        _beta_high = float(max(yahoo_3y["beta"].max(), yahoo_3y["yahoo_beta"].max()))
        _beta_identity = pd.DataFrame(
            {
                "beta": [_beta_low, _beta_high],
                "yahoo_beta": [_beta_low, _beta_high],
            }
        )
        _yahoo_beta_points = (
            alt.Chart(yahoo_3y)
            .mark_circle(size=40, opacity=0.8)
            .encode(
                x=alt.X("beta:Q", title="Our β vs SPXTR"),
                y=alt.Y("yahoo_beta:Q", title="Yahoo β"),
                color=alt.Color(
                    "lipper_gap_band:N",
                    title="Lipper α gap",
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=[
                    alt.Tooltip("name:N", title="Fund"),
                    alt.Tooltip("beta:Q", title="Our β", format=".3f"),
                    alt.Tooltip("yahoo_beta:Q", title="Yahoo β", format=".3f"),
                    alt.Tooltip("lipper_beta:Q", title="Lipper β", format=".3f"),
                    alt.Tooltip("delta_beta:Q", title="Δβ vs Lipper", format="+.3f"),
                ],
            )
        )
        _yahoo_beta_identity = (
            alt.Chart(_beta_identity)
            .mark_line(strokeDash=[4, 4], color="#78716C")
            .encode(x="beta:Q", y="yahoo_beta:Q")
        )
        _yahoo_beta_scatter = (_yahoo_beta_points + _yahoo_beta_identity).properties(
            width=300, height=280, title="3y β: our OLS vs Yahoo"
        )
        yahoo_scatter_panel = mo.vstack(
            [
                mo.md(
                    "Points on the dashed line match between our SPXTR regression and Yahoo. "
                    "Orange labels are funds where Lipper α differs from ours by more than 0.10 pp/month."
                ),
                alt.hconcat(_yahoo_alpha_scatter, _yahoo_beta_scatter).resolve_scale(
                    color="shared"
                ),
            ]
        )
    yahoo_scatter_panel
    return (yahoo_3y,)


@app.cell
def _(mo, yahoo_compare):
    yahoo_outliers_shown = (
        yahoo_compare.sort_values("abs_delta_alpha_pp_per_month", ascending=False)
        .head(30)[
            [
                "name",
                "isin",
                "horizon",
                "yahoo_ticker",
                "alpha_ann_pct",
                "yahoo_alpha_ann_pct",
                "lipper_alpha_ann_pct",
                "beta",
                "yahoo_beta",
                "lipper_beta",
                "delta_alpha_pp_per_month",
                "delta_beta",
            ]
        ]
        .copy()
    )
    for _col in (
        "alpha_ann_pct",
        "yahoo_alpha_ann_pct",
        "lipper_alpha_ann_pct",
        "delta_alpha_pp_per_month",
    ):
        yahoo_outliers_shown[_col] = yahoo_outliers_shown[_col].round(2)
    for _col in ("beta", "yahoo_beta", "lipper_beta", "delta_beta"):
        yahoo_outliers_shown[_col] = yahoo_outliers_shown[_col].round(3)
    yahoo_outliers_shown = yahoo_outliers_shown.rename(
        columns={
            "name": "Fund",
            "isin": "ISIN",
            "horizon": "Horizon",
            "yahoo_ticker": "Yahoo ticker",
            "alpha_ann_pct": "Our α (ann %)",
            "yahoo_alpha_ann_pct": "Yahoo α (ann %)",
            "lipper_alpha_ann_pct": "Lipper α (ann %)",
            "beta": "Our β",
            "yahoo_beta": "Yahoo β",
            "lipper_beta": "Lipper β",
            "delta_alpha_pp_per_month": "Δα vs Lipper (pp/mo)",
            "delta_beta": "Δβ vs Lipper",
        }
    )
    yahoo_outliers_table = mo.ui.table(
        yahoo_outliers_shown,
        label="Largest Lipper alpha gaps (with Yahoo)",
        selection=None,
        page_size=15,
    )
    mo.vstack([yahoo_outliers_table])
    return (yahoo_outliers_table,)


if __name__ == "__main__":
    app.run()
