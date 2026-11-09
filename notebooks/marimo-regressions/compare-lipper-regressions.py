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

    Load `output-data/v2-d-timeseries-corrected.xlsx` and `output-data/v2-d-timeseries-final.xlsx`.
    For each fund in `output-data/v2-funds-final.xlsx`, compound daily total returns to calendar
    months, regress the fund on its Lipper reference benchmark over 3, 5, and 10 years, and
    compare alpha, beta, R², and annualized tracking error with Lipper’s precomputed Funds columns.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Method

    - Daily `… TR %` columns only. Month return compounds within the calendar month.
    - Benchmark mapping: `.SPXTR` → `S&P 500 TR %`, `.INX` → `S&P 500 C Price %`.
    - OLS: fund monthly return on benchmark monthly return (no risk-free subtraction).
    - Lipper alpha is percent per month; tracking error is annualized percent.
    - **Total return** compounds fund monthly returns over the horizon (%); compared to Lipper `{N} Year Performance to Last Month End`.
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
        DEFAULT_CORRECTED_FILENAME,
        DEFAULT_FINAL_FILENAME,
        DEFAULT_FUNDS_FILENAME,
        compare_daily_workbooks_to_lipper,
        find_output_data_file,
        fit_monthly_regression,
        fund_lipper_match_summary,
        match_rate_by_horizon,
        monthly_scatter_frame,
    )

    funds_path = find_output_data_file(DEFAULT_FUNDS_FILENAME)
    corrected_path = find_output_data_file(DEFAULT_CORRECTED_FILENAME)
    final_path = find_output_data_file(DEFAULT_FINAL_FILENAME)
    comparison, monthly_panels = compare_daily_workbooks_to_lipper(
        corrected_path=corrected_path,
        final_path=final_path,
    )
    funds = pd.read_excel(funds_path, engine="openpyxl")
    return (
        alt,
        comparison,
        corrected_path,
        final_path,
        fit_monthly_regression,
        fund_lipper_match_summary,
        funds,
        funds_path,
        match_rate_by_horizon,
        monthly_panels,
        monthly_scatter_frame,
        pd,
    )


@app.cell
def _(comparison, corrected_path, final_path, funds, funds_path, mo, pd):
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
    summary = mo.md(
        f"- **Funds:** `{funds_path}` ({len(funds):,} rows) \n"
        f"- **Corrected daily series:** `{corrected_path}` \n"
        f"- **Original daily series:** `{final_path}` \n"
        f"- **Comparable regressions:** {comparable:,} funds with a mapped benchmark on the sheet \n"
        f"- **Regression window ends:** {last_month} \n"
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

    One row per fund, horizon, and daily-series version (`corrected` or `final`).
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
    ## One fund: monthly scatter (corrected series)

    Pick a fund and horizon. Points are monthly total returns; the line is the OLS fit.
    """)
    return


@app.cell
def _(comparison, mo, pd):
    pickable = (
        comparison.loc[
            comparison["status"].eq("ok") & comparison["series_source"].eq("corrected")
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
        & comparison["series_source"].eq("corrected")
        & comparison["horizon"].eq(horizon)
    ]
    mo.stop(not isin or row.empty, mo.md("Choose a fund with a completed regression."))
    row = row.iloc[0]
    bench_header = row["benchmark_header"]
    monthly = monthly_panels["corrected"]
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
    lipper_beta = row["lipper_beta"]
    lipper_beta_text = (
        f"{float(lipper_beta):.3f}" if pd.notna(lipper_beta) else "n/a"
    )
    chart = (points + rule).properties(
        width=720,
        height=380,
        title=alt.Title(
            f"{row['name']}",
            subtitle=(
                f"{horizon} OLS: α = {fit.alpha_pct_per_month:+.3f}%/mo, "
                f"β = {fit.beta:.3f}, R² = {fit.r_squared:.3f} "
                f"(Lipper β = {lipper_beta_text})"
            ),
        ),
    )
    chart
    return bench_header, chart, fit, horizon, horizon_months, isin, line, n_months, points, row, rule, scatter


if __name__ == "__main__":
    app.run()
