# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo>=0.25.2",
#     "numpy==2.5.4",
#     "openpyxl>=3.1.5",
#     "pandas>=3.0.6",
#     "statsmodels>=0.15.0",
# ]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Daily consolidation regressions")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Daily consolidation regressions

    Load a funds workbook (default `output-data/v2-funds-normalized-cleaned.xlsx`),
    set the **Analysis period** parameters, click **Run regressions**, then view
    per-fund daily OLS on the benchmark and **Consolidated statistics by group**
  (same logic as the Consolidation tab in the formatted reference workbook).
    """)
    return


@app.cell
def _(mo):
    get_regression_results, set_regression_results = mo.state(None)
    return get_regression_results, set_regression_results


@app.cell
def _(mo):
    import pathlib
    import sys

    import pandas as pd

    start = pathlib.Path.cwd().resolve()
    repo_root = None
    for directory in [start, *start.parents]:
        if (directory / "helpers").is_dir():
            repo_root = directory
            root = str(directory)
            if root not in sys.path:
                sys.path.insert(0, root)
            break
    else:
        raise FileNotFoundError("Could not find helpers/")

    from helpers.timeseries_functions.consolidate_daily_fund_regressions import (
        DEFAULT_BENCHMARK_NAME,
        DEFAULT_TRADING_DAYS_PER_YEAR,
        RETURN_SERIES_CHOICES,
        build_consolidated_group_stats,
        build_fund_regression_table,
        format_table_figures,
        list_benchmark_name_choices,
        load_daily_panel_and_catalog,
        resolve_analysis_parameters,
    )
    from helpers.timeseries_functions.regress_daily_to_benchmark import (
        DEFAULT_WORKBOOK_FILENAME,
        LIPPER_AS_OF,
        find_output_data_file,
    )

    def output_workbook_choices(root: pathlib.Path) -> list[str]:
        folder = root / "output-data"
        if not folder.is_dir():
            return []
        return sorted(path.name for path in folder.glob("*.xlsx"))

    def parse_optional_date(text: str) -> pd.Timestamp | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None
        return pd.Timestamp(pd.to_datetime(cleaned, dayfirst=True)).normalize()

    is_script_mode = mo.app_meta().mode == "script"
    return (
        DEFAULT_BENCHMARK_NAME,
        DEFAULT_TRADING_DAYS_PER_YEAR,
        DEFAULT_WORKBOOK_FILENAME,
        LIPPER_AS_OF,
        RETURN_SERIES_CHOICES,
        build_consolidated_group_stats,
        build_fund_regression_table,
        format_table_figures,
        find_output_data_file,
        is_script_mode,
        list_benchmark_name_choices,
        load_daily_panel_and_catalog,
        output_workbook_choices,
        parse_optional_date,
        pd,
        repo_root,
        resolve_analysis_parameters,
    )


@app.cell
def _(
    DEFAULT_WORKBOOK_FILENAME,
    mo,
    output_workbook_choices,
    repo_root,
):
    choices = output_workbook_choices(repo_root)
    default_name = (
        DEFAULT_WORKBOOK_FILENAME
        if DEFAULT_WORKBOOK_FILENAME in choices
        else (choices[0] if choices else "")
    )
    workbook_dropdown = mo.ui.dropdown(
        options=choices,
        value=default_name,
        label="Input workbook (output-data/)",
        full_width=True,
    )
    workbook_dropdown
    return (workbook_dropdown,)


@app.cell
def _(
    DEFAULT_WORKBOOK_FILENAME,
    find_output_data_file,
    list_benchmark_name_choices,
    load_daily_panel_and_catalog,
    repo_root,
    resolve_analysis_parameters,
    workbook_dropdown,
):
    workbook_name = workbook_dropdown.value
    workbook_path = (
        repo_root / "output-data" / workbook_name
        if workbook_name
        else find_output_data_file(DEFAULT_WORKBOOK_FILENAME)
    )
    daily_panel, catalog = load_daily_panel_and_catalog(workbook_path)
    default_params = resolve_analysis_parameters(daily_panel, catalog)
    benchmark_choices = list_benchmark_name_choices(catalog)
    return benchmark_choices, catalog, daily_panel, default_params, workbook_path


@app.cell
def _(default_params, mo):
    fmt = "%d/%m/%Y"
    return (fmt,)


@app.cell
def _(
    DEFAULT_BENCHMARK_NAME,
    LIPPER_AS_OF,
    RETURN_SERIES_CHOICES,
    benchmark_choices,
    default_params,
    fmt,
    mo,
):
    mo.md(
        f"""
        ## Analysis period

        Lipper As Of (end cap): **{LIPPER_AS_OF.date()}**. Override fields — clear to reset · dates inclusive.
        """
    )
    end_override = mo.ui.text(
        value=default_params.end_date.strftime(fmt),
        label="End date override (DD/MM/YYYY)",
        full_width=True,
    )
    start_override = mo.ui.text(
        value=default_params.start_date.strftime(fmt),
        label="Start date override (DD/MM/YYYY)",
        full_width=True,
    )
    return_series_picker = mo.ui.dropdown(
        options=list(RETURN_SERIES_CHOICES),
        value=default_params.return_series,
        label="Return series",
    )
    benchmark_picker = mo.ui.dropdown(
        options=benchmark_choices,
        value=(
            default_params.benchmark_name
            if default_params.benchmark_name in benchmark_choices
            else DEFAULT_BENCHMARK_NAME
        ),
        label="Benchmark series",
        full_width=True,
    )
    mo.vstack(
        [
            end_override,
            start_override,
            return_series_picker,
            benchmark_picker,
        ]
    )
    return benchmark_picker, end_override, return_series_picker, start_override


@app.cell
def _(
    DEFAULT_BENCHMARK_NAME,
    benchmark_picker,
    catalog,
    daily_panel,
    default_params,
    end_override,
    fmt,
    parse_optional_date,
    pd,
    resolve_analysis_parameters,
    return_series_picker,
    start_override,
):
    params = resolve_analysis_parameters(
        daily_panel,
        catalog,
        end_override=parse_optional_date(end_override.value),
        start_override=parse_optional_date(start_override.value),
        return_series=return_series_picker.value,
        benchmark_name=benchmark_picker.value,
    )
    used_end = params.end_date.strftime(fmt)
    used_start = params.start_date.strftime(fmt)
    end_override_display = end_override.value.strip() or used_end
    start_override_display = start_override.value.strip() or used_start
    defaults_only = default_params
    param_rows = [
        {
            "Parameter": "End date",
            "Default": defaults_only.end_date.strftime("%d/%m/%Y"),
            "Override": end_override_display,
            "Used": used_end,
        },
        {
            "Parameter": "Start date",
            "Default": defaults_only.start_date.strftime("%d/%m/%Y"),
            "Override": start_override_display,
            "Used": used_start,
        },
        {
            "Parameter": "Trading days in window",
            "Default": "*calculated*",
            "Override": "",
            "Used": str(params.trading_days_in_window),
        },
        {
            "Parameter": "Return series",
            "Default": "Total return",
            "Override": (
                return_series_picker.value
                if return_series_picker.value != "Total return"
                else ""
            ),
            "Used": params.return_series,
        },
        {
            "Parameter": "Benchmark series",
            "Default": DEFAULT_BENCHMARK_NAME,
            "Override": (
                benchmark_picker.value
                if benchmark_picker.value != DEFAULT_BENCHMARK_NAME
                else ""
            ),
            "Used": params.benchmark_name,
        },
        {
            "Parameter": "Benchmark return column",
            "Default": "*calculated*",
            "Override": "",
            "Used": params.benchmark_return_header,
        },
        {
            "Parameter": "Trading days per year (to annualize tracking error)",
            "Default": "*calculated*",
            "Override": "",
            "Used": str(params.trading_days_per_year),
        },
    ]
    params_table = pd.DataFrame(param_rows)
    return params, params_table, used_end, used_start


@app.cell
def _(mo, used_end, used_start):
    mo.md(f"Computation window: **{used_start}** → **{used_end}** (inclusive).")
    return


@app.cell
def _(mo, params_table):
    mo.ui.table(params_table, label="Analysis period parameters")
    return


@app.cell
def _(mo):
    run_regressions = mo.ui.run_button(
        label="Run regressions",
        kind="success",
    )
    run_regressions
    return (run_regressions,)


@app.cell
def _(
    build_consolidated_group_stats,
    build_fund_regression_table,
    is_script_mode,
    params,
    run_regressions,
    set_regression_results,
    workbook_path,
):
    if is_script_mode or run_regressions.value:
        _fund_table = build_fund_regression_table(workbook_path, params)
        _consolidated_table = build_consolidated_group_stats(_fund_table)
        set_regression_results((_fund_table, _consolidated_table))
    return


@app.cell
def _(format_table_figures, get_regression_results, mo):
    per_fund_payload = get_regression_results()
    if per_fund_payload is None:
        per_fund_view = mo.callout(
            "Set parameters above, then click **Run regressions**.",
            kind="info",
        )
    else:
        per_fund_table, _consolidated_table = per_fund_payload
        per_fund_view = mo.vstack(
            [
                mo.md(f"## Per-fund regressions ({len(per_fund_table):,} funds)"),
                mo.ui.table(
                    format_table_figures(per_fund_table),
                    selection=None,
                    page_size=25,
                ),
            ]
        )
    per_fund_view
    return


@app.cell
def _(format_table_figures, get_regression_results, mo):
    consolidated_payload = get_regression_results()
    if consolidated_payload is None:
        consolidated_view = None
    else:
        _per_fund_table, consolidated_table = consolidated_payload
        consolidated_view = mo.vstack(
            [
                mo.md("""
                ## Consolidated statistics by group

                Daily returns from D-Timeseries final, annualised × trading days/yr (252).
                Std dev & variance are sample (n−1). Blanks excluded.
                """),
                mo.ui.table(
                    format_table_figures(consolidated_table),
                    selection=None,
                    page_size=50,
                ),
            ]
        )
    consolidated_view
    return


if __name__ == "__main__":
    app.run()