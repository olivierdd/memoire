# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "altair>=6.3.0",
#     "exchange-calendars>=4.13.3",
#     "marimo>=0.25.2",
#     "openpyxl>=3.1.5",
#     "pandas>=3.0.6",
#     "pyarrow>=26.0.0",
#     "statsmodels>=0.15.0",
#     "yfinance>=1.7.0",
# ]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Load daily series (V2)")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    # State payloads for gated steps (None until Run button pressed)
    get_gap, set_gap = mo.state(None)
    get_holiday, set_holiday = mo.state(None)
    get_scale, set_scale = mo.state(None)
    get_level_jump, set_level_jump = mo.state(None)
    get_rebuild, set_rebuild = mo.state(None)
    get_spike, set_spike = mo.state(None)
    get_wide, set_wide = mo.state(None)
    get_frozen, set_frozen = mo.state(None)
    get_tbill, set_tbill = mo.state(None)
    get_export, set_export = mo.state(None)
    return (
        get_export,
        get_frozen,
        get_gap,
        get_holiday,
        get_level_jump,
        get_rebuild,
        get_scale,
        get_spike,
        get_tbill,
        get_wide,
        set_export,
        set_frozen,
        set_gap,
        set_holiday,
        set_level_jump,
        set_rebuild,
        set_scale,
        set_spike,
        set_tbill,
        set_wide,
    )


@app.cell
def _(mo):
    import textwrap

    def md(text: str):
        """Render markdown after stripping common indentation (avoids code blocks)."""
        return mo.md(textwrap.dedent(text).strip())

    def review_table(frame, label):
        return mo.ui.table(
            frame,
            label=label,
            selection=None,
            pagination=len(frame) > 12,
            page_size=12,
            max_height=420,
        )

    def selection_stats(n_ids: int, n_columns: int | None = None, *, when: str = "start"):
        columns = (
            f" ({n_columns:,} series columns)"
            if n_columns is not None
            else ""
        )
        if when == "start":
            text = (
                f"**Selection at the start of this step:** {n_ids:,} "
                f"fund/index ids{columns}."
            )
        else:
            text = (
                f"**Selection remaining after this step:** {n_ids:,} "
                f"fund/index ids{columns}."
            )
        return mo.md(text)

    def indent_section(content):
        """Nudge accordion body text right of the section title."""
        return mo.vstack([content]).style({"padding-left": "1.25rem"})

    def step_sections(*, documentation, result, decision, expanded=False):
        """Three collapsible panels for each workflow step (collapsed by default)."""
        return mo.accordion(
            {
                "1. Documentation": indent_section(documentation),
                "2. Result": indent_section(result),
                "3. Decision": indent_section(decision),
            },
            multiple=True,
            expanded=expanded,
        )

    def stack(*parts):
        return mo.vstack([part for part in parts if part is not None])

    def run_step_button(*, ready=True, tooltip=None):
        return mo.ui.run_button(
            label="Run step",
            disabled=not ready,
            tooltip=tooltip,
            kind="success",
        )

    def step_header(title: str, button):
        return mo.vstack([mo.md(title), button])

    return (
        md,
        review_table,
        run_step_button,
        selection_stats,
        stack,
        step_header,
        step_sections,
    )


@app.cell
def _():
    from helpers.timeseries_functions.series_v2_pipeline import (
        carry_holiday_placeholders,
        drop_identifiers_from_panel,
        drop_isins_from_funds_frame,
        flag_summary_table,
        holiday_calendar_diagnostic,
        non_zero_holiday_case_review,
        repair_distribution_day_tr,
        rescale_level_breaks,
        summarize_level_jumps,
        summarize_tr_consistency,
        thesis_sample_drop_isins,
    )

    return (
        carry_holiday_placeholders,
        drop_identifiers_from_panel,
        drop_isins_from_funds_frame,
        flag_summary_table,
        holiday_calendar_diagnostic,
        non_zero_holiday_case_review,
        repair_distribution_day_tr,
        rescale_level_breaks,
        summarize_level_jumps,
        summarize_tr_consistency,
        thesis_sample_drop_isins,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Time series data and quality-control pipeline

    **Sample at entry.** The raw extract contains every series in the
    `D-Timeseries final` sheet of `output-data/v2-funds-normalized.xlsx`:
    equity indices, the risk-free rate, and fund total-return, price and
    net-asset series. The number of identifiers, funds and series is reported
    from Step 1 onward.

    ### Objective

    This thesis measures fund performance from daily total returns and
    regresses them on the S&P 500 total return. Cumulative performance,
    volatility and regression estimates are all sensitive to errors in the
    underlying series. The raw extract is therefore treated as provisional.
    Every series passes through an eleven-step quality-control pipeline before
    it enters the analysis. This section describes the data, the problems the
    pipeline is designed to detect, and the conventions shared by all steps.

    ### Data and sources

    The panel is a set of daily series. Six header rows describe each series,
    and each following row holds one date. The first field of each row is the
    date, and each remaining field is one series: an equity index, the
    risk-free rate, or a fund's total return, price or net assets.

    The primary source is LSEG Datastream / Lipper, accessed through the
    Université libre de Bruxelles (ULB). Secondary sources are used only to
    correct or replace a Datastream series that proves unreliable:

    1. **Persistent level breaks** in Lipper data that cannot be repaired
       otherwise — Yahoo Finance (Step 1);
    2. **Missing cash distributions** needed to rebuild a total-return series
       from prices — Yahoo Finance (Step 6);
    3. **The US Treasury bill rate.** The Datastream series is empty and is
       filled from the frozen FRED series `DTB3` (Step 10).

    Throughout the pipeline, $r_{i,t}$ is the daily total return of series $i$
    on trading day $t$, and $m_t$ is the daily total return of the S&P 500
    (`.SPXTR`).

    ### Known pitfalls of Datastream data

    Studies of Datastream equity data show that naive use of its price and
    total-return series can materially distort volatility estimates, cumulative
    performance and regression inference
    ([Ince & Porter, 2006](https://doi.org/10.1111/j.1475-6803.2006.00189.x);
    [Brückner, 2013](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2243816);
    [Landis & Skouras, 2021](https://doi.org/10.1016/j.jbankfin.2021.106128)).
    Four of the documented pitfalls apply directly to a Lipper / Datastream fund
    panel (Table 0.1). Each one is screened and, where justified, repaired
    before the data is used.

    **Table 0.1 — Datastream pitfalls and their treatment in the pipeline**

    | Pitfall | Mechanism | Consequence for the analysis | Treatment |
    |---|---|---|---|
    | **Holiday padding** | On local non-trading weekdays, Datastream repeats the last close. | Artificial zero-return days that understate volatility. | Holiday observations are set to missing, and the next session's return is recomputed from the last trading day (Step 2). The gap check treats these dates as non-trading rather than missing (Step 3). |
    | **Stale prices after closure** | After a fund stops trading, its last price and return index are carried forward indefinitely. | Spurious flat tails that bias volatility and correlations downward. | Frozen post-closure tails, and series that never move, are set to missing after the last genuine observation (Step 9). |
    | **Retroactive adjustments and rounding** | Prices are restated retroactively for splits and capital changes. With limited decimal precision, heavily adjusted series can approach zero. | Spurious level jumps and extreme percentage returns. | Replacement with Yahoo data where Lipper breaks persist (Step 1); scale-shift diagnosis (Step 4); rescaling of persistent corporate-action breaks (Step 5); treatment of extreme spikes caused by data errors (Step 7). |
    | **Return-index errors** | The total-return index (RI) occasionally mishandles ordinary or special dividends and spin-offs. | Cumulative returns that drift away from a correctly reinvested path. | The daily total return is rebuilt from price plus cash distributions, and the rebuilt series is adopted when it better matches Lipper's 3-, 5- and 10-year total returns (Step 6). Distribution-day errors are repaired case by case (Step 7). |

    The divergence check (Step 8) does not target a single pitfall. It is a
    general screen that compares each series with the index.

    ### Series retained

    Step 1 retains only the series the analysis requires:

    - **fund total-return series**, together with the paired price series used
      for repairs;
    - **S&P 500 total return** (Lipper `.SPXTR`), used both as the
      quality-control benchmark and as the market factor in the main
      regressions;
    - **US Treasury bill rate**, used as the risk-free rate;
    - **S&P 500 Composite total-return series** (`S&P 500 Composite TR`,
      `S&P 500 C TR %`), kept for reference only;
    - **S&P 500 Composite daily price return** (`S&P 500 C Price %`), kept as
      a secondary benchmark for funds whose Lipper benchmark ticker is
      `.INX`. It is not used in Steps 2–11; the Lipper regression comparison
      maps `.INX` → `S&P 500 C Price %`.

    Quality control and the main regressions always use `.SPXTR` /
    `S&P 500 TR %`. The Composite series are never that benchmark. All other
    series in the extract, including net-asset series and the Composite price
    level, are dropped at Step 1.

    ### Structure of each step

    Each step is reported in three parts. The **Documentation** states the
    objective and the detection rule. The **Result** is a diagnostic that flags
    suspect observations without modifying them. The **Decision** lists the
    corrections actually applied, each with its justification.

    Steps are either *repair* or *diagnostic* steps (Table 0.2). A repair step
    modifies data only through a documented Decision. A diagnostic step never
    modifies data.

    **Table 0.2 — Pipeline steps**

    | Step | Check | Type |
    |---|---|---|
    | 1 | Loading, series selection, Yahoo replacement | Repair |
    | 2 | Holiday padding | Repair |
    | 3 | Gaps | Diagnostic |
    | 4 | Scale shift (optional, off by default) | Diagnostic |
    | 5 | Level jump | Repair |
    | 6 | Consistency with Lipper 3-, 5- and 10-year total returns | Repair |
    | 7 | Spikes and distribution days | Repair |
    | 8 | Divergence from the index | Diagnostic |
    | 9 | Frozen tails | Repair |
    | 10 | US T-bill fill | Repair |
    | 11 | Export | Output |

    ### Optional scale-shift check

    The scale-shift check (Step 4) is disabled by default. When it is disabled,
    Step 4 is skipped and the level-jump (Step 5) and spike (Step 7) checks use
    no scale-shift date. When it is enabled, the check detects lasting changes
    of at least five-fold in a series' typical return magnitude. Breaks dated
    after such a change are then excluded from the Results of Steps 5 and 7.

    ### Reproducibility and execution

    All corrections are held in memory during the session. Step 11 is the only
    step that writes to disk. It produces a separate cleaned workbook
    (`output-data/v2-funds-normalized-cleaned.xlsx`) and leaves the input file
    unchanged. Nothing is written when the notebook opens.

    The steps run in a fixed order. Step 1 runs automatically when the notebook
    opens. Each later step runs on demand, and only after the previous step has
    finished. A step's Result and Decision remain empty until that step has run.

    **Sample at exit.** Unchanged. This section describes the data and the
    pipeline and does not modify any series. Step 1 starts from the full raw
    extract.
    """)
    return


@app.cell
def _(mo):
    enable_scale_shift = mo.ui.switch(
        label="Enable scale-shift check (step 4)",
        value=False,
    )
    mo.vstack(
        [
            enable_scale_shift,
            mo.md(
                "Off by default: Step 4 is skipped and Steps 5 and 7 do not use "
                "a scale-shift date. Turn on to detect lasting 5× changes in "
                "return magnitude and to exclude post-shift breaks from the "
                "level-jump and spike Results."
            ),
        ]
    )
    return (enable_scale_shift,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 1. Loading the daily series
    """)
    return


@app.cell
def _():
    from pathlib import Path

    import pandas as pd

    from helpers.timeseries_functions.replace_yahoo_tr import (
        YAHOO_TR_REPLACEMENTS,
        replace_datastream_tr_with_yahoo,
        truncate_panel_to_sample_end,
    )
    from helpers.timeseries_functions.series_v2_panel_cache import (
        load_or_build_panel_cache,
    )
    from helpers.timeseries_functions.yahoo_tr_freeze import (
        yahoo_tr_freeze_download_date,
    )

    _label_rows = 6
    _filename = "v2-funds-normalized.xlsx"
    _sheet_name = "D-Timeseries final"

    def _find_series_workbook() -> Path:
        relative = Path("output-data") / _filename
        start = Path.cwd().resolve()
        for directory in [start, *start.parents]:
            candidate = directory / relative
            if candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError(f"Could not find {relative}, starting from {start}")

    _workbook = _find_series_workbook()

    def _build_panel_from_xlsx():
        with pd.ExcelFile(_workbook, engine="openpyxl") as book:
            _raw = pd.read_excel(book, sheet_name=_sheet_name, header=None)
        if len(_raw) <= _label_rows or _raw.shape[1] < 2:
            raise ValueError("The daily series sheet has no observations")

        _labels = _raw.iloc[:_label_rows, 1:]
        _catalog_all = pd.DataFrame(
            {
                "column": _labels.columns.astype(int),
                "id": _labels.iloc[0].astype("string").str.strip().to_numpy(),
                "name": _labels.iloc[1].astype("string").str.strip().to_numpy(),
                "category": _labels.iloc[2].astype("string").str.strip().to_numpy(),
                "fee": pd.to_numeric(_labels.iloc[3], errors="coerce").to_numpy(),
                "note": _labels.iloc[4].astype("string").str.strip().to_numpy(),
                "header": _labels.iloc[5].astype("string").str.strip().to_numpy(),
            }
        ).reset_index(drop=True)

        # Working sample only: total returns, primary S&P 500 TR / TR % (.SPXTR —
        # QA + regressions), US T-Bill, paired Price for repairs, and Composite TR
        # / C % (info / side work, e.g. .INX). Skip TNA and the S&P 500 Composite
        # Price *level* only.
        _note = _catalog_all["note"].astype("string")
        _header = _catalog_all["header"].astype("string")
        _keep = (
            _note.str.startswith("Total return")
            | _note.eq("Price, daily")
            | (
                _note.str.startswith("Daily simple return")
                & (
                    _header.str.contains(r" TR %", regex=False)
                    | _header.str.contains(r" Price %", regex=False)
                    | _header.eq("S&P 500 TR %")
                )
            )
            | _header.eq("US T-Bill 3M")
            | _header.eq("S&P 500 TR")
        )
        _catalog = _catalog_all.loc[_keep].reset_index(drop=True)
        _skipped = _catalog_all.loc[~_keep]
        _columns_on_sheet = int(len(_catalog_all))
        _columns_loaded = int(len(_catalog))
        _columns_skipped = _columns_on_sheet - _columns_loaded
        _columns_skipped_tna = int(
            _skipped["note"]
            .astype("string")
            .str.startswith("Total net assets")
            .sum()
        )
        _columns_skipped_composite_price = int(
            _skipped["header"].astype("string").eq("S&P 500 Composite Price").sum()
        )
        _keep_cols = _catalog["column"].to_numpy()

        _dates = pd.to_datetime(_raw.iloc[_label_rows:, 0], errors="coerce")
        _observations = _raw.iloc[_label_rows:, _keep_cols].apply(
            pd.to_numeric, errors="coerce"
        )
        _observations.index = pd.Index(_dates, name="date")
        _observations.columns = _keep_cols

        _valid = _observations.notna().to_numpy()
        _has_value = _valid.any(axis=0)
        _first_idx = _valid.argmax(axis=0)
        _last_idx = _valid.shape[0] - 1 - _valid[::-1].argmax(axis=0)
        _date_values = _observations.index.to_numpy()
        _first_date = pd.Series(
            pd.NaT, index=_observations.columns, dtype="datetime64[ns]"
        )
        _last_date = pd.Series(
            pd.NaT, index=_observations.columns, dtype="datetime64[ns]"
        )
        _first_date.iloc[_has_value] = _date_values[_first_idx[_has_value]]
        _last_date.iloc[_has_value] = _date_values[_last_idx[_has_value]]
        _catalog = _catalog.assign(
            observations=_valid.sum(axis=0),
            first_date=_first_date.to_numpy(),
            last_date=_last_date.to_numpy(),
        )

        # Drop the full sheet frame; export dumps catalog + cleaned observations
        # into a separate workbook (input unchanged; skipped series are omitted).
        del _raw

        # Truncate every series to the Lipper fund month-end endpoint before Yahoo
        # replacement, so replaced series cannot extend past that common date.
        _catalog, _observations, _sample_end = truncate_panel_to_sample_end(
            _catalog, _observations
        )

        # Replace Datastream/Lipper Price + TR for funds where Yahoo has no lasting
        # §5.3 break and matches Lipper long-horizon performance. CFIMX is not in
        # YAHOO_TR_REPLACEMENTS — Yahoo still has a level jump there.
        _catalog, _observations, _yahoo_tr_log = replace_datastream_tr_with_yahoo(
            _catalog, _observations
        )

        return {
            "catalog": _catalog,
            "observations": _observations,
            "yahoo_tr_log": _yahoo_tr_log,
            "label_rows": _label_rows,
            "sheet_name": _sheet_name,
            "columns_on_sheet": _columns_on_sheet,
            "columns_loaded": _columns_loaded,
            "columns_skipped": _columns_skipped,
            "columns_skipped_tna": _columns_skipped_tna,
            "columns_skipped_composite_price": _columns_skipped_composite_price,
            "sample_end_date": _sample_end,
            "yahoo_tr_download_date": yahoo_tr_freeze_download_date(),
        }

    # Excel remains the source of truth; a Parquet sidecar under
    # cache/series-v2-panel/ is rebuilt when the workbook or Yahoo freeze
    # inputs change.
    _panel = load_or_build_panel_cache(
        workbook=_workbook,
        sheet_name=_sheet_name,
        build=_build_panel_from_xlsx,
        replacements=YAHOO_TR_REPLACEMENTS,
    )

    label_rows = _panel["label_rows"]
    workbook = _workbook
    sheet_name = _panel["sheet_name"]
    catalog = _panel["catalog"]
    observations = _panel["observations"]
    sample_end_date = _panel["sample_end_date"]
    columns_on_sheet = _panel["columns_on_sheet"]
    columns_loaded = _panel["columns_loaded"]
    columns_skipped = _panel["columns_skipped"]
    columns_skipped_tna = _panel["columns_skipped_tna"]
    columns_skipped_composite_price = _panel["columns_skipped_composite_price"]
    yahoo_tr_log = _panel["yahoo_tr_log"]
    yahoo_tr_replacements = YAHOO_TR_REPLACEMENTS
    yahoo_tr_download_date = _panel["yahoo_tr_download_date"]
    panel_loaded_from_cache = bool(_panel["loaded_from_cache"])
    return (
        catalog,
        columns_loaded,
        columns_on_sheet,
        columns_skipped,
        columns_skipped_composite_price,
        columns_skipped_tna,
        label_rows,
        observations,
        panel_loaded_from_cache,
        pd,
        sample_end_date,
        sheet_name,
        workbook,
        yahoo_tr_download_date,
        yahoo_tr_log,
        yahoo_tr_replacements,
    )


@app.cell
def _(
    catalog,
    columns_loaded,
    columns_on_sheet,
    columns_skipped,
    columns_skipped_composite_price,
    columns_skipped_tna,
    md,
    mo,
    observations,
    panel_loaded_from_cache,
    pd,
    review_table,
    sample_end_date,
    stack,
    step_sections,
    yahoo_tr_download_date,
    yahoo_tr_log,
    yahoo_tr_replacements,
):
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _parsed_dates = observations.index.dropna()
    _missing_dates = int(observations.index.isna().sum())
    _fund_mask = catalog["category"].isin(
        ["Active MF", "Active ETF", "Passive MF", "Passive ETF", "To Check MF"]
    )
    _n_fund_ids = int(catalog.loc[_fund_mask, "id"].nunique())
    _n_fund_series = int(_fund_mask.sum())
    _category_label = {
        "Active MF": "Active mutual funds",
        "Active ETF": "Active ETFs",
        "Passive MF": "Passive mutual funds",
        "Passive ETF": "Passive ETFs",
        "To Check MF": "Mutual fund, category to be confirmed",
        "Index": "Index series (S&P 500 TR, S&P 500 Composite)",
        "Risk-free rate": "Risk-free rate (3-month T-bill)",
    }
    _cat_ids = catalog.groupby("category", dropna=False)["id"].nunique()
    _cat_series = catalog.groupby("category", dropna=False).size()
    _fund_keys = [
        "Active MF",
        "Active ETF",
        "Passive MF",
        "Passive ETF",
        "To Check MF",
    ]
    _composition_rows = []
    for _key in _fund_keys:
        if _key not in _cat_ids.index:
            continue
        _composition_rows.append(
            f"| {_category_label.get(_key, _key)} | "
            f"{int(_cat_ids[_key]):,} | {int(_cat_series[_key]):,} |"
        )
    _composition_rows.append(
        f"| **Total funds** | **{_n_fund_ids:,}** | **{_n_fund_series:,}** |"
    )
    for _key in ("Index", "Risk-free rate"):
        if _key not in _cat_ids.index:
            continue
        _composition_rows.append(
            f"| {_category_label.get(_key, _key)} | "
            f"{int(_cat_ids[_key]):,} | {int(_cat_series[_key]):,} |"
        )
    _composition_rows.append(
        f"| **Total** | **{_n_ids:,}** | **{_n_cols:,}** |"
    )
    _composition_md = (
        "| Category | Identifiers | Series |\n|---|---:|---:|\n"
        + "\n".join(_composition_rows)
    )
    _n_index_ids = int(_cat_ids.get("Index", 0))
    _to_check = catalog.loc[
        catalog["category"].eq("To Check MF"), ["id", "name"]
    ].drop_duplicates("id")
    if _to_check.empty:
        _to_check_md = ""
    else:
        _to_check_lines = [
            f"`{row.id}`, {row.name}"
            for row in _to_check.itertuples(index=False)
        ]
        _to_check_md = (
            "**Unclassified fund.** One mutual fund is still labelled "
            '"To Check MF": '
            + "; ".join(_to_check_lines)
            + ". Before the thesis sample is final, it must be classified as "
            "active or passive, or excluded."
        )
    _yahoo_replaced = yahoo_tr_log.loc[yahoo_tr_log["status"].eq("replaced")]
    _yahoo_isin_set = set(_yahoo_replaced["isin"].astype(str))
    _yahoo_by_cat = (
        catalog.loc[catalog["id"].isin(_yahoo_isin_set)]
        .drop_duplicates("id")["category"]
        .value_counts()
    )
    _yahoo_cat_bits = [
        f"{int(n)} {_category_label.get(cat, cat)}"
        for cat, n in _yahoo_by_cat.items()
    ]
    _yahoo_cat_phrase = (
        ", ".join(_yahoo_cat_bits) if _yahoo_cat_bits else "none"
    )
    _yahoo_table_rows = []
    for row in _yahoo_replaced.sort_values("isin").itertuples(index=False):
        _filled = int(row.tr_days_filled)
        _blank = int(row.tr_days_blank)
        _yahoo_table_rows.append(
            f"| {row.isin} | {row.ticker} | {_filled:,} | {_blank:,} |"
        )
    _yahoo_table_md_docs = (
        "| ISIN | Yahoo ticker |\n|---|---|\n"
        + "\n".join(
            f"| {isin} | {ticker} |"
            for isin, ticker in sorted(yahoo_tr_replacements.items())
        )
    )
    _yahoo_table_md_results = (
        "| ISIN | Ticker | Observations (TR and price) | Missing dates |\n"
        "|---|---|---:|---:|\n"
        + "\n".join(_yahoo_table_rows)
    )
    # Typical Lipper fund coverage (exclude Yahoo-replaced and non-funds).
    _lipper_tr_mask = (
        _fund_mask & catalog["header"].astype("string").str.endswith(" TR")
    )
    if "source" in catalog.columns:
        _lipper_tr_mask = _lipper_tr_mask & catalog["source"].ne("Yahoo")
    else:
        _lipper_tr_mask = _lipper_tr_mask & ~catalog["id"].isin(_yahoo_isin_set)
    _lipper_fund_tr = catalog.loc[_lipper_tr_mask]
    _typical_obs = (
        int(_lipper_fund_tr["observations"].mode().iloc[0])
        if len(_lipper_fund_tr) and _lipper_fund_tr["observations"].notna().any()
        else 0
    )
    _typical_first = (
        pd.Timestamp(_lipper_fund_tr["first_date"].mode().iloc[0])
        if len(_lipper_fund_tr) and _lipper_fund_tr["first_date"].notna().any()
        else None
    )
    _typical_last = (
        pd.Timestamp(_lipper_fund_tr["last_date"].mode().iloc[0])
        if len(_lipper_fund_tr) and _lipper_fund_tr["last_date"].notna().any()
        else None
    )
    _spx_row = catalog.loc[catalog["header"].eq("S&P 500 TR")]
    _spx_obs = int(_spx_row["observations"].iloc[0]) if len(_spx_row) else 0
    _spx_last = (
        pd.Timestamp(_spx_row["last_date"].iloc[0]) if len(_spx_row) else None
    )
    _tbill_row = catalog.loc[catalog["header"].eq("US T-Bill 3M")]
    _tbill_obs = int(_tbill_row["observations"].iloc[0]) if len(_tbill_row) else 0
    _date_start = _parsed_dates.min()
    _date_end = _parsed_dates.max()
    _typical_span = (
        f"from {_typical_first:%-d %B %Y} to {_typical_last:%-d %B %Y}"
        if _typical_first is not None and _typical_last is not None
        else "span unavailable"
    )
    _spx_end_text = (
        f"up to {_spx_last:%-d %B %Y}" if _spx_last is not None else "end unavailable"
    )
    _yahoo_missing_mode = (
        int(_yahoo_replaced["tr_days_blank"].mode().iloc[0])
        if len(_yahoo_replaced) and _yahoo_replaced["tr_days_blank"].notna().any()
        else None
    )
    _yahoo_filled_mode = (
        int(_yahoo_replaced["tr_days_filled"].mode().iloc[0])
        if len(_yahoo_replaced) and _yahoo_replaced["tr_days_filled"].notna().any()
        else None
    )
    _gqepx = _yahoo_replaced.loc[_yahoo_replaced["ticker"].eq("GQEPX")]
    _gqepx_blank = (
        int(_gqepx["tr_days_blank"].iloc[0]) if len(_gqepx) else None
    )
    _step1_result = stack(
        md(f"""
        ### 1.5 Results

        The working panel contains {_n_cols:,} series for {_n_ids:,} identifiers
        ({_n_fund_ids:,} funds, {_n_index_ids:,} index series and the risk-free
        rate) over {len(_parsed_dates):,} dates, from
        {_date_start:%-d %B %Y} to {_date_end:%-d %B %Y}. All
        {len(_yahoo_replaced):,} Yahoo replacements were carried out.
        {f"{len(_to_check):,} fund is still unclassified." if len(_to_check) == 1 else (f"{len(_to_check):,} funds are still unclassified." if len(_to_check) else "Every fund is classified.")}
        {"Loaded from the Parquet sidecar in `cache/series-v2-panel/` (xlsx unchanged)." if panel_loaded_from_cache else "Built from the xlsx and written to `cache/series-v2-panel/` for faster reloads."}

        **Calendar.** The panel covers {len(_parsed_dates):,} dates, and
        {"every row has a valid date." if _missing_dates == 0 else f"**{_missing_dates:,}** rows have no date."}

        **Series selection.** Of the {columns_on_sheet:,} series in the source
        sheet, {columns_loaded:,} are loaded and {columns_skipped:,} are
        excluded: {columns_skipped_tna:,} fund total-net-asset (TNA) series and
        {columns_skipped_composite_price:,} S&P 500 Composite price level
        (Table 1.1). Not every fund has a TNA column in the extract:
        {_n_fund_ids - columns_skipped_tna:,} of the {_n_fund_ids:,} loaded
        funds have none, so the exclusion count is below one TNA per fund plus
        the Composite price level. Each fund contributes four series:
        total-return index, daily total return, price and daily price return.
        This gives {_n_fund_ids:,} × 4 = {_n_fund_series:,} fund series. Six
        market series are added: the S&P 500 total-return index and its daily
        return, the S&P 500 Composite total-return index and its daily return,
        the Composite daily price return, and the 3-month T-bill rate. The
        total is {_n_cols:,} series (Table 1.3).

        **Table 1.3 — Composition of the loaded panel**
        """),
        mo.md(_composition_md),
        md(f"""
        Seven of these funds ({_yahoo_cat_phrase}) use Yahoo Finance data
        (§1.3). Their category is unchanged, so the active / passive counts in
        Table 1.3 are unaffected.
        """),
        md(_to_check_md) if _to_check_md else None,
        md(f"""
        **Coverage.** The working panel was truncated to the common Lipper fund
        sample end
        ({f"{pd.Timestamp(sample_end_date):%-d %B %Y}" if sample_end_date is not None else "unavailable"}).
        Every series — fund, index and risk-free — ends on that date. Datastream
        / Lipper fund series typically have {_typical_obs:,} level observations,
        {_typical_span}. This count includes the holiday observations repeated
        by Datastream, which Step 2 handles. The S&P 500 TR benchmark covers the
        whole truncated panel ({_spx_obs:,} observations, {_spx_end_text}).

        The common endpoint is the last trading day of the latest completed
        month. Later comparisons with Lipper's month-end performance statistics
        (Step 6) therefore share that month-end with every series. Regressions
        and Lipper checks use common dates. The 3-month T-bill series
        {"has no observations in the source and is filled in Step 10" if _tbill_obs == 0 else f"is already populated ({_tbill_obs:,} observations)"}.

        **Yahoo replacement.** All {len(_yahoo_replaced):,} funds in Table 1.2
        were replaced from the frozen extract after the panel truncation
        (Table 1.4).
        {f"Freeze download date: **{yahoo_tr_download_date}**." if yahoo_tr_download_date else "No freeze manifest found; a live Yahoo download was used."}
        {f"For six of them, the TR and price series each have {_yahoo_filled_mode:,} observations and {_yahoo_missing_mode:,} missing dates, which is consistent with US market holidays being left missing by design." if _yahoo_filled_mode is not None and _yahoo_missing_mode is not None else ""}
        {f"GQEPX has {int(_gqepx['tr_days_filled'].iloc[0]):,} observations and {_gqepx_blank:,} missing dates, consistent with a shorter history over the sample period." if len(_gqepx) and _gqepx_blank is not None and _yahoo_missing_mode is not None and _gqepx_blank != _yahoo_missing_mode else ""}

        **Table 1.4 — Coverage of the replaced series**
        """),
        mo.md(_yahoo_table_md_results),
        mo.md(
            f"**Sample at exit.** {_n_ids:,} identifiers ({_n_fund_ids:,} funds, "
            f"{_n_index_ids:,} index series and the risk-free rate) and "
            f"{_n_cols:,} series."
        ),
        review_table(yahoo_tr_log, "Yahoo Price+TR replacement log"),
        review_table(catalog, "Daily series catalog (loaded)"),
    )
    _step_view = step_sections(
        documentation=stack(
            mo.md(
                f"**Sample at entry.** The source sheet contains "
                f"{columns_on_sheet:,} series."
            ),
            md(r"""
            ### 1.1 Objective

            This step builds the working panel that every later step uses. It
            loads the raw daily series and retains only those the analysis
            needs. It also replaces the price and total-return series of seven
            funds with Yahoo Finance data, because their Datastream / Lipper
            series contain persistent level breaks (§1.3).

            ### 1.2 Series retained

            The empirical chapters rely on three kinds of series: fund daily
            total returns, the S&P 500 total return as the market benchmark, and
            the 3-month US Treasury bill rate as the risk-free rate. The source
            workbook contains more series than these. Table 1.1 shows which are
            loaded.

            **Table 1.1 — Series in the source workbook and their role**

            | Series | Role | Loaded |
            |---|---|---|
            | Fund total-return index and daily total return (`TR`, `TR %`) | Main variable of the analysis | Yes |
            | Fund price and daily price return (`Price`, `Price %`) | Input to the repair steps only (distributions, level breaks) | Yes |
            | S&P 500 total-return index and daily return (`S&P 500 TR`, `S&P 500 TR %`; Lipper `.SPXTR`) | Quality-control benchmark and regression market factor | Yes |
            | S&P 500 Composite total-return index and daily return (`S&P 500 Composite TR`, `S&P 500 C TR %`) | Reference only | Yes |
            | S&P 500 Composite daily price return (`S&P 500 C Price %`) | Secondary benchmark in the Lipper regression comparison for funds whose Lipper ticker is `.INX` (not used in Steps 2–11) | Yes |
            | 3-month US Treasury bill (`US T-Bill 3M`) | Risk-free rate (filled in Step 10) | Yes |
            | Total net assets (TNA) | Not used | No |
            | S&P 500 Composite price level (daily price index; Lipper `.INX` level) | Not used | No |

            Quality control and the main regressions always use
            `S&P 500 TR %` (Lipper `.SPXTR`). The Composite total-return series
            are reference only. `S&P 500 C Price %` is loaded solely so the
            Lipper regression comparison can map funds with benchmark ticker
            `.INX` to a market series; it is not a quality-control benchmark
            and is unused in Steps 2–11. Series that are not loaded remain in
            the input workbook but do not appear in the cleaned export
            (Step 11).

            ### 1.3 Replacement of seven fund series with Yahoo Finance data

            The seven funds in Table 1.2 are a **fixed curated list**
            (`YAHOO_TR_REPLACEMENTS`). Step 1 does not re-screen the panel for
            replacements. The list was produced offline by:

            1. running the lasting-break screen later formalised in §5.3 on the
               **raw** Datastream / Lipper Price and TR series;
            2. identifying funds with persistent Lipper level breaks caused by
               mishandled corporate actions;
            3. checking the corresponding Yahoo Price and TR series against the
               same lasting-break rule over the whole period, and against
               Lipper's reported 3-, 5- and 10-year performance;
            4. keeping only funds whose Yahoo series showed **no lasting break**
               and agreed with Lipper's long-horizon performance.

            For these funds, both the price and the total-return series are
            replaced, so that the two remain consistent for the later
            quality-control and repair steps. Step 5 later skips the same seven
            ISINs so Datastream corporate-action factors are not applied to
            Yahoo history.

            **Table 1.2 — Funds whose series are replaced with Yahoo Finance data**
            """),
            mo.md(_yahoo_table_md_docs),
            md(f"""
            The Clipper Fund (US1888501012, CFIMX) was screened the same way and
            is not replaced, because its Yahoo series shows the same break as
            the Datastream / Lipper series. It is corrected in Step 5 instead
            (§5.6).

            The replacement series are constructed as follows.

            - **Price.** The Yahoo closing price adjusted for splits but not
              for distributions.[^yf] The price therefore has no break at a
              split and stays consistent with the total-return series.
            - **Total return.** The Yahoo closing price adjusted for
              distributions, i.e. with distributions reinvested.
            - **Calendar.** The working panel is first truncated to the common
              Lipper fund sample end (last trading day of the latest completed
              month). Both Yahoo series are then aligned to those dates. Dates
              with no Yahoo observation stay missing. US market holidays,
              identified as days on which the S&P 500 does not move, are left
              missing. Yahoo history after the sample end is never written.
            - **Daily returns.** Returns are computed from one trading session
              to the next:

            $$
            r_{{i,t}} = \\frac{{P_{{i,t}}}}{{P_{{i,t^-}}}} - 1,
            $$

            where $P_{{i,t}}$ is the level of series $i$ on day $t$ and $t^-$ is
            the last trading day before $t$. As a result, a holiday does not
            cause a second missing return on the following session.

            The replaced series keep their original names (`{{ISIN}} Price`,
            `{{ISIN}} TR`), so later steps treat them like any other series.
            Their fund-type category is unchanged, and the catalog records
            their source (Lipper or Yahoo).

            **Reproducibility.** Yahoo recomputes the whole
            distribution-adjusted history whenever a new distribution is paid,
            so adjusted *levels* depend on the download date (daily *returns*
            do not). Step 1 therefore reads a **frozen extract** under
            `cache/yahoo-tr-replacements/` (Price and TR CSV files plus
            `manifest.json`).
            {f"Download date recorded in the manifest: **{yahoo_tr_download_date}**." if yahoo_tr_download_date else "No freeze manifest was found; Step 1 falls back to a live Yahoo download."}
            Re-freeze the extract only when the replacement map or the intended
            download date changes.

            [^yf]: In yfinance, the price is `Close` downloaded with
            `auto_adjust=False`, which is split-adjusted but not
            distribution-adjusted. The total return is `Close` downloaded with
            `auto_adjust=True`.

            ### 1.4 Procedure

            1. **Reading.** The source sheet is read without a header.[^file]
            2. **Header rows.** Rows 1 to 6 describe each series: identifier,
               name, category, fee (% per year), note and short header.
            3. **Series filter.** A series is retained if it meets at least one
               of the following conditions:
               - **Total-return level:** its note starts with "Total return"
                 (fund TR levels and S&P 500 Composite TR);
               - **S&P 500 TR:** it is `S&P 500 TR` or `S&P 500 TR %`;
               - **Daily return:** its short header contains `TR %` or
                 `Price %` (daily simple returns, including the S&P 500
                 Composite series);
               - **Risk-free rate:** it is `US T-Bill 3M`;
               - **Paired price:** it is a fund `Price` or `Price %` series
                 paired with a retained TR series.

               In effect, only total net assets and the S&P 500 Composite price
               level are excluded.
            4. **Working tables.** The filtered sheet is split into two tables:
               - a *catalog* with one row per series: identifier, name,
                 category (fund type), source (Lipper or Yahoo), fee, note,
                 short header, original position in the sheet, and coverage
                 (number of observations, first and last date);
               - an *observation panel* of dates × series, with dates parsed,
                 values converted to numbers and unreadable cells set to
                 missing.

               The full sheet is then released from memory. The export
               (Step 11) writes only these two tables.
            5. **Sample-end truncation.** Observation rows after the modal last
               date of Lipper fund total-return series are dropped. Every
               retained series — funds, indices and the risk-free rate — then
               ends on that common date (the last trading day of the latest
               completed month).
            6. **Yahoo replacement.** The price and TR series of the seven
               funds in Table 1.2 are replaced from the frozen Yahoo extract
               (§1.3), and their source is set to Yahoo. Because the panel has
               already been truncated, Yahoo prints after the sample end are
               never written.

            [^file]: Sheet `D-Timeseries final` of
            `output-data/v2-funds-normalized.xlsx`.
            """),
        ),
        result=_step1_result,
        decision=stack(
            md(f"""
            ### 1.6 Decision

            Step 1 applies four decisions (Table 1.5).

            **Table 1.5 — Decisions applied in Step 1**

            | Decision | Series affected | Justification |
            |---|---|---|
            | Series selection | {columns_skipped:,} series not loaded ({columns_skipped_tna:,} TNA, {columns_skipped_composite_price:,} S&P 500 Composite price level) | Not used in the analysis (§1.2) |
            | Sample-end truncation | All loaded series; panel ends {f"{pd.Timestamp(sample_end_date):%-d %B %Y}" if sample_end_date is not None else "on the Lipper fund month-end"} | Common month-end endpoint for Lipper comparisons (Step 6) and for Yahoo replacements (§1.4) |
            | Yahoo replacement | Price and TR series of seven funds (Table 1.2); frozen extract{f" dated {yahoo_tr_download_date}" if yahoo_tr_download_date else ""} | Curated offline list: raw Lipper lasting breaks under the §5.3 rule, Yahoo clean and Lipper-consistent (§1.3). Not recomputed at load. |
            | Lipper data kept | Clipper Fund (US1888501012, CFIMX) | The Yahoo series shows the same break; corrected in Step 5 (§5.6) |

            **Benchmark.** All later quality-control and repair steps, and the
            main regressions, compare funds with `S&P 500 TR %` (Lipper
            `.SPXTR`). Composite TR / `C TR %` are reference only.
            `S&P 500 C Price %` is reserved for the Lipper regression
            comparison, which maps `.INX` → `S&P 500 C Price %`; it is not
            used in Steps 2–11.

            **Interaction with Step 5.** The level-break rescaling in Step 5
            skips the seven replaced funds. This prevents Datastream
            corporate-action factors from being applied to Yahoo history.
            Observation counts for the replaced series are given in Table 1.4.

            **Sample at exit.** {_n_ids:,} identifiers ({_n_fund_ids:,} funds,
            {_n_index_ids:,} index series and the risk-free rate) and
            {_n_cols:,} series.
            """),
        ),
    )
    _step_view
    return


@app.cell(hide_code=True)
def _(run_step_button, step_header):
    run_holiday = run_step_button()
    _header = step_header("## 2. Exchange holidays", run_holiday)
    _header
    return (run_holiday,)


@app.cell
def _(
    carry_holiday_placeholders,
    catalog,
    observations,
    run_holiday,
    set_holiday,
):
    if run_holiday.value:
        _corrected, _correction_log, _holiday_dates = carry_holiday_placeholders(
            catalog, observations
        )
        set_holiday(
            {
                "observations": _corrected,
                "correction_log": _correction_log,
                "holiday_dates": _holiday_dates,
            }
        )
    return


@app.cell
def _(
    catalog,
    get_holiday,
    holiday_calendar_diagnostic,
    md,
    mo,
    non_zero_holiday_case_review,
    observations,
    pd,
    review_table,
    stack,
    step_sections,
):
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _fund_mask = catalog["category"].isin(
        ["Active MF", "Active ETF", "Passive MF", "Passive ETF", "To Check MF"]
    )
    _n_fund_ids = int(catalog.loc[_fund_mask, "id"].nunique())
    _n_index_ids = int(
        catalog.loc[catalog["category"].eq("Index"), "id"].nunique()
    )
    _n_rf_ids = int(
        catalog.loc[catalog["category"].eq("Risk-free rate"), "id"].nunique()
    )
    _sample_phrase = (
        f"{_n_ids:,} identifiers ({_n_fund_ids:,} funds, "
        f"{_n_index_ids:,} index series and the risk-free rate) and "
        f"{_n_cols:,} series"
    )
    _documentation = stack(
        mo.md(
            f"**Sample at entry.** {_sample_phrase} (price and total-return "
            f"levels, each with its daily return, plus the reference index "
            f"returns and the risk-free rate)."
        ),
        md(r"""
        ### 2.1 Objective

        This step takes US exchange holidays out of the return observations. All
        series share one panel calendar, and that calendar still has a row on
        days when the US equity market is closed. If those rows were kept,
        non-trading days would count as observations with a zero or spurious
        return. That would understate return volatility and inflate the number
        of observations in the regressions on the S&P 500 total return. It
        would also create artificial gaps in series that do not report on those
        dates. Step 2 sets every holiday to missing and restates the return of
        the next session, so that this return covers the whole interval since
        the last trading day.

        ### 2.2 Background: sources of holiday rows

        Holiday rows appear through two different source behaviours:

        - **Padding (Datastream / Lipper).** On a market holiday, Datastream
          often carries the level forward from the previous close. The series
          then shows a repeated level and a daily return of exactly zero.
        - **Omission (Yahoo Finance).** Yahoo Finance usually publishes no
          print on a holiday. Once the series is aligned to the panel calendar,
          the cell is already missing.

        So the same date is a zero-return observation in a padded series and a
        missing value in a Yahoo series. Without a common treatment, the gap
        check (Step 3) would flag the Yahoo series, and the return statistics
        would mix two conventions.

        ### 2.3 Method

        **Notation.** Let $m_t$ be the level of the S&P 500 total return index
        (`S&P 500 TR`) on date $t$. Let $P_{i,t}$ be the level of series $i$
        (price or total-return index), $r_{i,t}$ its daily return, and
        $\varepsilon = 10^{-6}$ an absolute tolerance on the level difference
        $|m_t - m_{t-1}|$.

        **Holiday rule.** A date $t$ is a US exchange holiday when the
        benchmark level is unchanged from the previous date:

        $$
        t \in \mathcal{H} \iff \left| m_t - m_{t-1} \right| \le \varepsilon .
        $$

        The tolerance is absolute, not relative. It is small enough to detect
        exact carry-forwards of the previous close and large enough to absorb
        floating-point noise. The rule needs no external calendar: it uses the
        benchmark of the analysis, so the funds and the benchmark are treated
        on the same trading days. Section 2.5 reports two checks: that no
        trading day with a genuine near-zero S&P 500 TR move falls inside the
        tolerance band, and that $\mathcal{H}$ coincides with the official
        NYSE holiday list over the sample.

        **Treatment.** For every level series and its paired return, on each
        holiday $h \in \mathcal{H}$:

        $$
        P_{i,h} \leftarrow \text{NA}, \qquad r_{i,h} \leftarrow \text{NA}.
        $$

        Let $\tau$ be the last trading date before the holiday and $t$ the first
        following session with a valid level. The return on $t$ is restated
        against the last trading close:

        $$
        r_{i,t} = \frac{P_{i,t}}{P_{i,\tau}} - 1 .
        $$

        In a padded series, the carried-forward holiday level equals
        $P_{i,\tau}$, so the restated return is the same as the original one.
        The restatement changes the return only when the holiday print differs
        from the previous close (Table 2.1). Series that are already missing on
        a holiday, typically Yahoo series, go through the same procedure, so
        every series follows one calendar.

        **Table 2.1 — Treatment of a padded series around a holiday $h$**

        | Date | Level before | Return before | Level after | Return after |
        |---|---|---|---|---|
        | $\tau$ (last trading date) | $P_{i,\tau}$ | $r_{i,\tau}$ | $P_{i,\tau}$ | $r_{i,\tau}$ |
        | $h$ (holiday) | $P_{i,\tau}$ (carried forward) | $0$ | NA | NA |
        | $t$ (next session) | $P_{i,t}$ | $P_{i,t}/P_{i,\tau} - 1$ | $P_{i,t}$ | $P_{i,t}/P_{i,\tau} - 1$ |

        ### 2.4 Outputs

        The Result is diagnostic only. It reports the holiday calendar
        $\mathcal{H}$, its match with the official NYSE list, any series that
        print a non-zero return on a holiday before treatment, and a case
        review of those identifiers (NYSE status of each flagged date and the
        surrounding level path). The Decision applies the treatment and
        produces:

        1. The holiday calendar $\mathcal{H}$, passed to Step 3 to exempt
           these dates from the gap check.
        2. A per-series blanking log: identifier, series, fund category,
           series type (price or total-return index), number of holidays
           treated, and number of values changed. A value counts as changed
           only if it differs after treatment; cells that were already
           missing are not counted.
        3. The treated panel, passed to Step 3 and later steps.
        """),
    )
    _holiday = get_holiday()
    if _holiday is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to identify S&P-flat holidays and score "
                "the calendar diagnostics._"
            ),
            decision=mo.md("_Decision pending until this step has run._"),
        )
    else:
        _correction_log = _holiday["correction_log"]
        _holiday_dates = _holiday["holiday_dates"]
        _holiday_count = len(_holiday_dates)
        _n_series_blanked = len(_correction_log)
        _n_ids_blanked = (
            int(_correction_log["id"].nunique()) if len(_correction_log) else 0
        )
        _n_ids_untreated = _n_ids - _n_ids_blanked
        _treated_id_set = (
            set(_correction_log["id"].astype("string"))
            if len(_correction_log)
            else set()
        )
        _short_history_mask = _fund_mask & ~catalog["id"].astype("string").isin(
            _treated_id_set
        )
        _n_short_history_ids = int(
            catalog.loc[_short_history_mask, "id"].nunique()
        )
        _n_short_history_series = int(_short_history_mask.sum())
        _n_reference_untouched_ids = _n_ids_untreated - _n_short_history_ids
        _n_series_treated_pairs = 2 * _n_series_blanked
        _n_series_unchanged = _n_cols - _n_series_treated_pairs
        _last_holiday = (
            pd.Timestamp(_holiday_dates.max()) if _holiday_count else None
        )
        _last_holiday_txt = (
            f"{_last_holiday:%-d %B %Y}" if _last_holiday is not None else "unavailable"
        )
        _n_cells = (
            int(_correction_log["cells_changed"].sum()) if len(_correction_log) else 0
        )
        _has_spx = (
            bool(_correction_log["header"].eq("S&P 500 TR").any())
            if len(_correction_log)
            else False
        )
        _n_dual_funds = (_n_series_blanked - int(_has_spx)) // 2
        _pure_carry = 2 * _holiday_count
        _structure_eq = (
            f"{_n_series_blanked:,} = 2 × {_n_dual_funds:,} + 1"
            if _has_spx
            else f"{_n_series_blanked:,} = 2 × {_n_dual_funds:,}"
        )
        _spx_clause = (
            "; the S&P 500 TR has only a total-return level"
            if _has_spx
            else ""
        )
        _panel_start = pd.Timestamp(observations.index.min())
        _panel_end = pd.Timestamp(observations.index.max())
        _panel_years = (_panel_end - _panel_start).days / 365.25
        _holidays_per_year = (
            _holiday_count / _panel_years if _panel_years > 0 else float("nan")
        )
        _spx_level_row = catalog.loc[
            catalog["header"].eq("S&P 500 TR")
            & catalog["note"].astype("string").str.startswith("Total return index")
        ]
        _min_non_holiday_move = None
        if len(_spx_level_row):
            _spx_level = observations[int(_spx_level_row.iloc[0]["column"])]
            _prev_close = _spx_level.shift(1)
            _abs_move = (_spx_level - _prev_close).abs()
            _non_holiday = (
                _spx_level.notna()
                & _prev_close.notna()
                & ~_spx_level.index.isin(_holiday_dates)
            )
            if _non_holiday.any():
                _min_non_holiday_move = float(_abs_move.loc[_non_holiday].min())
        _min_move_txt = (
            f"{_min_non_holiday_move:.2f}"
            if _min_non_holiday_move is not None
            else "unavailable"
        )
        _holiday_table, _nyse_only = holiday_calendar_diagnostic(
            _holiday_dates, observations.index
        )
        _n_nyse_match = (
            int(_holiday_table["nyse_holiday"].sum()) if len(_holiday_table) else 0
        )
        _n_nyse_only = len(_nyse_only)
        # Plain Unicode in f-string Results/Decision: KaTeX inside interpolated
        # mo.md text often shows raw "$\\command$" instead of rendering.
        _h_tex = "holiday calendar H"
        _eps_tex = "ε = 10⁻⁶"
        _pair_blanks_tex = f"2 × {_holiday_count:,}"
        _nyse_absent_txt = (
            f"No NYSE holiday on a panel weekday is absent from the {_h_tex}."
            if _n_nyse_only == 0
            else (
                f"**{_n_nyse_only:,}** NYSE holiday"
                f"{'s' if _n_nyse_only != 1 else ''} on panel weekdays "
                f"{'are' if _n_nyse_only != 1 else 'is'} absent from the "
                f"{_h_tex}."
            )
        )
        _case_summary, _nonzero_holiday = non_zero_holiday_case_review(
            catalog, observations, _holiday_dates, _correction_log
        )
        _n_nonzero_cells = len(_nonzero_holiday)
        _n_nonzero_series = (
            int(_nonzero_holiday["header"].nunique()) if _n_nonzero_cells else 0
        )
        _n_nonzero_ids = (
            int(_nonzero_holiday["id"].nunique()) if _n_nonzero_cells else 0
        )
        _n_case_all_nyse = (
            int(_case_summary["all_nyse"].sum()) if len(_case_summary) else 0
        )
        _n_above_pure = (
            int((_case_summary["max_cells_changed"] > _pure_carry).sum())
            if len(_case_summary)
            else 0
        )
        _holiday_table_view = _holiday_table.rename(
            columns={
                "date": "Date",
                "weekday": "Weekday",
                "nyse_holiday": "NYSE holiday",
            }
        )
        _case_view = (
            _case_summary.rename(
                columns={
                    "id": "Identifier",
                    "name": "Name",
                    "category": "Category",
                    "holiday_dates": "Holiday dates with non-zero return",
                    "all_nyse": "All dates NYSE holidays",
                    "max_cells_changed": "Max values changed after treatment",
                    "finding": "Finding",
                }
            )
            if len(_case_summary)
            else _case_summary
        )
        _nonzero_view = (
            _nonzero_holiday.rename(
                columns={
                    "id": "Identifier",
                    "header": "Series",
                    "category": "Category",
                    "date": "Date",
                    "return": "Return",
                    "nyse_holiday": "NYSE holiday",
                }
            )
            if _n_nonzero_cells
            else _nonzero_holiday
        )
        _case_lines = []
        for _row in _case_summary.itertuples(index=False):
            _case_lines.append(
                f"- `{_row.id}` ({_row.name}, {_row.category}): "
                f"{_row.holiday_dates} holiday date"
                f"{'s' if int(_row.holiday_dates) != 1 else ''} with a "
                f"non-zero return"
                f"{'; all NYSE' if bool(_row.all_nyse) else ''}. "
                f"{_row.finding}"
            )
        # Indent case bullets to the same column as the surrounding f-string
        # body so textwrap.dedent (inside md()) still strips the common
        # indent. Unindented insert lines zero the common prefix and Markdown
        # then treats the whole Result as an indented code fence.
        _case_indent = "                "
        _case_md = (
            "\n".join(_case_indent + line for line in _case_lines)
            if _case_lines
            else (
                _case_indent
                + "No identifier prints a non-zero return on an S&P-flat "
                "holiday."
            )
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                md(f"""
                ### 2.5 Results

                The holiday rule identifies **{_holiday_count:,}** exchange
                holidays over the working panel, from
                {_panel_start:%-d %B %Y} to {_panel_end:%-d %B %Y}
                (about {_panel_years:.0f} years, or
                {_holidays_per_year:.1f} holidays a year). This Result is
                diagnostic only: it does not modify any series.

                **False-positive check.** On every non-holiday day with a
                valid S&P 500 TR print, the absolute level change is at least
                {_min_move_txt} index points — four orders of magnitude above
                {_eps_tex}. No trading day with a near-zero benchmark move was
                therefore classified as a holiday.

                **External calendar.** Of the {_holiday_count:,} S&P-flat
                dates, **{_n_nyse_match:,}** match an official NYSE holiday.
                {_nyse_absent_txt}[^nyse] Table 2.2 lists every date and the
                match flag.

                **Non-zero holiday returns.** Before treatment,
                **{_n_nonzero_series:,}** series belonging to
                **{_n_nonzero_ids:,}** identifiers print a non-zero daily
                return on at least one holiday ({_n_nonzero_cells:,}
                holiday–series cells). All other paired return series are
                either exactly zero or already missing on every holiday.

                **Case review.** Each flagged date was checked against the
                NYSE calendar and against the surrounding level path.
                **{_n_case_all_nyse:,}** of {_n_nonzero_ids:,} identifiers
                have every flagged date on an official NYSE holiday: none of
                these prints falls on a misclassified trading day. The
                patterns are source artifacts (Table 2.3):

{_case_md}

                After treatment, **{_n_above_pure:,}** of these identifiers
                have more than {_pure_carry:,} changed values
                ({_pair_blanks_tex} blanks plus at least one restated
                next-session return). Table 2.4 lists every holiday–series
                cell with a non-zero pre-treatment return.

                [^nyse]: Cross-checked with the `XNYS` calendar in the
                `exchange_calendars` package over the panel weekdays.
                """),
                mo.md("**Table 2.2 — S&P-flat holidays and NYSE match**"),
                review_table(_holiday_table_view, "Holiday calendar"),
                (
                    mo.md(
                        "**Table 2.3 — Case review of identifiers with "
                        "non-zero holiday returns**"
                    )
                    if len(_case_summary)
                    else mo.md(
                        "**Table 2.3 — Case review of identifiers with "
                        "non-zero holiday returns.** None."
                    )
                ),
                (
                    review_table(_case_view, "Non-zero holiday case review")
                    if len(_case_summary)
                    else None
                ),
                (
                    mo.md(
                        "**Table 2.4 — Non-zero daily returns on S&P-flat "
                        "holidays (before treatment)**"
                    )
                    if _n_nonzero_cells
                    else None
                ),
                (
                    review_table(_nonzero_view, "Non-zero holiday returns")
                    if _n_nonzero_cells
                    else None
                ),
                (
                    review_table(
                        _nyse_only.rename(
                            columns={"date": "Date", "weekday": "Weekday"}
                        ),
                        "NYSE holidays absent from H",
                    )
                    if _n_nyse_only
                    else None
                ),
            ),
            decision=stack(
                md(f"""
                ### 2.6 Decision

                **Decision.** All identifiers and series are retained. On each
                of the {_holiday_count:,} holidays, the level and return of
                every paired series are set to missing, and the next session's
                return is restated from the last trading close (§2.3). The
                holiday calendar is passed to Step 3, and the treated panel to
                the later consistency steps.

                This treatment puts every series, whatever its source, on the
                trading calendar of the regression benchmark. Funds and
                benchmark returns therefore span the same intervals, and
                non-trading days are not counted as observations.

                The treatment touches **{_n_series_blanked:,}** level series
                belonging to **{_n_ids_blanked:,}** identifiers
                ({_n_series_treated_pairs:,} series once each paired return is
                counted). The count of level series is consistent with the
                panel structure: {_structure_eq}. Each of the
                {_n_dual_funds:,} funds has a price level and a total-return
                level{_spx_clause}.

                **{_n_ids_untreated:,}** identifiers do not appear in the
                blanking log. They fall into two groups:

                1. **Short histories ({_n_short_history_ids:,} funds,
                   {_n_short_history_series:,} series).** Their samples begin
                   after {_last_holiday_txt}, the last date in the {_h_tex},
                   so no exchange holiday falls in their span.
                2. **Reference series outside the logged Price/TR pairs
                   ({_n_reference_untouched_ids:,} identifiers).** The S&P 500
                   Composite TR level has no return series named to match the
                   level header under this step's pairing rule; three
                   stand-alone index daily-return identifiers and the empty
                   3-month T-bill are not logged as level pairs. The benchmark
                   return `S&P 500 TR %` is nonetheless blanked as the pair of
                   the treated `S&P 500 TR` level, so its catalog identifier is
                   absent from the log even though the series is treated.

                **{_n_series_unchanged:,}** series are left unchanged: the
                {_n_short_history_series:,} short-history fund series and the
                unpaired reference series (Composite TR level, Composite daily
                returns, and the T-bill).

                For a series that covers all {_holiday_count:,} holidays,
                {_pure_carry:,} changed values means the level and the return
                were set to missing on each holiday ({_pair_blanks_tex}) and no
                next-session return changed — every holiday print was a pure
                carry-forward. The S&P 500 TR is in this case. A count above
                {_pure_carry:,} means that on at least one holiday the printed
                level differed from the previous close, so the next-session
                return was restated. The case review in §2.5 confirms that
                those dates are official NYSE holidays and that the excess
                changes come from source artifacts (Table 2.3), not from a
                misclassified trading day.

                **Table 2.5 — Summary of the holiday treatment**

                | Item | Count |
                |---|---:|
                | Exchange holidays identified | {_holiday_count:,} |
                | Match with NYSE holiday calendar | {_n_nyse_match:,} of {_holiday_count:,} |
                | Identifiers treated | {_n_ids_blanked:,} of {_n_ids:,} |
                | Level series treated (each with its return series) | {_n_series_blanked:,} |
                | Series unchanged | {_n_series_unchanged:,} of {_n_cols:,} |
                | Values changed (holiday values set to missing, next-session returns restated) | {_n_cells:,} |
                | Identifiers removed | 0 |

                The full per-series blanking log ({_n_series_blanked:,} rows)
                is reported below.

                **Sample at exit.** {_sample_phrase} (unchanged; no identifier
                removed).
                """),
                review_table(_correction_log, "Holiday blanking log"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_holiday, run_step_button, step_header):
    _ready = get_holiday() is not None
    run_gap = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 2 first")
    _header = step_header("## 3. Gap", run_gap)
    _header
    return (run_gap,)


@app.cell
def _(catalog, get_holiday, run_gap, set_gap, summarize_tr_consistency):
    if run_gap.value:
        _holiday = get_holiday()
        if _holiday is None:
            raise ValueError("Gap step requires holiday output")
        _observations = _holiday["observations"]
        _controls, _issue_summary, _checks = summarize_tr_consistency(
            catalog,
            _observations,
            flags=("gaps",),
            exchange_holidays=_holiday["holiday_dates"],
        )
        set_gap(
            {
                "observations": _observations,
                "controls": _controls,
                "issue_summary": _issue_summary,
                "checks": _checks,
            }
        )
    return


@app.cell
def _(
    catalog,
    flag_summary_table,
    get_gap,
    get_holiday,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    mo.stop(
        get_holiday() is None,
        mo.md("Run step 2 first."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _documentation = stack(
        selection_stats(_n_ids, _n_cols),
        md("""
        ### What and why

        This step scores **gaps** on the **post-holiday** panel: missing returns,
        skipped months, or long holes between dates. Step 2 already set exchange
        holidays to NA (exempt from the gap screen), so Gap focuses on remaining
        calendar holes.

        Gap scoring uses the shared helper
        `helpers.timeseries_functions.check_timeseries_consistency.locate_series_issues`
        with ``flags=("gaps",)`` so only the gap predicates run. Later steps
        request their own flags (and any prerequisites) on the evolving panel.
        No series are rewritten here.

        ### Universe

        Daily **TR %** columns whose matching level is a total-return index,
        excluding `S&P 500 TR %` (benchmark).

        ### Gap rule

        A row is a **gap** if any of the following holds (the first row is never
        treated as missing): (i) the fund return is missing (except S&P-flat
        exchange holidays); (ii) the calendar month label in `Period` jumps by
        more than one month; (iii) consecutive `Date` values are more than **45
        calendar days** apart.

        On a daily panel, any hole longer than one trading day already triggers
        (i), so (ii) and (iii) rarely add a flag. They are kept as backstops
        against structural extraction holes — whole dates missing from the
        panel index, not merely blank cells — for which the 45-day threshold is
        a coarse guard (about two calendar months).

        **Coverage of the screen.** The check is applied only between each
        series' first and last non-missing return. Dates before a fund enters
        the panel, and dates after it leaves, are outside that window and are
        not treated as missing returns. The working panel itself already ends
        on the common Lipper fund sample end set in Step 1 (30 October 2026);
        any longer raw benchmark tail is not part of the sample screened here.
        """),
    )
    _gap = get_gap()
    if _gap is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to score gaps on the post-holiday panel._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _issue_summary = _gap["issue_summary"]
        _gap_table = flag_summary_table(_issue_summary, "gaps")
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{len(_issue_summary):,}** series checked \n"
                    f"- **{len(_gap_table):,}** series with at least one gap \n"
                ),
                review_table(_gap_table, "Series with gaps"),
            ),
            decision=stack(
                md("""
                Keep all series. Gap counts are diagnostic; no levels or returns
                are rewritten at this step. The post-holiday observations frame
                is retained for later consistency checks.
                """),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(enable_scale_shift, get_gap, mo, run_step_button, step_header):
    if not enable_scale_shift.value:
        _header = mo.vstack(
            [
                mo.md("## 4. Scale shift"),
                mo.md("_Skipped — enable the scale-shift switch at the top of the notebook to run this step._"),
            ]
        )
        run_scale = None
    else:
        _ready = get_gap() is not None
        run_scale = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 3 first")
        _header = step_header("## 4. Scale shift", run_scale)
    _header
    return (run_scale,)


@app.cell
def _(
    catalog,
    enable_scale_shift,
    get_gap,
    run_scale,
    set_scale,
    summarize_tr_consistency,
):
    if run_scale is not None and run_scale.value and enable_scale_shift.value:
        _gap = get_gap()
        if _gap is None:
            raise ValueError("Scale step requires gap output")
        _observations = _gap["observations"]
        _controls, _issue_summary, _checks = summarize_tr_consistency(
            catalog, _observations, flags=("scale",)
        )
        set_scale(
            {
                "observations": _observations,
                "controls": _controls,
                "issue_summary": _issue_summary,
                "checks": _checks,
            }
        )
    return


@app.cell
def _(
    catalog,
    enable_scale_shift,
    flag_summary_table,
    get_gap,
    get_scale,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    if not enable_scale_shift.value:
        mo.stop(
            get_gap() is None,
            mo.md("Run step 3 first."),
        )
        mo.stop(
            mo.md(
                "### Step 4 skipped\n\nScale-shift is **disabled**. Level jump and "
                "spike steps proceed from step 3 without scale prerequisites."
            )
        )
    mo.stop(
        get_gap() is None,
        mo.md("Run step 3 first."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _mermaid_init = (
        "%%{init: "
        '{"flowchart": {"padding": 8, "nodeSpacing": 12, "rankSpacing": 20}, '
        '"themeVariables": {"fontSize": "13px"}}'
        "}%%\n"
    )
    _documentation = stack(
        selection_stats(_n_ids, _n_cols),
        md("""
        ### What and why

        **Question asked:** on the **post-holiday** panel (after step 2), did a
        fund’s *typical* daily move size change **for good** — and stay on the new
        scale — rather than just having an unusually large single day?

        This is **not** the spike screen. We ask whether the whole TR % history
        looks like two eras with different **normal** move magnitudes. Common
        causes:

        - **Percent vs decimal** — e.g. `0.01` (1%) in one segment and `1.0` (1%)
          in another, so typical ``|return|`` jumps by orders of magnitude.
        - **Rebased or re-spliced TR feed** — vendor changes level or return
          construction so daily % sizes no longer match pre-change history.
        - **Lasting ~5× regime** — for many months, day-to-day absolute moves stay
          much larger or smaller than before (the default fold threshold is **5×**,
          not one outlier).

        **Post-holiday panel:** step 2 blanks level and daily % on US exchange
        holidays (S&P-flat days). That frame is what gap and later checks use; scale
        runs on the same observations (via the gap payload), without rewriting
        series here.

        ### Scale rule

        We scan candidate split dates and use **medians of** ``|return|`` (robust to
        a few wild days). For each candidate **S**, compare:

        1. **Local:** median ``|r|`` in the **126** trading days after **S** vs the
           **126** days before.
        2. **Global:** median ``|r|`` for all days after **S** vs all days before.

        Flag **scale shift** only when **both** ratios are ≥ **5×** or both are ≤
        **1/5**; among qualifying splits, keep the sharpest. One-off spikes rarely
        move both medians enough to pass.

        ### Diagnostic and later steps

        This step is **diagnostic only**: it records candidate splits and does
        **not** adjust levels or returns.

        Later steps do **not** read a split date stored here. Step 5
        (`summarize_level_jumps`) re-detects scale on the current panel when the
        scale-shift switch is on and drops post-split **TR** lasting breaks from
        Result only. Step 7 spikes still re-detect scale via
        `summarize_tr_consistency` (`_FLAG_REQUIRES`) to suppress post-split
        spike flags for that scoring pass.
        """),
        mo.mermaid(
            _mermaid_init
            + """
    flowchart TB
      subgraph local["Local test at candidate split S"]
        direction LR
        B["126 days before S<br/>median |r| e.g. 0.5%"] --> S["split S"]
        S --> A["126 days after S<br/>median |r| e.g. 3%"]
      end
      subgraph global["Global test at the same S"]
        direction LR
        P["All days before S<br/>median |r|"] --> S2["split S"]
        S2 --> Q["All days after S<br/>median |r|"]
      end
      local --> rule["Flag only if BOTH local and global<br/>are ≥ 5× or both ≤ 1/5"]
      global --> rule
    """
        ),
    )
    _scale = get_scale()
    if _scale is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to re-score scale shifts._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _controls = _scale["controls"]
        _issue_summary = _scale["issue_summary"]
        _scale_table = flag_summary_table(_issue_summary, "scale_shift")
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{len(_issue_summary):,}** series re-checked \n"
                    f"- **{len(_scale_table):,}** series with a scale shift \n"
                    f"- Scale factor {_controls['scale_factor']:g} over "
                    f"{_controls['scale_window']} days \n"
                ),
                review_table(_scale_table, "Series with scale shifts"),
            ),
            decision=stack(
                md("""
                Diagnostic only. No levels or returns are rescaled at this step.
                The scale flags shown here are not persisted into later steps as
                a stored state. Steps 5 and 7 re-detect scale on the current
                panel when needed (Result scale gate for level jumps; spike
                scoring for Step 7) and suppress post-split regimes for that
                pass only.
                """),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(enable_scale_shift, get_gap, get_scale, run_step_button, step_header):
    if enable_scale_shift.value:
        _ready = get_scale() is not None
        _tip = None if _ready else "Run step 4 first"
    else:
        _ready = get_gap() is not None
        _tip = None if _ready else "Run step 3 first"
    run_level_jump = run_step_button(ready=_ready, tooltip=_tip)
    _header = step_header("## 5. Level jump", run_level_jump)
    _header
    return (run_level_jump,)


@app.cell
def _(
    catalog,
    enable_scale_shift,
    get_gap,
    get_scale,
    rescale_level_breaks,
    run_level_jump,
    set_level_jump,
    summarize_level_jumps,
):
    if run_level_jump.value:
        if enable_scale_shift.value:
            _prior = get_scale()
            if _prior is None:
                raise ValueError("Level jump step requires scale output")
        else:
            _prior = get_gap()
            if _prior is None:
                raise ValueError("Level jump step requires gap output")
        _observations = _prior["observations"]
        _controls, _issue_summary, _all_breaks, _result_breaks = summarize_level_jumps(
            catalog,
            _observations,
            use_scale=enable_scale_shift.value,
        )
        _adjusted, _action_log = rescale_level_breaks(
            catalog, _observations, breaks=_all_breaks
        )
        set_level_jump(
            {
                "observations": _adjusted,
                "controls": _controls,
                "issue_summary": _issue_summary,
                "all_breaks": _all_breaks,
                "result_breaks": _result_breaks,
                "action_log": _action_log,
            }
        )
    return


@app.cell
def _(
    catalog,
    enable_scale_shift,
    flag_summary_table,
    get_gap,
    get_level_jump,
    get_scale,
    md,
    mo,
    pd,
    review_table,
    stack,
    step_sections,
):
    if enable_scale_shift.value:
        mo.stop(
            get_scale() is None,
            mo.md("Run step 4 first."),
        )
    else:
        mo.stop(
            get_gap() is None,
            mo.md("Run step 3 first."),
        )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _sample_phrase = f"{_n_ids:,} identifiers (funds and indices), {_n_cols:,} series"
    _mermaid_init = (
        "%%{init: "
        '{"flowchart": {"padding": 8, "nodeSpacing": 12, "rankSpacing": 20}, '
        '"themeVariables": {"fontSize": "13px"}}'
        "}%%\n"
    )
    _documentation = stack(
        mo.md(f"**Sample at entry.** {_sample_phrase}."),
        md(r"""
        ### 5.1 Objective

        This step looks for daily returns that move the level of a series
        permanently. A one-day spike that later reverses is a different case.
        Permanent level breaks come from broken corporate-action adjustments,
        unadjusted splits or rebasings, and splices between share classes or
        quote types. Any cumulative return or regression window that spans the
        break date carries the error forward. These breaks must therefore be
        found and corrected before any performance measure is computed.

        Other anomalies are handled in later steps. Spikes (an absolute daily
        return of at least 10%) are treated in Step 7. Days on which a fund
        deviates from the benchmark by at least 5% are treated in Step 8. A
        lasting change in the typical size of returns (a scale shift) is the
        subject of Step 4.

        ### 5.2 Sources of persistent breaks

        In Lipper and Datastream fund panels, persistent breaks usually have
        one of five origins:

        1. **Splits and reverse splits.** The NAV moves by the split ratio, but
           the history is not restated consistently. The effective date may
           also be misaligned, for example around holidays.
        2. **Incorrect split adjustment.** The vendor scales the history in the
           wrong direction, applies the factor more than once, or applies it to
           only part of the history. If the history was multiplied by $N$
           instead of divided by $N$ (or the reverse), the correction factor is
           $N^2$.
        3. **Master–feeder or quote switches.** The series switches from a
           technical notional value to the published NAV of an investor share
           class.
        4. **Total-return rebasing.** The price series is coherent, but the
           return index is spliced or rebuilt incorrectly, for example in the
           treatment of distributions.
        5. **Other splices.** Fund mergers, share-class consolidations and ISIN
           changes.

        Three phenomena are explicitly not treated as level breaks:

        - (i) ex-dividend or liquidation price drops when the total-return
          series is continuous;
        - (ii) extreme moves that later reverse (spikes, Step 7);
        - (iii) scale shifts (Step 4).

        Comparing a fund's price series with its total-return (TR) series helps
        identify the cause of a break (Table 5.1). The thesis measures
        performance from total returns, so only TR breaks are reported in the
        Result (§5.5). A price break on the same day does not create a separate
        Result entry. It confirms the TR break and usually means both series
        need rescaling in the Decision (§5.6).

        **Table 5.1 — Interpretation of a break by the series in which it appears**

        | Break observed in | Most likely cause | Treatment |
        |---|---|---|
        | Price and TR | Split, wrong-direction or double adjustment, master–feeder switch | Reported in Result (via TR); candidate for rescaling of both series |
        | TR only | Return-index rebasing | Reported in Result |
        | Price only (TR continuous) | Distribution or liquidation NAV | Not reported in Result; usually retained |

        ### 5.3 Detection rule

        Let $r_{i,t}$ be the daily simple return (in decimals) of series $i$ on
        day $t$, either price or TR. Let $m_t$ be the daily total return of the
        S&P 500 (`S&P 500 TR %`). With threshold $L = 0.50$, day $t$ is flagged
        as a persistent level break in series $i$ if all three conditions below
        hold:

        1. **Magnitude:** $|r_{i,t}| \ge L$.
        2. **Idiosyncrasy:** $|r_{i,t} - m_t| \ge L/2$. The market cannot
           explain the move.
        3. **Persistence:** the compounded return over the first $K \le 4$
           non-missing sessions starting at $t$,
        $$
        s_{i,t} = \prod_{k=0}^{K-1} \left(1 + r_{i,t+k}\right) - 1,
        $$
        satisfies
        $$
        \frac{s_{i,t}}{r_{i,t}} \ge \frac{1}{2}.
        $$
        Equivalently, $s_{i,t}$ has the same sign as $r_{i,t}$ and
        $|s_{i,t}| \ge |r_{i,t}|/2$.

        The threshold $L = 0.50$ is set to catch large, persistent level
        errors: unadjusted or wrongly adjusted splits of 2-for-1 or larger
        (a fall of about $50\%$ or a rise of $100\%$), and comparable vendor
        splices. Smaller ratios, such as a 3-for-2 split (about $-33\%$), fall
        below this floor. They are left to case review and to later steps;
        a move that does not reverse is also outside the spike screen in
        Step 7. A sensitivity check with $L = 0.30$ is reported in §5.5.

        The idiosyncrasy condition is kept as a guard against an extreme
        market day. On this panel it does not bind once $|r_{i,t}| \ge L$:
        the largest daily S&P 500 TR move in the sample is about $12\%$ in
        absolute value, well below $L/2$ at either $L = 0.50$ or
        $L = 0.30$. Detection therefore turns on magnitude and persistence.

        The persistence condition is what separates a break from a spike. An
        absolute-value test alone would treat an overshooting reversal
        (for example $+60\%$ then $-70\%$) as a break, because the compounded
        return is large even though its sign has flipped. Requiring the same
        sign rules that case out. If the move reverses within the window, the
        ratio falls below one half. If the level has really moved, at least
        half of the initial move remains in the same direction. Table 5.2
        gives a stylised example.

        **Table 5.2 — Stylised example of the persistence condition**

        | Case | $r_{t-1}$ | $r_t$ | $r_{t+1}$ | $r_{t+2}$ | $s_{i,t}$ | $s_{i,t}/r_t$ | Outcome |
        |---|---|---|---|---|---|---|---|
        | Spike | +1% | +60% | −37.5% | +1% | ≈ +1% | ≈ 0.02 | Not flagged |
        | Level break | +1% | +60% | +2% | +1% | ≈ +65% | ≈ 1.08 | Flagged |

        The rule is applied to every fund price series and every fund TR series,
        each tested against the S&P 500 TR.

        ### 5.4 Outputs

        - **Result** reports TR breaks only. This includes the series replaced
          with Yahoo Finance data in Step 1. The Result changes no observation.
        - **Optional scale-shift gate (Result only).** When the gate is on, the
          date $S^*$ of a TR scale shift is detected again with the Step 4 rule:
          a rolling window of $W = 126$ sessions and a factor $\kappa = 5$ on the
          ratio of local to global median $|r|$. TR breaks on or after $S^*$ are
          then dropped from the Result, so that a unit change is not also
          counted as a level break.
        - **Decision** works on the full, ungated set of price and TR breaks. It
          applies curated rules (§5.6.1) to breaks that are still present. It
          logs every TR series flagged in the Result and every rescaled or
          retained break, including price-only breaks.
        """),
        mo.mermaid(
            _mermaid_init
            + """
    flowchart LR
      subgraph jump["Level break — move sticks"]
        direction LR
        j1["… +1%"] --> j2["+60% vs S&P"] --> j3["+2%"] --> j4["+1%"]
      end
      subgraph notjump["Not a level break — reverses"]
        direction LR
        n1["… +1%"] --> n2["+60%"] --> n3["−37.5%"] --> n4["+1%"]
      end
    """
        ),
    )
    _decision_policy = md(r"""
        ### 5.6 Decision: correction of persistent breaks

        #### 5.6.1 Principles

        No series is removed at this step. An observation is changed only when
        two conditions both hold:

        - a curated rule exists for the series;
        - the break that the rule targets is still detected in the current
          panel.

        Each rule was set after a case-by-case review against external evidence:
        published NAVs, fund announcements and distribution notices. Each rule
        records its justification. There are two types of rule:

        - **Rescaling rules.** A rule names the identifier, the break date and
          the series (price, TR or both), and gives a factor and a direction. In
          *history* mode, all levels before the break are multiplied by the
          factor (here a factor below 1, i.e. a division). In *forward* mode,
          all levels from the break onward are multiplied. The break-day return
          is then recomputed from the corrected levels.
        - **Retention rules.** These use the same identification and do no
          rescaling. They document price drops caused by a real economic event,
          such as an ex-distribution date or a liquidating distribution, while
          the TR series stays continuous. The observation is kept as it is and
          logged.

        A break in a Result series with no matching rule is left unadjusted and
        reported as such. Series replaced with Yahoo Finance data have no
        rescaling rules, because that source is already split-adjusted.

        #### 5.6.2 Scope of the decision log

        The log covers two sets:

        - (i) every break in a series flagged in the Result (§5.5);
        - (ii) every rescaled or retained break from the full price and TR scan,
          so that price-only events are documented too.

        A rule whose target break is no longer detected, for example because an
        earlier run of this step already corrected it, is left out. The log
        therefore shows only the outcomes of the current run.
        """)
    _level_jump = get_level_jump()
    if _level_jump is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to run the lasting-break scan, build the "
                "TR Result table, and apply Decision rules._"
            ),
            decision=stack(
                _decision_policy,
                mo.md("_Decision pending until this step has run._"),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. No series is "
                    f"removed until this step has run."
                ),
            ),
        )
    else:
        _issue_summary = _level_jump["issue_summary"]
        _jump_table = flag_summary_table(_issue_summary, "level_jumps")
        _action_log = _level_jump["action_log"]
        _all_breaks = _level_jump.get("all_breaks") or []
        _result_breaks = _level_jump.get("result_breaks") or []
        _jump_isins = set(_jump_table["id"].astype("string").str.strip())
        _scan_isins = {str(item["isin"]).strip() for item in _all_breaks}
        _price_break_n = sum(1 for item in _all_breaks if item.get("side") == "Price")
        _tr_break_n = sum(1 for item in _all_breaks if item.get("side") == "TR")

        def _fund_display_name(isin: str) -> str:
            names = catalog.loc[
                catalog["id"].astype("string").str.strip().eq(isin), "name"
            ].astype("string")
            label = str(names.iloc[0]) if len(names) else isin
            for _suffix in (
                " - TOT RETURN IND",
                " - PRICE",
                " - TOTAL NET ASSETS",
            ):
                if label.endswith(_suffix):
                    return label[: -len(_suffix)]
            return label

        def _category_for(isin: str) -> str:
            cats = catalog.loc[
                catalog["id"].astype("string").str.strip().eq(isin), "category"
            ].astype("string")
            return str(cats.iloc[0]) if len(cats) else "—"

        # Decision = Result ISINs (all outcomes) ∪ rescaled/kept from full scan.
        _pending = _action_log.loc[
            ~_action_log["decision"].eq("already rescaled")
        ].copy()
        _pending_isin = _pending["isin"].astype("string").str.strip()
        _in_result = _pending_isin.isin(_jump_isins)
        _rule_done = _pending["decision"].isin(["rescaled", "kept"])
        _decision_log = _pending.loc[_in_result | _rule_done].reset_index(drop=True)
        if len(_decision_log):
            _decision_log = _decision_log.assign(
                in_result=_decision_log["isin"]
                .astype("string")
                .str.strip()
                .isin(_jump_isins)
            )

        _rescaled = _decision_log.loc[_decision_log["decision"].eq("rescaled")]
        _kept = _decision_log.loc[_decision_log["decision"].eq("kept")]
        _not_adjusted = _decision_log.loc[_decision_log["decision"].eq("not adjusted")]
        _rescaled_funds = int(_rescaled["isin"].nunique()) if len(_rescaled) else 0
        _kept_funds = int(_kept["isin"].nunique()) if len(_kept) else 0
        _not_adjusted_funds = (
            int(_not_adjusted["isin"].nunique()) if len(_not_adjusted) else 0
        )
        _covered_isins = set(_decision_log["isin"].astype("string").str.strip())

        def _fmt_return(value) -> str:
            if value is None:
                return "—"
            try:
                number = float(value)
            except (TypeError, ValueError):
                return "—"
            if number != number:
                return "—"
            return f"{number:.2%}"

        def _outcome_label(decision: str) -> str:
            return {
                "rescaled": "Rescaled",
                "kept": "Retained",
                "not adjusted": "Unadjusted",
            }.get(str(decision), str(decision))

        # S&P 500 TR % on Clipper break date (panel), for the case note.
        _panel = (
            get_scale()["observations"]
            if enable_scale_shift.value and get_scale() is not None
            else get_gap()["observations"]
            if get_gap() is not None
            else None
        )
        _spx_clipper = None
        if _panel is not None:
            _spx_cols = catalog.loc[
                catalog["header"].astype("string").eq("S&P 500 TR %"), "column"
            ]
            if len(_spx_cols):
                _spx_day = pd.Timestamp("2025-05-12")
                if _spx_day in _panel.index:
                    _spx_clipper = float(_panel.loc[_spx_day, int(_spx_cols.iloc[0])])

        _cells_modified = (
            int(_rescaled["cells"].sum()) if len(_rescaled) else 0
        )
        _summary_rows = [
            {
                "Outcome": "Rescaled",
                "Identifiers": _rescaled_funds,
                "Breaks": int(len(_rescaled)),
                "Observations modified": _cells_modified,
            },
            {
                "Outcome": "Retained",
                "Identifiers": _kept_funds,
                "Breaks": int(len(_kept)),
                "Observations modified": 0,
            },
            {
                "Outcome": "Unadjusted",
                "Identifiers": _not_adjusted_funds,
                "Breaks": int(len(_not_adjusted)),
                "Observations modified": 0,
            },
            {
                "Outcome": "Total",
                "Identifiers": int(
                    _decision_log["isin"].nunique() if len(_decision_log) else 0
                ),
                "Breaks": int(len(_decision_log)),
                "Observations modified": _cells_modified,
            },
        ]
        _summary_table = pd.DataFrame(_summary_rows)

        _display_log = _decision_log.copy()
        if len(_display_log):
            _display_log = _display_log.assign(
                outcome=_display_log["decision"].map(_outcome_label),
                correction=_display_log.apply(
                    lambda row: (
                        str(row["adjustment"])
                        if row["decision"] == "rescaled"
                        else "None"
                    ),
                    axis=1,
                ),
                return_path=[
                    (
                        f"{_fmt_return(before)} → {_fmt_return(after)}"
                        if decision == "rescaled"
                        else f"{_fmt_return(before)} (unchanged)"
                    )
                    for decision, before, after in zip(
                        _display_log["decision"],
                        _display_log["return_before"],
                        _display_log["return_after"],
                        strict=True,
                    )
                ],
            )
            _display_log = _display_log[
                [
                    "isin",
                    "fund",
                    "date",
                    "series",
                    "outcome",
                    "correction",
                    "return_path",
                    "cells",
                ]
            ].rename(
                columns={
                    "isin": "Identifier",
                    "fund": "Fund",
                    "date": "Break date",
                    "series": "Series",
                    "outcome": "Outcome",
                    "correction": "Correction",
                    "return_path": "Break-day return (before → after)",
                    "cells": "Observations modified",
                }
            )

        # Case narratives: one polished justification per identifier+date.
        _case_blocks: list[str] = []
        if len(_decision_log):
            _grouped = _decision_log.sort_values(["date", "isin", "series"])
            for (_isin, _date), _grp in _grouped.groupby(["isin", "date"], sort=False):
                _fund = str(_grp["fund"].iloc[0])
                _why = str(_grp["why"].iloc[0])
                _decisions = sorted(set(_grp["decision"].astype(str)))
                _label = "/".join(_outcome_label(d).lower() for d in _decisions)
                _ticker_by_isin = {
                    "US1888501012": "CFIMX",
                    "US00791R7807": "VNUYX",
                    "US3624014086": "SRIDX",
                }
                _ticker = _ticker_by_isin.get(str(_isin).strip())
                _title = (
                    f"**{_fund}** ({_ticker}, {_isin}) — {_label}."
                    if _ticker
                    else f"**{_fund}** ({_isin}) — {_label}."
                )
                _lines = [_title, _why]
                if (
                    str(_isin).strip() == "US1888501012"
                    and str(_date) == "2025-05-12"
                    and _spx_clipper is not None
                ):
                    _resc = _grp.loc[_grp["decision"].eq("rescaled")]
                    if len(_resc):
                        _price_after = _resc.loc[
                            _resc["series"].astype(str).eq("Price"), "return_after"
                        ]
                        _tr_after = _resc.loc[
                            _resc["series"].astype(str).eq("TR"), "return_after"
                        ]
                        _price_txt = (
                            _fmt_return(_price_after.iloc[0])
                            if len(_price_after)
                            else "—"
                        )
                        _tr_txt = (
                            _fmt_return(_tr_after.iloc[0])
                            if len(_tr_after)
                            else "—"
                        )
                        _lines.append(
                            f"The corrected break-day return ({_price_txt} for "
                            f"price, {_tr_txt} for TR) is close to the S&P 500 "
                            f"TR return on the same day "
                            f"({_fmt_return(_spx_clipper)}). This fits a strong "
                            f"market day rather than leftover vendor noise."
                        )
                if str(_isin).strip() == "US3624014086":
                    _lines.append(
                        "The residual post-liquidation days are kept for audit "
                        "continuity but are not treated as active performance. "
                        "Step 9 blanks frozen tails, where price and TR stay "
                        "flat while the market moves."
                    )
                _case_blocks.append("\n\n".join(_lines))
        for _isin in sorted(_jump_isins - _covered_isins):
            _case_blocks.append(
                f"**{_fund_display_name(_isin)}** ({_isin}) — unadjusted. "
                f"Flagged in the Result but no matching rule this run (break "
                f"already absent or unmatched)."
            )

        _resolved = _rescaled_funds + _kept_funds
        _n_break_rows = int(len(_decision_log))
        if (
            len(_scan_isins)
            and _resolved == len(_scan_isins)
            and _not_adjusted_funds == 0
        ):
            _outcomes_intro = (
                f"All {_n_break_rows:,} break"
                f"{'' if _n_break_rows == 1 else 's'}, across "
                f"{len(_scan_isins):,} identifier"
                f"{'' if len(_scan_isins) == 1 else 's'}, "
                f"{'is' if _n_break_rows == 1 else 'are'} resolved by a curated "
                f"rule. None is left unadjusted (Table 5.5):"
            )
        else:
            _outcomes_intro = (
                f"Of {_n_break_rows:,} break"
                f"{'' if _n_break_rows == 1 else 's'} across "
                f"{len(_covered_isins):,} identifier"
                f"{'' if len(_covered_isins) == 1 else 's'}: "
                f"{_rescaled_funds:,} rescaled, {_kept_funds:,} retained, "
                f"{_not_adjusted_funds:,} unadjusted (Table 5.5)."
            )

        _rescaled_detail = ""
        if _rescaled_funds == 1 and int(len(_rescaled)) >= 1:
            _obs_per = (
                _cells_modified // max(int(len(_rescaled)), 1)
                if _cells_modified
                else 0
            )
            _sides = sorted({str(s) for s in _rescaled["series"]})
            if _sides == ["Price", "TR"]:
                _side_phrase = "in both price and TR"
            else:
                _side_phrase = "in " + " and ".join(s.lower() for s in _sides)
            _per_series = (
                f", {_obs_per:,} per series."
                if int(len(_rescaled)) > 1 and _obs_per
                else "."
            )
            _rescaled_detail = (
                f"\n\n- {_fund_display_name(str(_rescaled['isin'].iloc[0]))} "
                f"is rescaled {_side_phrase}: {_cells_modified:,} "
                f"observations in total{_per_series}"
            )
        elif _rescaled_funds:
            _rescaled_detail = (
                f"\n\n- {_rescaled_funds:,} identifiers rescaled "
                f"({_cells_modified:,} observations)."
            )
        _retained_detail = ""
        if _kept_funds == 1:
            _retained_detail = (
                "\n- The price-only break is retained unchanged."
            )
        elif _kept_funds == 2:
            _retained_detail = (
                "\n- The two price-only breaks are retained unchanged."
            )
        elif _kept_funds > 2:
            _retained_detail = (
                f"\n- The {_kept_funds:,} price-only breaks are retained "
                f"unchanged."
            )

        _cases_md = (
            "\n\n".join(_case_blocks)
            if _case_blocks
            else "_No Decision outcomes on this run._"
        )
        _decision_outcomes = md(
            "#### 5.6.3 Outcomes\n\n"
            + _outcomes_intro
            + _rescaled_detail
            + _retained_detail
        )
        # Build without indented f-string lines: leading spaces would make
        # Markdown treat the case titles as a code block.
        _decision_justifications = md(
            "#### 5.6.4 Justification of each decision\n\n" + _cases_md
        )
        _n_tr_days = int(_issue_summary["level_jumps"].sum())
        _n_tested = int(len(_issue_summary))
        _n_tr_series = int(len(_jump_table))
        _scale_enabled = bool(enable_scale_shift.value)
        _scale_phrase = "on" if _scale_enabled else "off"

        _tr_break_isins = {
            str(item["isin"]).strip()
            for item in _all_breaks
            if item.get("side") == "TR"
        }
        _price_break_rows = []
        for _item in sorted(
            (b for b in _all_breaks if b.get("side") == "Price"),
            key=lambda b: (str(b["date"]), str(b["isin"])),
        ):
            _isin = str(_item["isin"]).strip()
            _also_tr = _isin in _tr_break_isins
            _price_break_rows.append(
                {
                    "Identifier": _isin,
                    "Fund": _fund_display_name(_isin),
                    "Break date": pd.Timestamp(_item["date"]).strftime("%Y-%m-%d"),
                    "Break-day price return": _fmt_return(
                        float(_item["stored_return"])
                    ),
                    "TR break on same day": "Yes" if _also_tr else "No",
                    "Classification": (
                        "Price and TR (Result flag)"
                        if _also_tr
                        else "Price only"
                    ),
                }
            )
        _price_cols = [
            "Identifier",
            "Fund",
            "Break date",
            "Break-day price return",
            "TR break on same day",
            "Classification",
        ]
        _price_break_table = (
            pd.DataFrame(_price_break_rows, columns=_price_cols)
            if _price_break_rows
            else pd.DataFrame(columns=_price_cols)
        )
        _price_isins = (
            set(_price_break_table["Identifier"].astype("string").str.strip())
            if len(_price_break_table)
            else set()
        )
        _n_price_only_isins = len(_price_isins - _jump_isins)
        _n_both_isins = len(_price_isins & _jump_isins)

        # Prefer TR Result breaks; fall back to TR side of the full scan so the
        # interactive table never shows the raw issue_summary (column / days /
        # gaps / spikes / …) that flag_summary_table returns.
        _tr_source = _result_breaks or [
            b for b in _all_breaks if b.get("side") == "TR"
        ]
        _result_rows = []
        for _item in sorted(
            _tr_source,
            key=lambda b: (str(b["date"]), str(b["isin"])),
        ):
            _isin = str(_item["isin"]).strip()
            _result_rows.append(
                {
                    "Identifier": _isin,
                    "Fund": _fund_display_name(_isin),
                    "Category": _category_for(_isin),
                    "Break date": pd.Timestamp(_item["date"]).strftime("%Y-%m-%d"),
                    "Break-day TR return": _fmt_return(
                        float(_item["stored_return"])
                    ),
                }
            )
        _result_cols = [
            "Identifier",
            "Fund",
            "Category",
            "Break date",
            "Break-day TR return",
        ]
        _result_display = (
            pd.DataFrame(_result_rows, columns=_result_cols)
            if _result_rows
            else pd.DataFrame(columns=_result_cols)
        )

        if _n_tr_series == 0:
            _main_finding = (
                f"Of the {_n_tested:,} TR series tested, none shows a "
                f"persistent level break. Persistent breaks are therefore rare "
                f"in this sample."
            )
        elif _n_tr_series == 1 and _n_tr_days == 1:
            _main_finding = (
                f"Of the {_n_tested:,} TR series tested, one shows a "
                f"persistent level break, on a single day (Table 5.3). "
                f"Persistent breaks are therefore rare in this sample. The one "
                f"break still matters: left uncorrected, it would bias every "
                f"cumulative return and every regression window for this fund "
                f"that spans that date."
            )
        else:
            _main_finding = (
                f"Of the {_n_tested:,} TR series tested, "
                f"{_n_tr_series:,} show a persistent level break "
                f"({_n_tr_days:,} break-days in total; Table 5.3). "
                f"Persistent breaks remain uncommon relative to the panel "
                f"size. Left uncorrected, each such break would bias every "
                f"cumulative return and every regression window for the "
                f"affected fund that spans the break date."
            )

        _full_set_md = (
            f"When the scan is extended to price series, it flags "
            f"{len(_scan_isins):,} identifier"
            f"{'' if len(_scan_isins) == 1 else 's'}: "
            f"{_price_break_n:,} price break"
            f"{'' if _price_break_n == 1 else 's'} and "
            f"{_tr_break_n:,} TR break"
            f"{'' if _tr_break_n == 1 else 's'} (Table 5.4). "
        )
        if _n_tr_series == 0:
            _full_set_md += (
                "No identifier shows a break in total return. Under Table 5.1, "
                "price-only breaks with a continuous TR series point to a "
                "distribution or a liquidation rather than a data error, so "
                "they are not Result flags. Their treatment is documented in "
                "§5.6."
            )
        elif _n_price_only_isins > 0 and _n_both_isins:
            if _n_tr_series == 1:
                _both_subject = (
                    f"Only {_fund_display_name(next(iter(_jump_isins)))} "
                    f"breaks in both series."
                )
            else:
                _both_subject = (
                    f"Only {_n_tr_series:,} identifiers break in both series."
                )
            _full_set_md += (
                f"{_both_subject} The other {_n_price_only_isins:,} break in "
                f"price only, and their TR series stay continuous. Under "
                f"Table 5.1, this pattern points to a distribution or a "
                f"liquidation rather than a data error, so these "
                f"{_n_price_only_isins:,} are not Result flags. Their "
                f"treatment is documented in §5.6."
            )
        elif _n_price_only_isins > 0:
            _full_set_md += (
                f"The {_n_price_only_isins:,} price-only break"
                f"{'' if _n_price_only_isins == 1 else 's'} "
                f"{'has' if _n_price_only_isins == 1 else 'have'} a continuous "
                f"TR series. Under Table 5.1, this pattern points to a "
                f"distribution or a liquidation rather than a data error, so "
                f"{'it is' if _n_price_only_isins == 1 else 'they are'} not "
                f"Result flag{'s' if _n_price_only_isins != 1 else ''}. "
                f"Treatment is documented in §5.6."
            )
        else:
            _full_set_md += (
                "Every scanned identifier that breaks also breaks in total "
                "return, so all enter Result as TR flags. Decision documents "
                "any rescaling or retention of the accompanying price series."
            )

        _result_md = md(
            f"""
            ### 5.5 Results

            **Test specification.** Each TR series is tested against the S&P
            500 TR with the rule of §5.3:

            - magnitude: $|r_{{i,t}}| \\ge 50\\%$;
            - idiosyncrasy: $|r_{{i,t}} - m_t| \\ge 25\\%$;
            - persistence: $s_{{i,t}} / r_{{i,t}} \\ge 1/2$.

            The scale-shift gate is {_scale_phrase} for this run. Series
            replaced with Yahoo Finance data in Step 1 are included.

            **Main finding.** {_main_finding}

            **Full scan (price and TR).** {_full_set_md}

            **Sensitivity ($L = 0.30$).** Repeating the same scan with
            $L = 0.30$ leaves the TR Result unchanged: still one persistent
            TR break (Clipper Fund). It adds seven price-only lasting drops
            of about $-30\\%$ to $-41\\%$. None is a TR break near $-33\\%$
            (a 3-for-2 scale), none matches a curated rescaling rule, and
            none changes the Decision outcomes in §5.6. The idiosyncrasy
            screen rejects no candidate at either threshold. The working
            rule therefore remains $L = 0.50$.

            The Result is diagnostic only: no observation is modified.
            Corrections and retentions are reported in §5.6.
            """
        )
        _exit_md = mo.md(
            f"**Sample at exit.** {_sample_phrase}. No series is removed. "
            + (
                f"{_cells_modified:,} observations are rescaled"
                + (
                    f", in {int(len(_rescaled)):,} series of "
                    f"{_rescaled_funds:,} fund"
                    f"{'' if _rescaled_funds == 1 else 's'}."
                    if _rescaled_funds
                    else "."
                )
                if _cells_modified
                else "No observation is rescaled."
            )
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                _result_md,
                review_table(
                    _result_display[_result_cols],
                    "Table 5.3 — TR series with persistent level breaks (Result)",
                )
                if len(_result_display)
                else mo.md(
                    "_Table 5.3 — no TR series with persistent level breaks "
                    "on this run._"
                ),
                review_table(
                    _price_break_table[_price_cols],
                    "Table 5.4 — Price series with persistent breaks (full scan)",
                )
                if len(_price_break_table)
                else mo.md(
                    "_Table 5.4 — no price series with persistent breaks on this run._"
                ),
            ),
            decision=stack(
                _decision_policy,
                _decision_outcomes,
                review_table(
                    _summary_table,
                    "Table 5.5 — Decision outcomes",
                ),
                review_table(
                    _display_log,
                    "Table 5.6 — Decision log",
                )
                if len(_display_log)
                else mo.md("_Table 5.6 — empty Decision log on this run._"),
                _decision_justifications,
                _exit_md,
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_level_jump, run_step_button, step_header):
    _ready = get_level_jump() is not None
    run_rebuild = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 5 first")
    _header = step_header(
        "## 6. Consistency with Lipper 3-, 5- and 10-year total returns",
        run_rebuild,
    )
    _header
    return (run_rebuild,)


@app.cell
def _(catalog, get_level_jump, pd, run_rebuild, set_rebuild, workbook):
    if run_rebuild.value:
        _level_jump = get_level_jump()
        if _level_jump is None:
            raise ValueError("Rebuild step requires level jump output")
        _adjusted_observations = _level_jump["observations"]

        from pathlib import Path as _Path

        def _code_root():
            _start = _Path.cwd().resolve()
            for _directory in [_start, *_start.parents]:
                if (_directory / "helpers").is_dir():
                    return _directory
            raise FileNotFoundError(f"Could not find helpers/, starting from {_start}")

        def _openfigi_tickers() -> dict[str, str]:
            import json

            _cache_path = _code_root() / "cache" / "cache-isin-openfigi.json"
            _payload = json.loads(_cache_path.read_text())
            return {
                str(_isin).strip(): str(_ticker).strip()
                for _isin, _ticker in _payload.items()
                if isinstance(_isin, str) and isinstance(_ticker, str) and _ticker
            }

        from helpers.timeseries_functions.rebuild_tr_from_distributions import (
            load_distributions_cache,
            rebuild_tr_panel,
        )
        from helpers.timeseries_functions.regress_daily_to_benchmark import (
            FUNDS_SHEET,
            load_funds_reference,
        )

        _funds = load_funds_reference(workbook, sheet_name=FUNDS_SHEET)
        _funds_by_isin = {
            str(row["ISIN"]).strip(): row for _, row in _funds.iterrows() if pd.notna(row.get("ISIN"))
        }
        _isin_to_ticker = _openfigi_tickers()

        _tr_ready_observations, _rebuild_log = rebuild_tr_panel(
            _adjusted_observations,
            catalog,
            _funds_by_isin,
            _isin_to_ticker,
            distributions_cache=load_distributions_cache(),
        )

        set_rebuild(
            {
                "observations": _tr_ready_observations,
                "rebuild_log": _rebuild_log,
            }
        )
    return


@app.cell
def _(
    catalog,
    get_level_jump,
    get_rebuild,
    md,
    mo,
    pd,
    review_table,
    stack,
    step_sections,
):
    mo.stop(
        get_level_jump() is None,
        mo.md("Run step 5 first."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _fund_mask = catalog["category"].isin(
        ["Active MF", "Active ETF", "Passive MF", "Passive ETF", "To Check MF"]
    )
    _n_fund_ids = int(catalog.loc[_fund_mask, "id"].nunique())
    _n_index_ids = int(
        catalog.loc[catalog["category"].eq("Index"), "id"].nunique()
    )
    _n_rf_ids = int(
        catalog.loc[catalog["category"].eq("Risk-free rate"), "id"].nunique()
    )
    _n_non_fund = _n_ids - _n_fund_ids
    _sample_phrase = (
        f"{_n_ids:,} fund and index identifiers ({_n_cols:,} series)"
    )
    _sample_scope = (
        f"Lipper consistency is run only on the {_n_fund_ids:,} fund ISINs "
        f"with a TR % series. The {_n_non_fund:,} non-fund identifiers "
        f"({_n_index_ids:,} index series and {_n_rf_ids:,} risk-free rate) "
        f"are out of scope for this step."
        if _n_non_fund
        else (
            f"Lipper consistency is run on the {_n_fund_ids:,} fund ISINs "
            f"with a TR % series."
        )
    )
    _documentation = stack(
        mo.md(
            f"**Sample at entry.** {_sample_phrase}. {_sample_scope}"
        ),
        md(r"""
        ### 6.1 Objective

        This step checks whether the daily total-return (TR) series used in the
        analysis add up to the cumulative returns that Lipper publishes for the
        same funds over 3, 5 and 10 years. All later measurement relies on these
        daily returns, both the regression on the S&P 500 TR and the performance
        comparison between passive and active funds. A series whose compounded
        return drifts away from an independent published figure would bias
        estimated performance, especially alpha. Lipper is the external
        reference throughout.

        ### 6.2 Background: distribution reinvestment errors

        A fund's total return has to reinvest cash distributions (dividends and
        capital-gain distributions) on their ex-dates. Some Datastream TR series
        handle this incorrectly on distribution days. When a distribution is
        missed or mistreated, the NAV drop on the ex-date is recorded as a loss.
        The cumulative return then falls permanently below the true figure, and
        the shortfall grows with each distribution in the window.

        To deal with this, the step builds a second candidate series for every
        fund, a **distribution rebuild**. It is computed from the Datastream
        price/NAV and an independent record of cash distributions, and it is
        scored against Lipper in the same way as the Datastream TR (§6.3.3).

        ### 6.3 Method

        #### 6.3.1 Horizon gaps

        Let $r_{i,t}$ be the daily total return of fund $i$ on day $t$. The
        series is truncated at the Lipper reference date $T = $ 30 September
        2026, which is the month-end of the Lipper figures in the fund master
        sheet, and then compounded to monthly returns. Let $W_h$ be the $12h$
        months ending at $T$, for $h \in \{3, 5, 10\}$. The cumulative return
        over horizon $h$ is

        $$
        R_i^{(h)} = \prod_{t \in W_h} \left(1 + r_{i,t}\right) - 1 ,
        $$

        and the gap to Lipper, in percentage points, is

        $$
        g_i^{(h)} = 100\,R_i^{(h)} - L_i^{(h)},
        $$

        where $L_i^{(h)}$ is the Lipper published total return of fund $i$ over
        $h$ years, in percent.

        #### 6.3.2 Scoring rule

        All three horizons are computed. Each fund is scored on the longest
        horizon available, with tolerance $\tau = 0.5$ pp (Table 6.1).

        The tolerance is an operational agreement band with Lipper, not an
        estimate of measurement error. Half a percentage point matches the
        tracking-error match band used when daily regressions are compared with
        Lipper elsewhere in the thesis, and it is stricter than the $1$ pp band
        used to mark cumulative total-return charts as close. Published Lipper
        horizon returns are typically quoted to two decimal places; $\tau$ is
        therefore well above rounding noise, while remaining far below the
        multi-percentage-point shortfalls that motivate the distribution rebuild
        (§6.2). Pass/fail and adoption counts at $\tau = 0.25$ pp and
        $\tau = 1$ pp are reported as a sensitivity check in §6.5–§6.6; the
        production rule keeps $\tau = 0.5$ pp.

        **Table 6.1 — Choice of scoring horizon**

        | Priority | Horizon used | Condition |
        |---|---|---|
        | 1 | 10 years | Lipper 10-year figure exists and the series covers at least 120 months |
        | 2 | 5 years | Otherwise, if the 5-year Lipper figure and window are available |
        | 3 | 3 years | Otherwise, if the 3-year Lipper figure and window are available |
        | — | Unscored | None of the three horizons can be tested |

        On the chosen horizon $h^*_i$:

        - **Pass**: $\left|g_i^{(h^*_i)}\right| \le \tau$;
        - **Fail**: $\left|g_i^{(h^*_i)}\right| > \tau$;
        - **Unscored**: no horizon can be tested.

        #### 6.3.3 Distribution rebuild

        The candidate series combines the Datastream price/NAV $P_{i,t}$ with
        the cash distribution per share $D_{i,t}$ going ex on day $t$
        ($D_{i,t} = 0$ on other days):

        $$
        \tilde r_{i,t} = \frac{P_{i,t} + D_{i,t}}{P_{i,t-1}} - 1 .
        $$

        Distributions come from Yahoo Finance first and from a cached Financial
        Modeling Prep (FMP) extract second. The prior close in the formula is the
        last non-missing price, so that after Step 2 blanks exchange holidays the
        first session after a holiday still compounds against the previous
        trading print. The candidate's gaps $\tilde g_i^{(h)}$ are computed and
        scored exactly as in §6.3.1–§6.3.2.

        A fund is classified as **index-like** when any of the following holds on
        the Funds sheet: the flag `is_index_or_idx` is true; the fund name
        contains “S&P 500”, “500 Index” or “Index Fund”; or the Lipper benchmark
        ticker is `.SPXTR` and `fund_type` is passive. The label identifies
        vehicles that are expected to track the S&P 500 total return closely. It
        is used only for the missed-ex-date fill below and for the
        no-distribution veto in §6.3.4.

        When Yahoo and FMP both supply no cash distribution and the fund is
        index-like, the rebuild applies a **missed-ex-date fill** before
        scoring. A session $t$ is treated as a missed payout when the Datastream
        price return and the Datastream TR both fall by at least $1\%$, the two
        returns agree to within $1$ percentage point, and the absolute S&P 500
        TR move that day is below $0.5\%$. On each such day the rebuilt return
        is set to the S&P 500 TR, $m_t$. The rule is a panel heuristic for
        December-style capital-gain distributions that the vendor recorded as a
        NAV drop without a matching cash event; it is not taken from a vendor
        field. Non-index-like funds without distributions receive no such fill
        and are blocked from adoption (§6.3.4).

        #### 6.3.4 Adoption rule (Decision)

        The Result is diagnostic only. It reports how the Datastream TR and the
        rebuild each score and does not choose between them. The Decision
        replaces the Datastream TR of fund $i$ with the rebuild only when both
        of the following hold (**pass-and-improve**). The business purpose is
        to rewrite a series only when the rebuild is an independently validated
        repair of a documented shortfall: within Lipper tolerance, and closer
        than the series it displaces. A rebuild that still fails Lipper is not
        adopted, even if it narrows the gap. A rebuild that passes but leaves
        Datastream closer to Lipper is also refused, so that an already
        consistent Datastream TR is not swapped for an equally admissible but
        worse alternative.

        1. **Pass.** On the rebuild's primary horizon $h^*_i$,
           $\left|\tilde g_i^{(h^*_i)}\right| \le \tau$.
        2. **Improve.** On shared horizons from longest to shortest,
           $\left|\tilde g_i^{(h)}\right| < \left|g_i^{(h)}\right|$ on the first
           comparable horizon. Ties fall through to the next shorter horizon; a
           worse gap on the first comparable horizon refuses adoption. If no
           shared horizon exists, the rebuild is refused.

        Two further provisions apply:

        - **No-distribution veto.** If neither Yahoo nor FMP supplies any cash
          distribution for the fund, and the fund is not index-like under the
          definition in §6.3.3, the rebuild is never adopted, whatever the
          comparison says. Index-like funds may still be scored after the
          missed-ex-date fill of §6.3.3.
        - **Retention.** No fund is removed from the panel at this step. Only
          the TR series (daily % return and TR level) of adopting funds is
          replaced. Funds that still fail Lipper on the series used after the
          Decision remain in the working sample; each tested fund receives a
          **Lipper fail after Step 6** flag (`lipper_fail_after`) for later
          robustness (§6.5–§6.6).

        ### 6.4 Outputs

        For each fund the Result gives the 3-, 5- and 10-year gaps of both the
        Datastream TR and the rebuild, the scoring horizon, and the pass/fail
        status. Table 6.3 summarizes the cross-sectional distribution of those
        gaps; Table 6.7 in the appendix lists every fund that still fails Lipper
        after the Decision. The Decision gives the adoption outcome and a
        counterfactual under a looser pass-only rule (§6.6). Pass and adoption
        counts at alternate $\tau$ are in Table 6.4.
        """),
    )
    _decision_policy = md(r"""
        ### 6.6 Decision

        Every series is retained. The pass-and-improve rule of §6.3.4 is applied
        subject to the no-distribution veto, with all horizons evaluated through
        30 September 2026. Lipper failures are not dropped here; the
        `lipper_fail_after` flag marks series that remain outside tolerance on
        the TR used in later steps.
        """)
    _rebuild = get_rebuild()
    if _rebuild is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to score Datastream and rebuilt TR "
                "against Lipper 3y / 5y / 10y._"
            ),
            decision=stack(
                _decision_policy,
                mo.md("_Decision pending until this step has run._"),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. No identifier or "
                    f"series is removed until this step has run."
                ),
            ),
        )
    else:
        from helpers.timeseries_functions.rebuild_tr_from_distributions import (
            LIPPER_CLOSE_PP as _LIPPER_CLOSE_PP,
            annotate_rebuild_log_lipper_status as _annotate_rebuild_log,
            summarize_lipper_gap_distribution as _summarize_gap_distribution,
            summarize_lipper_tolerance_sensitivity as _summarize_tau_sensitivity,
            summarize_rebuild_gate_transparency as _summarize_rebuild_gate,
        )

        _rebuild_log = _rebuild["rebuild_log"].copy()
        if (
            len(_rebuild_log)
            and "lipper_fail_after" not in _rebuild_log.columns
        ):
            _rebuild_log = _annotate_rebuild_log(
                _rebuild_log, close_pp=_LIPPER_CLOSE_PP
            )
        _n_tested = int(len(_rebuild_log))
        _adopted = (
            int(_rebuild_log["decision"].eq("adopted").sum()) if _n_tested else 0
        )
        _kept = _n_tested - _adopted

        def _fmt_gap(value) -> str:
            if value is None or (isinstance(value, float) and value != value):
                return "—"
            try:
                if pd.isna(value):
                    return "—"
            except (TypeError, ValueError):
                return "—"
            return f"{float(value):.2f}"

        def _outcome_label(decision: str) -> str:
            return (
                "rebuild adopted"
                if str(decision).strip() == "adopted"
                else "Datastream retained"
            )

        if _n_tested and "datastream_vs_lipper" in _rebuild_log.columns:
            _ds_pass = int((_rebuild_log["datastream_vs_lipper"] == "pass").sum())
            _ds_fail = int((_rebuild_log["datastream_vs_lipper"] == "fail").sum())
            _ds_unscored = int(
                (_rebuild_log["datastream_vs_lipper"] == "unscored").sum()
            )
            _rb_pass = int((_rebuild_log["rebuild_vs_lipper"] == "pass").sum())
            _rb_fail = int((_rebuild_log["rebuild_vs_lipper"] == "fail").sum())
            _rb_unscored = int((_rebuild_log["rebuild_vs_lipper"] == "unscored").sum())
            _sorted_shortfall = _rebuild_log.sort_values(
                "gap_10y_before", ascending=True, na_position="last"
            )
            _n_fail_after = int(_rebuild_log["lipper_fail_after"].sum())
            _n_pass_after = int(
                (_rebuild_log["lipper_status_after"] == "pass").sum()
            )
            _n_unscored_after = int(
                (_rebuild_log["lipper_status_after"] == "unscored").sum()
            )
            _n_dual_fail = int(_rebuild_log["lipper_dual_fail"].sum())
        else:
            _ds_pass = _ds_fail = _ds_unscored = 0
            _rb_pass = _rb_fail = _rb_unscored = 0
            _sorted_shortfall = _rebuild_log
            _n_fail_after = _n_pass_after = _n_unscored_after = _n_dual_fail = 0

        _n_scored = _ds_pass + _ds_fail
        _ds_pass_pct = 100.0 * _ds_pass / _n_scored if _n_scored else 0.0
        _ds_fail_pct = 100.0 * _ds_fail / _n_scored if _n_scored else 0.0
        _rb_pass_pct = 100.0 * _rb_pass / _n_scored if _n_scored else 0.0

        _summary_table = pd.DataFrame(
            [
                {
                    "Series": "Datastream TR",
                    "Pass": _ds_pass,
                    "Fail": _ds_fail,
                    "Unscored": _ds_unscored,
                    "Total tested": _n_tested,
                },
                {
                    "Series": "Distribution rebuild",
                    "Pass": _rb_pass,
                    "Fail": _rb_fail,
                    "Unscored": _rb_unscored,
                    "Total tested": _n_tested,
                },
            ]
        )

        _gap_dist_raw = (
            _summarize_gap_distribution(_rebuild_log)
            if _n_tested and "gap_10y_before" in _rebuild_log.columns
            else pd.DataFrame()
        )
        _gap_dist_table = _gap_dist_raw.copy()
        for _qcol in ("median", "p10", "p25", "p75", "p90"):
            if _qcol in _gap_dist_table.columns:
                _gap_dist_table[_qcol] = _gap_dist_table[_qcol].map(
                    lambda v, _c=_qcol: (
                        f"{float(v):.2f}"
                        if pd.notna(v)
                        else "—"
                    )
                )

        _deferred_error_tickers = []
        for _row in _sorted_shortfall.itertuples(index=False):
            _row_s = pd.Series(_row._asdict())
            _g3 = _row_s.get("gap_3y_before")
            _g10 = _row_s.get("gap_10y_before")
            _ticker = _row_s.get("ticker")
            if (
                pd.notna(_g3)
                and pd.notna(_g10)
                and abs(float(_g3)) <= 0.05
                and float(_g10) <= -40.0
                and _ticker is not None
                and pd.notna(_ticker)
            ):
                _deferred_error_tickers.append(str(_ticker).strip())
            if len(_deferred_error_tickers) >= 2:
                break

        if "ticker" in _rebuild_log.columns and len(_rebuild_log):
            _mspix = _rebuild_log.loc[
                _rebuild_log["ticker"].astype("string").str.upper().eq("MSPIX")
            ]
        else:
            _mspix = _rebuild_log.iloc[0:0]
        _mspix_note = ""
        if len(_mspix):
            _m = _mspix.iloc[0]
            _mspix_note = (
                f" MSPIX is an S&P 500 index fund, so its true gap to Lipper "
                f"should be close to zero. It shows a "
                f"{_fmt_gap(_m.get('gap_10y_before'))} pp Datastream gap and a "
                f"{_fmt_gap(_m.get('gap_10y_after'))} pp rebuild gap, which "
                f"suggests that neither series is reliable for these funds in "
                f"its current form."
            )

        _rebuild_pass_phrase = (
            f"a single fund ({_rb_pass_pct:.1f}%)"
            if _rb_pass == 1
            else f"{_rb_pass:,} funds ({_rb_pass_pct:.1f}%)"
        )
        if _rb_pass > _ds_pass:
            _compare_md = (
                f"The distribution rebuild matches Lipper far more often: it "
                f"passes for {_rebuild_pass_phrase} and fails for {_rb_fail:,} "
                f"({(100.0 * _rb_fail / _n_scored) if _n_scored else 0.0:.1f}% "
                f"of scorable funds)."
            )
        elif _rb_pass < _ds_pass:
            _compare_md = (
                f"The distribution rebuild does worse: it passes for "
                f"{_rebuild_pass_phrase} and fails for {_rb_fail:,}."
            )
        else:
            _compare_md = (
                f"The distribution rebuild passes for {_rebuild_pass_phrase} "
                f"and fails for {_rb_fail:,}."
            )

        _gap_narrative = ""
        if len(_gap_dist_raw):
            _ds_10y_row = _gap_dist_raw.loc[
                (_gap_dist_raw["Series"] == "Datastream TR")
                & (_gap_dist_raw["Horizon"] == "10y")
            ]
            _rb_10y_row = _gap_dist_raw.loc[
                (_gap_dist_raw["Series"] == "Distribution rebuild")
                & (_gap_dist_raw["Horizon"] == "10y")
            ]
            if len(_ds_10y_row):
                _d = _ds_10y_row.iloc[0]
                _gap_narrative = (
                    f"Table 6.3 summarizes the cross-section of Lipper gaps. "
                    f"Over 10 years the Datastream TR lies a median "
                    f"{float(_d['median']):.1f} pp below Lipper (10th–90th "
                    f"percentile: {float(_d['p10']):.1f} to "
                    f"{float(_d['p90']):.1f} pp), consistent with the "
                    f"missed-reinvestment pattern in §6.2."
                )
                if len(_rb_10y_row):
                    _r = _rb_10y_row.iloc[0]
                    _gap_narrative += (
                        f" The rebuild candidate is tighter: median "
                        f"{float(_r['median']):.1f} pp "
                        f"({float(_r['p10']):.1f} to {float(_r['p90']):.1f} pp)."
                    )
        if _deferred_error_tickers:
            _tickers_txt = ", ".join(_deferred_error_tickers)
            _gap_narrative += (
                f" In {'two cases' if len(_deferred_error_tickers) == 2 else 'some cases'} "
                f"({_tickers_txt}) the 3-year gap is essentially zero while the "
                f"10-year gap is below −40 pp, which places the reinvestment "
                f"errors mainly in the older part of the history."
            )
        if _n_dual_fail and _n_tested:
            _gap_narrative += (
                f" {_n_dual_fail:,} fund"
                f"{'' if _n_dual_fail == 1 else 's'} fail Lipper on both the "
                f"Datastream TR and the rebuild; pass-and-improve keeps them "
                f"on Datastream (Table 6.7)."
            )

        _fail_after_rows = []
        if _n_tested and "lipper_fail_after" in _rebuild_log.columns:
            _fail_after_log = _rebuild_log.loc[
                _rebuild_log["lipper_fail_after"].astype(bool)
            ].sort_values(
                "lipper_gap_after_pp",
                key=lambda s: s.abs(),
                ascending=False,
                na_position="last",
            )
            for _row in _fail_after_log.itertuples(index=False):
                _row_s = pd.Series(_row._asdict())
                _ticker = _row_s.get("ticker")
                _fail_after_rows.append(
                    {
                        "Ticker": (
                            str(_ticker).strip()
                            if _ticker is not None
                            and pd.notna(_ticker)
                            and str(_ticker).strip()
                            else "—"
                        ),
                        "ISIN": str(_row_s.get("isin", "—")),
                        "Horizon": _row_s.get("lipper_horizon_after", "—"),
                        "Gap (pp)": _fmt_gap(_row_s.get("lipper_gap_after_pp")),
                        "DS 10y gap": _fmt_gap(_row_s.get("gap_10y_before")),
                        "Rebuild 10y gap": _fmt_gap(_row_s.get("gap_10y_after")),
                        "Outcome": _outcome_label(_row_s.get("decision")),
                    }
                )
        _fail_after_table = pd.DataFrame(_fail_after_rows)

        if _n_tested:
            _result_paras = [
                "### 6.5 Results",
                (
                    f"Of the {_n_tested:,} funds tested, {_n_scored:,} could be "
                    f"scored against Lipper and {_ds_unscored:,} were unscored "
                    f"(Table 6.2). On the scorable funds, the Datastream TR "
                    f"matches Lipper within {_LIPPER_CLOSE_PP:g} pp for "
                    f"{_ds_pass:,} funds ({_ds_pass_pct:.1f}%) and fails for "
                    f"{_ds_fail:,} ({_ds_fail_pct:.1f}%). {_compare_md}"
                ),
                (
                    "Nearly all unscored funds have no Lipper performance "
                    "figure on any of the three horizons. A few have less than "
                    "three years of daily history."
                ),
            ]
            if _gap_narrative.strip():
                _result_paras.append(_gap_narrative.strip())
            if _n_fail_after:
                _result_paras.append(
                    f"After the Decision, **{_n_fail_after:,}** of "
                    f"{_n_tested:,} funds still fail Lipper on the total-return "
                    f"series used in later steps ({_n_pass_after:,} pass, "
                    f"{_n_unscored_after:,} unscored). They are retained in the "
                    f"panel and listed in Table 6.7."
                    + (_mspix_note if _mspix_note else "")
                )
            _result_md = md("\n\n".join(_result_paras))
        else:
            _result_md = md(
                "### 6.5 Results\n\nNo funds were tested on this run."
            )

        _tau_sens = _summarize_tau_sensitivity(
            _rebuild_log, close_pp_values=(0.25, 0.5, 1.0)
        )
        _tau_sens_table = pd.DataFrame(
            [
                {
                    "τ (pp)": (
                        f"{float(row.tau_pp):g}"
                        + (
                            " (production)"
                            if abs(float(row.tau_pp) - _LIPPER_CLOSE_PP) < 1e-12
                            else ""
                        )
                    ),
                    "Datastream pass": int(row.datastream_pass),
                    "Rebuild pass": int(row.rebuild_pass),
                    "Would adopt (pass-and-improve)": int(row.would_adopt),
                }
                for row in _tau_sens.itertuples(index=False)
            ]
        ) if len(_tau_sens) else pd.DataFrame()
        _tau_by = {
            float(row.tau_pp): row for row in _tau_sens.itertuples(index=False)
        }
        _tau_025 = _tau_by.get(0.25)
        _tau_10 = _tau_by.get(1.0)
        if _tau_025 is not None and _tau_10 is not None and _n_tested:
            _tau_sens_md = md(
                "\n\n".join(
                    [
                        (
                            f"**Sensitivity ($\\tau$).** Repeating the same "
                            f"pass/fail screen and the pass-and-improve gate at "
                            f"$\\tau = 0.25$ pp and $\\tau = 1$ pp leaves the "
                            f"qualitative picture unchanged (Table 6.4). At "
                            f"$0.25$ pp, {_tau_025.datastream_pass:,} Datastream "
                            f"and {_tau_025.rebuild_pass:,} rebuild series pass, "
                            f"and {_tau_025.would_adopt:,} fund"
                            f"{'' if _tau_025.would_adopt == 1 else 's'} would "
                            f"adopt. At $1$ pp the counts are "
                            f"{_tau_10.datastream_pass:,}, "
                            f"{_tau_10.rebuild_pass:,} and "
                            f"{_tau_10.would_adopt:,} respectively. Production "
                            f"keeps $\\tau = {_LIPPER_CLOSE_PP:g}$ pp "
                            f"(§6.3.2)."
                        ),
                    ]
                )
            )
        else:
            _tau_sens_md = mo.md(
                "_Table 6.4 — empty τ sensitivity on this run._"
            )

        _gate_summary, _adopted_still_fail = _summarize_rebuild_gate(
            _rebuild_log, close_pp=_LIPPER_CLOSE_PP
        )
        _adoption_table = pd.DataFrame(
            [
                {" ": "Rebuild adopted (pass and improve)", "Funds": _adopted},
                {
                    " ": (
                        f"— of which pass Lipper "
                        f"(≤ {_LIPPER_CLOSE_PP:g} pp)"
                    ),
                    "Funds": int(_gate_summary["adopted_pass"]),
                },
                {
                    " ": "— of which still fail Lipper",
                    "Funds": int(_gate_summary["adopted_fail"]),
                },
                {" ": "Datastream TR retained", "Funds": _kept},
                {" ": "Total tested", "Funds": _n_tested},
            ]
        )

        _fail_adopt_rows = []
        if len(_adopted_still_fail):
            _fail_sorted = _adopted_still_fail.sort_values(
                "gap_primary_after_pp", ascending=False, na_position="last"
            )
            for _row in _fail_sorted.itertuples(index=False):
                _row_s = pd.Series(_row._asdict())
                _ticker = _row_s.get("ticker")
                _fail_adopt_rows.append(
                    {
                        "Ticker": (
                            str(_ticker).strip()
                            if _ticker is not None
                            and pd.notna(_ticker)
                            and str(_ticker).strip()
                            else "—"
                        ),
                        "Rebuild 10y gap": _fmt_gap(
                            _row_s.get("gap_primary_after_pp")
                        ),
                    }
                )
        _fail_adopt_table = pd.DataFrame(_fail_adopt_rows)

        _n_fail_adopt = int(_gate_summary["adopted_fail"])
        if _adopted == 0:
            _adopt_narrative = (
                "No fund adopts the distribution rebuild under the "
                "pass-and-improve rule on this run."
            )
        elif _n_fail_adopt == 0:
            _adopt_narrative = (
                f"All {_adopted:,} adoption"
                f"{'' if _adopted == 1 else 's'} pass Lipper "
                f"(≤ {_LIPPER_CLOSE_PP:g} pp) and improve on the Datastream "
                f"gap on the primary comparable horizon."
            )
        else:
            _adopt_narrative = (
                f"Of the {_adopted:,} adoptions, "
                f"{int(_gate_summary['adopted_pass']):,} pass Lipper and "
                f"{_n_fail_adopt:,} still fail. Under pass-and-improve a "
                f"failing adopt should not occur; Table 6.6 lists them for "
                f"audit."
            )

        _pass_only_extra = int(_gate_summary.get("pass_only_extra", 0))
        _pass_only_n = int(_gate_summary["strict_would_adopt"])
        _pass_only_keep_n = int(_gate_summary["strict_would_keep"])
        _pass_only_phrase = (
            f"{_pass_only_n:,} fund would adopt"
            if _pass_only_n == 1
            else f"{_pass_only_n:,} funds would adopt"
        )
        if _pass_only_extra == 0:
            _sensitivity_overlap = (
                "On this run the looser rule selects the same adoption set as "
                "production. "
            )
        elif _pass_only_extra == 1:
            _sensitivity_overlap = (
                "That looser rule would add **1** further fund where the "
                "rebuild passes Lipper but does not improve on Datastream. "
            )
        else:
            _sensitivity_overlap = (
                f"That looser rule would add **{_pass_only_extra:,}** further "
                f"funds where the rebuild passes Lipper but does not improve "
                f"on Datastream. "
            )
        _robustness_md = ""
        if _n_tested and _n_fail_after:
            _robustness_md = (
                f"**Robustness (not applied here).** A thesis regression sample "
                f"that drops Lipper failures would exclude the "
                f"**{_n_fail_after:,}** funds flagged `lipper_fail_after` and "
                f"retain **{_n_pass_after:,}** funds that pass on the "
                f"post-Decision series. This notebook keeps the full panel for "
                f"Steps 7–11; the flag is recorded on the rebuild log for "
                f"downstream use."
            )
        _decision_outcomes = md(
            "\n\n".join(
                [
                    p
                    for p in (
                        (
                            f"Of the {_n_tested:,} funds tested, **{_adopted:,} adopt "
                            f"the distribution rebuild** and **{_kept:,} retain the "
                            f"Datastream TR** unchanged (Table 6.5)."
                        ),
                        _adopt_narrative.strip(),
                        _robustness_md.strip() if _robustness_md else "",
                        (
                            "**Sensitivity (not applied).** A looser **pass-only** "
                            "rule would adopt whenever the rebuild already passes "
                            "Lipper, without requiring improvement on Datastream. "
                            f"Under that rule {_pass_only_phrase} and "
                            f"{_pass_only_keep_n:,} would retain the Datastream TR. "
                            f"{_sensitivity_overlap}"
                            "The panel uses pass-and-improve. The counterfactual "
                            "is reported only to show how much the adoption "
                            "decision depends on requiring improvement."
                        ),
                    )
                    if p
                ]
            )
        )

        _exit_md = mo.md(
            f"**Sample at exit.** {_sample_phrase}. No identifier or series is "
            f"removed. The TR series of {_adopted:,} fund"
            f"{'' if _adopted == 1 else 's'} "
            f"{'is' if _adopted == 1 else 'are'} replaced by "
            f"{'its' if _adopted == 1 else 'their'} distribution rebuild"
            f"{'' if _adopted == 1 else 's'}."
            if _adopted
            else (
                f"**Sample at exit.** {_sample_phrase}. No identifier or series "
                f"is removed. No TR series is replaced."
            )
        )
        _impl_note = md(
            """
            *Implementation note.* Tolerance constant `LIPPER_CLOSE_PP`.
            Reference date shared with `regress_daily_to_benchmark.py`. Rebuild
            and adoption logic in
            `helpers/timeseries_functions/rebuild_tr_from_distributions.py`.
            """
        )

        _result_parts = [
            _result_md,
            review_table(
                _summary_table,
                "Table 6.2 — Lipper consistency test (longest available "
                f"horizon, τ = {_LIPPER_CLOSE_PP:g} pp)",
            ),
        ]
        if len(_gap_dist_table):
            _result_parts.append(
                review_table(
                    _gap_dist_table,
                    "Table 6.3 — Distribution of Lipper gaps by horizon (pp; "
                    "computed minus published)",
                )
            )
        else:
            _result_parts.append(
                mo.md("_Table 6.3 — empty on this run._")
            )
        _result_parts.extend(
            [
                _tau_sens_md,
                (
                    review_table(
                        _tau_sens_table,
                        "Table 6.4 — Sensitivity of Lipper pass counts and "
                        "pass-and-improve adoption to τ",
                    )
                    if len(_tau_sens_table)
                    else mo.md("_Table 6.4 — empty on this run._")
                ),
            ]
        )
        if len(_fail_after_table):
            _appendix_label = (
                f"Appendix — funds still failing Lipper after Decision "
                f"({_n_fail_after:,})"
            )
            _appendix_body = stack(
                md(
                    f"Table 6.7 lists every fund with `lipper_fail_after` "
                    f"after §6.6. Gap (pp) is on the primary Lipper horizon for "
                    f"the TR series carried forward (rebuild if adopted, "
                    f"Datastream if retained)."
                ),
                mo.ui.table(
                    _fail_after_table,
                    label=(
                        f"Table 6.7 — Funds still failing Lipper after Decision "
                        f"({_n_fail_after:,})"
                    ),
                    selection=None,
                    pagination=len(_fail_after_table) > 25,
                    page_size=25,
                    max_height=480,
                ),
            )
            _result_parts.append(
                mo.accordion({_appendix_label: _appendix_body}, multiple=True)
            )
        else:
            _result_parts.append(
                mo.md(
                    "_Table 6.7 — empty: every fund passes Lipper on the "
                    "post-Decision series, or none were tested._"
                )
            )

        _decision_parts = [
            _decision_policy,
            _decision_outcomes,
            review_table(
                _adoption_table,
                "Table 6.5 — Adoption outcome and Lipper status of adopted "
                "rebuilds",
            ),
        ]
        if len(_fail_adopt_table):
            _decision_parts.append(
                review_table(
                    _fail_adopt_table,
                    "Table 6.6 — Adopted rebuilds still failing Lipper "
                    f"(10-year rebuild gap, pp; first 12 of "
                    f"{len(_fail_adopt_table):,})",
                )
            )
        else:
            _decision_parts.append(
                mo.md(
                    "_Table 6.6 — empty: under pass-and-improve, no adopted "
                    "rebuild fails Lipper on the primary horizon._"
                )
            )
        _decision_parts.extend([_exit_md, _impl_note])

        _step_view = step_sections(
            documentation=_documentation,
            result=stack(*_result_parts),
            decision=stack(*_decision_parts),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_rebuild, run_step_button, step_header):
    _ready = get_rebuild() is not None
    run_spike = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 6 first")
    _header = step_header("## 7. Spike", run_spike)
    _header
    return (run_spike,)


@app.cell
def _(
    catalog,
    enable_scale_shift,
    get_rebuild,
    repair_distribution_day_tr,
    run_spike,
    set_spike,
    summarize_tr_consistency,
):
    if run_spike.value:
        _rebuild = get_rebuild()
        if _rebuild is None:
            raise ValueError("Spike step requires rebuild output")
        _observations = _rebuild["observations"]
        _controls, _issue_summary, _checks = summarize_tr_consistency(
            catalog,
            _observations,
            flags=("spikes",),
            use_scale=enable_scale_shift.value,
        )
        _repaired, _distribution_log = repair_distribution_day_tr(catalog, _observations)
        set_spike(
            {
                "observations": _repaired,
                "controls": _controls,
                "issue_summary": _issue_summary,
                "checks": _checks,
                "distribution_log": _distribution_log,
            }
        )
    return


@app.cell
def _(
    catalog,
    flag_summary_table,
    get_rebuild,
    get_spike,
    md,
    mo,
    pd,
    review_table,
    stack,
    step_sections,
):
    mo.stop(
        get_rebuild() is None,
        mo.md("Run step 6 first."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _sample_phrase = (
        f"{_n_ids:,} fund and index identifiers ({_n_cols:,} series)"
    )

    def _fund_display_name(isin: str) -> str:
        names = catalog.loc[
            catalog["id"].astype("string").str.strip().eq(isin), "name"
        ].astype("string")
        label = str(names.iloc[0]) if len(names) else isin
        for _suffix in (
            " - TOT RETURN IND",
            " - PRICE",
            " - TOTAL NET ASSETS",
        ):
            if label.endswith(_suffix):
                return label[: -len(_suffix)]
        return label

    def _category_for(isin: str) -> str:
        cats = catalog.loc[
            catalog["id"].astype("string").str.strip().eq(isin), "category"
        ].astype("string")
        return str(cats.iloc[0]) if len(cats) else "—"

    def _fmt_pct(value, digits: int = 2) -> str:
        if value is None or (isinstance(value, float) and value != value):
            return "—"
        try:
            if pd.isna(value):
                return "—"
        except (TypeError, ValueError):
            return "—"
        return f"{100.0 * float(value):+.{digits}f}%"

    _documentation = stack(
        mo.md(f"**Sample at entry.** {_sample_phrase}."),
        md(r"""
        ### 7.1 Objective

        This step screens the fund total-return series for abnormal single-day
        returns, called spikes, and corrects the ones that are data errors. Most
        of these errors are total-return prints on ex-distribution days. The
        thesis measures performance by regressing daily fund total returns on
        the S&P 500 total return, $m_t$. One erroneous day of ±10% or more can
        dominate the regression residuals and inflate tracking error. Once
        compounded into the total-return index, it also shifts every later level
        of the series. Genuine large moves, however, must be kept: removing them
        would understate risk and bias measured performance.

        ### 7.2 Background: sources of abnormal daily returns

        Three situations produce a daily return of 10% or more in absolute
        value:

        1. **Data spikes.** A single erroneous print that either reverses the
           next day or is not shared by the market.
        2. **Distribution-day errors.** On an ex-distribution date the
           published NAV (price) falls by roughly the cash amount distributed.
           A correct total-return series adds that cash back, so the fund's
           total return on the day stays close to the market's. Defective
           prints take two forms. Either the distribution is not added back, so
           the total return falls with the price, or it is added back at the
           wrong scale, so the total return jumps while the price falls by a few
           percent. Either way, the error is carried into every later
           total-return level.
        3. **Genuine moves.** Large returns in which price and total return
           move together: crash days such as March 2020, payoffs of hedging
           strategies, or lasting jumps in NAV.

        The automated screen (§7.3) targets the first situation. The second is
        handled by a hand-reviewed list (§7.4), because many distribution-day
        errors fall below the spike threshold. The third is retained.

        ### 7.3 Detection rule (Result)

        Let $r_{i,t}$ be the daily total return of fund $i$ on day $t$,
        $p_{i,t}$ its price (NAV) return and $m_t$ the S&P 500 total return
        (`S&P 500 TR %`). The spike threshold is $\theta = 10\%$ and the
        reversal band is $\beta = 15\%$.

        A day is a **reversal spike** if

        $$
        |r_{i,t}| \ge \theta, \qquad r_{i,t}\, r_{i,t+1} < 0, \qquad
        \bigl|(1+r_{i,t})(1+r_{i,t+1}) - 1\bigr| \le \beta,
        $$

        and the S&P 500 does not show the same reversal, that is, it is not the
        case that $|m_t| \ge 5\%$ and $m_t\, m_{t+1} < 0$.

        A day is an **isolated spike** if

        $$
        |r_{i,t}| \ge \theta \qquad \text{and} \qquad
        |r_{i,t} - m_t| \ge \tfrac{1}{2}\,|r_{i,t}|.
        $$

        For example, a fund return of +12% on a day the S&P 500 gains 1% is an
        isolated spike ($|12 - 1| = 11 \ge 6$). A fund return of +12% followed
        by −11% is a reversal spike: the two-day return is −0.3%.

        **Suppressions.** A day is not flagged when (i) it has already been
        flagged as a persistent level shift in §5 (always applied); (ii) it
        falls on or after a re-detected scale-shift split, which applies only
        when the optional scale-shift step (§4) is enabled; or (iii) it is the
        second day of a reversal pair, so each pair counts once.

        The screen scores the total-return series as they enter the step,
        before any correction from §7.4, and does not re-score them afterwards.
        Its flags are diagnostic only and never modify the data.[^1]

        ### 7.4 Correction rule (Decision)

        Corrections come from a curated list of reviewed fund-days. Each entry
        is marked either for repair or for retention.

        **Eligibility gate.** A curated repair is applied only if both
        conditions still hold on the current panel, after the Yahoo replacement
        and rebuild of §1:

        $$
        |r_{i,t} - p_{i,t}| \ge 1\% \qquad \text{and} \qquad
        |r_{i,t} - m_t| \ge 1\%.
        $$

        The first condition requires total return and price to disagree by more
        than rounding. The second requires the total return to depart from the
        market as well. A correctly recorded ex-distribution day (price down,
        total return close to the market) fails the second condition and is
        logged as *already clean*. Curated days that are no longer in the panel
        are skipped.

        **Forward repair (S&P 500 proxy).** This is used when the error is
        carried into later levels. On the defective day $t^*$, the fund's total
        return is replaced by the market return, and every later level is
        rescaled by the same factor:

        $$
        \tilde r_{i,t^*} = m_{t^*}, \qquad
        \widetilde{TR}_{i,s} = TR_{i,s}\,\frac{1+m_{t^*}}{1+r_{i,t^*}}
        \quad (s \ge t^*).
        $$

        Returns after $t^*$ are unchanged.

        **One-day repair.** This is used when the spike reverses the next day
        and later levels are already correct. The day's return is replaced by
        the fund's own price return, and the next return is recomputed so that
        the level from $t^*+1$ onward is preserved:

        $$
        \tilde r_{i,t^*} = p_{i,t^*}, \qquad
        \tilde r_{i,t^*+1} =
        \frac{(1+r_{i,t^*})(1+r_{i,t^*+1})}{1+p_{i,t^*}} - 1 .
        $$

        **Choice of proxy.** For the forward cases, no confirmed distribution
        amount is available that would allow the total return to be rebuilt from
        NAV and cash. On a distribution day, index-like and broad equity funds
        track the market within a few percent. Substituting the S&P 500 total
        return for that single session is therefore the correction that assumes
        the least.

        **Retention.** Days on which price and total return move together are
        treated as genuine and logged as *retained*. Result flags without a
        curated entry are left unadjusted.

        ### 7.5 Outputs

        The step produces three tables: the series carrying automated spike
        flags (Table 7.2), a crosswalk by fund between Result and Decision
        (Table 7.3), and the log of reviewed days (Tables 7.4–7.6). The two
        views use different filters, so a fund can appear in either or both
        (Table 7.1).

        In the Decision log the curated raw defect (the Lipper print as first
        documented, often before the Yahoo replacement of §1) is stored
        separately from the outcome note. The outcome is built from the
        decision actually taken and from the current panel values of the fund
        total return, the price return and the S&P 500 total return. A day that
        is skipped as already clean therefore no longer reads as if it had been
        repaired.

        *Table 7.1 — Result↔Decision crosswalk categories*

        | Category | Definition | Typical case |
        |---|---|---|
        | Both | Result flag and curated entry | Genuine large move retained, or spike repaired |
        | Result only | Result flag, no curated entry | Large day not on the curated list; left unadjusted |
        | Decision only | Curated entry, no current Result flag | Distribution-day error below the 10% threshold, or already corrected upstream |

        [^1]: In the notebook, the Result screen calls the shared flagging
        helper with the spike flag only, before the distribution-day repair
        routine runs.
        """),
    )
    _decision_policy = md(r"""
        ### 7.7 Decision

        **All series are kept.** Corrections follow the curated list and the
        eligibility gate of §7.4. Result flags without a curated entry are left
        unadjusted. Days on which price and total return move together are
        retained as genuine moves.
        """)
    _spike = get_spike()
    if _spike is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to score the pre-repair spike screen "
                "(§7.3), apply gated distribution-day repairs (§7.4), and "
                "build the Result↔Decision crosswalk._"
            ),
            decision=stack(
                _decision_policy,
                mo.md("_Decision pending until this step has run._"),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. No series is "
                    f"removed until this step has run."
                ),
            ),
        )
    else:
        _controls = _spike["controls"]
        _spike_table = flag_summary_table(_spike["issue_summary"], "spikes")
        _distribution_log = _spike["distribution_log"].copy()
        _result_isins = set(_spike_table["id"].astype("string").str.strip())
        _distribution_log["in_result_spikes"] = (
            _distribution_log["isin"]
            .astype("string")
            .str.strip()
            .isin(_result_isins)
        )
        _repaired_rows = _distribution_log.loc[
            _distribution_log["decision"].eq("repaired")
        ]
        _skipped_clean = _distribution_log.loc[
            _distribution_log["decision"].eq("skipped — already clean")
        ]
        _kept_rows = _distribution_log.loc[
            _distribution_log["decision"].eq("kept")
        ]
        _adj = _repaired_rows["adjustment"].astype("string")
        _n_forward = int(
            _adj.str.contains("S&P return", regex=False, na=False).sum()
        )
        _n_one_day = int(
            _adj.str.contains("price return", regex=False, na=False).sum()
        )
        _n_already = int(_adj.eq("already matches").sum())
        _n_cells = (
            int(_repaired_rows["cells"].sum()) if len(_repaired_rows) else 0
        )
        _n_spike_days = (
            int(_spike_table["spikes"].sum()) if len(_spike_table) else 0
        )
        _n_spike_series = int(len(_spike_table))
        _n_reviewed = int(len(_distribution_log))
        _n_curated_repairs = (
            int(
                _distribution_log["decision"]
                .isin(["repaired", "skipped — already clean"])
                .sum()
            )
            if len(_distribution_log)
            else 0
        )

        _decision_isins = set(
            _distribution_log["isin"].astype("string").str.strip()
        )
        _cross_rows = []
        for _isin in sorted(_result_isins | _decision_isins):
            _in_result = _isin in _result_isins
            _in_decision = _isin in _decision_isins
            if _in_result and _in_decision:
                _overlap = "Both"
            elif _in_result:
                _overlap = "Result only"
            else:
                _overlap = "Decision only"
            _dec_part = _distribution_log.loc[
                _distribution_log["isin"]
                .astype("string")
                .str.strip()
                .eq(_isin)
            ]
            _spike_count = 0
            if _in_result:
                _spike_count = int(
                    _spike_table.loc[
                        _spike_table["id"]
                        .astype("string")
                        .str.strip()
                        .eq(_isin),
                        "spikes",
                    ].sum()
                )
            _cross_rows.append(
                {
                    "Fund": _fund_display_name(_isin),
                    "ISIN": _isin,
                    "Category": _overlap,
                    "Result spikes": _spike_count,
                    "Repaired": (
                        int(_dec_part["decision"].eq("repaired").sum())
                        if len(_dec_part)
                        else 0
                    ),
                    "Already clean": (
                        int(
                            _dec_part["decision"]
                            .eq("skipped — already clean")
                            .sum()
                        )
                        if len(_dec_part)
                        else 0
                    ),
                    "Retained": (
                        int(_dec_part["decision"].eq("kept").sum())
                        if len(_dec_part)
                        else 0
                    ),
                }
            )
        _crosswalk = pd.DataFrame(_cross_rows)
        if len(_crosswalk):
            _overlap_order = {
                "Both": 0,
                "Result only": 1,
                "Decision only": 2,
            }
            _crosswalk = (
                _crosswalk.assign(
                    _ord=_crosswalk["Category"].map(_overlap_order)
                )
                .sort_values(["_ord", "ISIN"])
                .drop(columns="_ord")
                .reset_index(drop=True)
            )
        _n_both = (
            int((_crosswalk["Category"] == "Both").sum())
            if len(_crosswalk)
            else 0
        )
        _n_result_only = (
            int((_crosswalk["Category"] == "Result only").sum())
            if len(_crosswalk)
            else 0
        )
        _n_decision_only = (
            int((_crosswalk["Category"] == "Decision only").sum())
            if len(_crosswalk)
            else 0
        )
        _n_cross_funds = int(len(_crosswalk))

        _spike_display_rows = []
        for _row in _spike_table.itertuples(index=False):
            _isin = str(_row.id).strip()
            _spike_display_rows.append(
                {
                    "Fund": _fund_display_name(_isin),
                    "ISIN": _isin,
                    "Category": str(_row.category),
                    "Observations": int(_row.days),
                    "Spike days": int(_row.spikes),
                }
            )
        _spike_display = (
            pd.DataFrame(_spike_display_rows).sort_values(
                ["Spike days", "Fund"], ascending=[False, True]
            )
            if _spike_display_rows
            else pd.DataFrame(
                columns=[
                    "Fund",
                    "ISIN",
                    "Category",
                    "Observations",
                    "Spike days",
                ]
            )
        )

        _cat_counts = (
            _spike_display["Category"].value_counts().to_dict()
            if len(_spike_display)
            else {}
        )

        def _cat_phrase(counts: dict) -> str:
            _order = [
                ("Active MF", "active mutual fund"),
                ("Active ETF", "active ETF"),
                ("Passive MF", "passive mutual fund"),
                ("Passive ETF", "passive ETF"),
            ]
            _parts = []
            for _key, _label in _order:
                _n = int(counts.get(_key, 0))
                if _n:
                    _parts.append(f"{_n} {_label}{'s' if _n != 1 else ''}")
            if not _parts:
                return "no flagged funds"
            if len(_parts) == 1:
                return _parts[0]
            if len(_parts) == 2:
                return f"{_parts[0]} and {_parts[1]}"
            return ", ".join(_parts[:-1]) + f" and {_parts[-1]}"

        _flagged_mix = _cat_phrase(_cat_counts)
        _result_only_funds = (
            _crosswalk.loc[
                _crosswalk["Category"].eq("Result only"), "Fund"
            ].tolist()
            if len(_crosswalk)
            else []
        )
        if _n_result_only == 0:
            _both_phrase = (
                f"All {_n_spike_series:,} flagged funds also have a curated "
                f"entry (Table 7.3)."
            )
        elif _n_result_only == 1 and _result_only_funds:
            _both_phrase = (
                f"{_n_both:,} of the {_n_spike_series:,} flagged funds also "
                f"have a curated entry (Table 7.3). The remaining fund, "
                f"{_result_only_funds[0]}, has none and its flagged day is "
                f"left unadjusted."
            )
        else:
            _both_phrase = (
                f"{_n_both:,} of the {_n_spike_series:,} flagged funds also "
                f"have a curated entry; {_n_result_only:,} are Result only "
                f"(Table 7.3)."
            )

        _spike_day_word = "day" if _n_spike_days == 1 else "days"
        _spike_series_word = "series" if _n_spike_series == 1 else "series"
        if _n_spike_series == 0:
            _main_finding = (
                "The screen flags **no spike days** in the fund total-return "
                "series after steps 1–6."
            )
        else:
            _main_finding = (
                f"The screen flags **{_n_spike_days:,} spike {_spike_day_word} "
                f"in {_n_spike_series:,} fund total-return "
                f"{_spike_series_word}** (Table 7.2). The flagged funds are "
                f"{_flagged_mix}."
            )

        _result_md = md(
            f"""
            ### 7.6 Results

            {_main_finding}

            After steps 1–6, large single-day anomalies are therefore rare.
            The flags are diagnostic, so the outcome for each day is set in
            §7.7. {_both_phrase}

            The crosswalk covers {_n_cross_funds:,} fund
            {"s" if _n_cross_funds != 1 else ""}: {_n_both:,} in both views,
            {_n_result_only:,} in Result only and {_n_decision_only:,} in
            Decision only. Controls for this run: $\\theta =$
            {_controls["spike_return"]:.0%}, $\\beta =$
            {_controls["reversal_band"]:.0%}.
            """
        )

        def _row_get(_row, name: str, default=None):
            return getattr(_row, name, default)

        _repaired_display_rows = []
        for _row in _repaired_rows.sort_values(["date", "isin"]).itertuples(
            index=False
        ):
            _adj_txt = str(_row.adjustment)
            if "S&P return" in _adj_txt:
                _repair_label = "Forward (S&P 500 proxy)"
            elif "price return" in _adj_txt:
                _repair_label = "One-day"
            elif _adj_txt == "already matches":
                _repair_label = "Already matches"
            else:
                _repair_label = _adj_txt
            _repaired_display_rows.append(
                {
                    "Fund": str(_row.fund),
                    "Date": str(_row.date),
                    "Repair": _repair_label,
                    "Price return": _fmt_pct(_row_get(_row, "price_return")),
                    "TR before → after": (
                        f"{_fmt_pct(_row.return_before)} → "
                        f"{_fmt_pct(_row.return_after)}"
                    ),
                    "Outcome": str(
                        _row_get(_row, "outcome") or _row_get(_row, "why") or ""
                    ),
                    "Values changed": int(_row.cells),
                }
            )
        _repaired_display = (
            pd.DataFrame(_repaired_display_rows)
            if _repaired_display_rows
            else pd.DataFrame(
                columns=[
                    "Fund",
                    "Date",
                    "Repair",
                    "Price return",
                    "TR before → after",
                    "Outcome",
                    "Values changed",
                ]
            )
        )

        _retained_display_rows = []
        for _row in _kept_rows.sort_values(["date", "isin"]).itertuples(
            index=False
        ):
            _evidence = _row_get(_row, "defect") or _row_get(_row, "why") or ""
            _retained_display_rows.append(
                {
                    "Fund": str(_row.fund),
                    "Date": str(_row.date),
                    "Fund return (price / TR)": (
                        f"{_fmt_pct(_row_get(_row, 'price_return'))} / "
                        f"{_fmt_pct(_row.return_before)}"
                    ),
                    "S&P 500": _fmt_pct(_row_get(_row, "market_return")),
                    "Evidence": str(_evidence),
                }
            )
        _retained_display = (
            pd.DataFrame(_retained_display_rows)
            if _retained_display_rows
            else pd.DataFrame(
                columns=[
                    "Fund",
                    "Date",
                    "Fund return (price / TR)",
                    "S&P 500",
                    "Evidence",
                ]
            )
        )

        _clean_display_rows = []
        for _row in _skipped_clean.sort_values(["date", "isin"]).itertuples(
            index=False
        ):
            _clean_display_rows.append(
                {
                    "Fund": str(_row.fund),
                    "Date": str(_row.date),
                    "Defect as documented": str(
                        _row_get(_row, "defect") or ""
                    ),
                    "Current TR": _fmt_pct(_row.return_before),
                    "Current price": _fmt_pct(
                        _row_get(_row, "price_return")
                    ),
                    "S&P 500": _fmt_pct(_row_get(_row, "market_return")),
                    "Outcome": str(
                        _row_get(_row, "outcome") or _row_get(_row, "why") or ""
                    ),
                }
            )
        _clean_display = (
            pd.DataFrame(_clean_display_rows)
            if _clean_display_rows
            else pd.DataFrame(
                columns=[
                    "Fund",
                    "Date",
                    "Defect as documented",
                    "Current TR",
                    "Current price",
                    "S&P 500",
                    "Outcome",
                ]
            )
        )

        _cell_breakdown = ""
        if len(_repaired_rows) and _n_cells:
            _cell_parts = [
                f"{int(_r.cells):,}"
                for _r in _repaired_rows.sort_values(
                    ["date", "isin"]
                ).itertuples(index=False)
                if int(_r.cells) > 0
            ]
            if _cell_parts:
                _cell_breakdown = " (" + " + ".join(_cell_parts) + ")"

        _decision_outcomes = md(
            f"""
            **All series are kept.** Of the {_n_reviewed:,} reviewed
            fund-day{"s" if _n_reviewed != 1 else ""},
            {len(_repaired_rows):,} {"are" if len(_repaired_rows) != 1 else "is"}
            repaired ({_n_forward:,} forward repair{"s" if _n_forward != 1 else ""},
            {_n_one_day:,} one-day repair{"s" if _n_one_day != 1 else ""}),
            changing {_n_cells:,} values{_cell_breakdown}.
            {len(_skipped_clean):,} curated day{"s" if len(_skipped_clean) != 1 else ""}
            {"are" if len(_skipped_clean) != 1 else "is"} skipped as already
            clean, and {len(_kept_rows):,} genuine large move
            {"s are" if len(_kept_rows) != 1 else " is"} retained
            {f", plus {_n_already:,} already-matching print{'s' if _n_already != 1 else ''}" if _n_already else ""}.

            {len(_skipped_clean):,} of the {_n_curated_repairs:,} curated
            distribution-day error{"s" if _n_curated_repairs != 1 else ""}
            {"are" if len(_skipped_clean) != 1 else "is"} no longer present in
            the current panel, which indicates that the upstream replacement
            and rebuild (§1) had already resolved most of them. The forward
            repairs that remain typically sit below the 10% spike threshold,
            which explains Decision-only cases and why the curated list is
            needed alongside the automated screen. For index funds, the S&P 500
            proxy is close to the correct value by construction.
            """
        )

        _repaired_isins = set(
            _repaired_rows["isin"].astype("string").str.strip()
        ) if len(_repaired_rows) else set()
        _justification_bits = []
        if "US78472P1093" in _repaired_isins:
            _justification_bits.append(
                "*State Street S&P 500 Index Fund N.* The price fell 4.07% "
                "while the recorded total return was +4.85% and the S&P 500 "
                "rose 0.50%. A deviation of 4.35 pp from the index is "
                "implausible for a fund that replicates it, and the pattern "
                "matches a distribution added back at the wrong scale. Both "
                "gate conditions hold (8.92 pp and 4.35 pp). The day is set to "
                "the S&P 500 return and later levels are rescaled."
            )
        if "US85749T7569" in _repaired_isins:
            _justification_bits.append(
                "*State Street Equity 500 Index II Portfolio.* The pattern is "
                "the same: the price fell 1.76%, the total return was +2.37% "
                "and the S&P 500 rose 0.50%. Both gate conditions hold "
                "(4.13 pp and 1.87 pp). The repair is the same forward repair."
            )
        if "US92646A2520" in _repaired_isins:
            _justification_bits.append(
                "*Victory S&P 500 Index Fund A.* On 2024-12-13 the total return "
                "jumped +15.57% while the price was flat and the S&P 500 rose "
                "0.01%. The next session (2024-12-16) both price and total "
                "return fell ≈13% while the S&P 500 rose 0.39%. Victory’s 2024 "
                "distribution notice records a capital-gain distribution of "
                "$4.094 (≈15.57% of NAV) with ex-date 2024-12-13 and pay date "
                "2024-12-16, so the print is a mis-timed distribution: the "
                "add-back landed on the ex-date without the NAV drop, and the "
                "NAV drop on the pay date took the total return with it. Both "
                "gate conditions hold. The two-day total return (+0.43%) shows "
                "that later levels are already correct, so only the ex-date "
                "print is replaced with the price return (0%); the next day’s "
                "return is recomputed and becomes ≈ +0.43%, near the market, "
                "while the price fall of ≈13% remains as the genuine "
                "ex-distribution NAV move."
            )
        if "US0263933063" in _repaired_isins:
            _justification_bits.append(
                "*American Growth Fund B.* The total return jumped 14.60% and "
                "reversed by 12.60% the next day, while the price did not jump "
                "(−0.77%). The two-day return, +0.16%, shows that later levels "
                "are already correct, so only the spike print is replaced. The "
                "day's return becomes the price return (−0.77%) and the next "
                "day's return is recomputed so that the two-day return is "
                "unchanged."
            )
        _decision_justifications = (
            md("\n\n".join(_justification_bits))
            if _justification_bits
            else None
        )

        _exit_md = mo.md(
            f"**Sample at exit.** {_sample_phrase}. No series is removed"
            + (
                f"; values are changed in {len(_repaired_rows):,} series."
                if len(_repaired_rows)
                else "; no values are changed."
            )
        )

        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                _result_md,
                review_table(
                    _spike_display,
                    "Table 7.2 — Series with automated spike flags "
                    "(pre-correction screen; θ = 10%, β = 15%)",
                )
                if len(_spike_display)
                else mo.md(
                    "_Table 7.2 — no series with automated spike flags "
                    "on this run._"
                ),
                review_table(
                    _crosswalk,
                    "Table 7.3 — Result↔Decision crosswalk by fund "
                    "(number of days)",
                )
                if len(_crosswalk)
                else mo.md(
                    "_Table 7.3 — empty Result↔Decision crosswalk on this run._"
                ),
            ),
            decision=stack(
                _decision_policy,
                _decision_outcomes,
                review_table(
                    _repaired_display,
                    "Table 7.4 — Repaired days",
                )
                if len(_repaired_display)
                else mo.md("_Table 7.4 — no repaired days on this run._"),
                review_table(
                    _retained_display,
                    "Table 7.5 — Retained days (genuine moves)",
                )
                if len(_retained_display)
                else mo.md("_Table 7.5 — no retained days on this run._"),
                review_table(
                    _clean_display,
                    "Table 7.6 — Curated days skipped as already clean "
                    "(gate not met on the current panel)",
                )
                if len(_clean_display)
                else mo.md(
                    "_Table 7.6 — no curated days skipped as already clean "
                    "on this run._"
                ),
                _decision_justifications,
                _exit_md,
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_spike, run_step_button, step_header):
    _ready = get_spike() is not None
    run_wide = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 7 first")
    _header = step_header("## 8. Far from index", run_wide)
    _header
    return (run_wide,)


@app.cell
def _(
    catalog,
    drop_identifiers_from_panel,
    get_spike,
    run_wide,
    set_wide,
    summarize_tr_consistency,
):
    if run_wide.value:
        _spike = get_spike()
        if _spike is None:
            raise ValueError("Wide step requires spike output")
        _observations = _spike["observations"]
        _controls, _issue_summary, _checks = summarize_tr_consistency(
            catalog, _observations, flags=("wide",)
        )
        # Score the full entry sample first (Result), then remove thesis
        # sample drops (Decision) so later steps never see those series.
        _kept_catalog, _kept_observations, _sample_drop_log = (
            drop_identifiers_from_panel(catalog, _observations)
        )
        set_wide(
            {
                "observations": _kept_observations,
                "catalog": _kept_catalog,
                "controls": _controls,
                "issue_summary": _issue_summary,
                "checks": _checks,
                "sample_drop_log": _sample_drop_log,
                "entry_catalog": catalog,
                "entry_n_ids": int(catalog["id"].nunique()),
                "entry_n_cols": int(len(catalog)),
            }
        )
    return


@app.cell
def _(
    catalog,
    flag_summary_table,
    get_spike,
    get_wide,
    md,
    mo,
    pd,
    review_table,
    stack,
    step_sections,
):
    mo.stop(
        get_spike() is None,
        mo.md("Run step 7 first."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _sample_phrase = (
        f"{_n_ids:,} fund and index identifiers ({_n_cols:,} series)"
    )
    _documentation = stack(
        mo.md(f"**Sample at entry.** {_sample_phrase}."),
        md(r"""
        ### 8.1 Objective

        This step flags trading days on which a fund's daily total return
        differs from the S&P 500 total return by a large margin. The thesis
        regresses fund returns on the benchmark, so isolated days of extreme
        divergence carry a lot of weight in the estimated coefficients and in
        tracking-error measures. The step checks whether such days remain after
        the corrections of the earlier steps, and how often they occur.

        ### 8.2 Background

        The spike and distribution-day repairs (§7) have already dealt with
        return anomalies caused by data errors. A large gap between fund and
        benchmark that is still present after §7 has two plausible explanations.
        For an active fund, it may be genuine active risk: holdings and weights
        that differ from the index. Otherwise it may be residual tracking
        difference. On daily data a gap of several percentage points is rare.
        This screen is therefore a test for notable days, not a routine
        tracking-error band.

        ### 8.3 Method

        Let $r_{i,t}$ denote the daily total return of series $i$ on day $t$,
        and $m_t$ the daily return of the benchmark `S&P 500 TR %`, both in
        percent. On every day where both returns are observed, define the gap

        $$
        g_{i,t} = r_{i,t} - m_t .
        $$

        **Wide day.** Day $t$ is flagged as wide for series $i$ if

        $$
        \lvert g_{i,t} \rvert \geq \tau, \qquad \tau = 5 \text{ percentage points}.
        $$

        Days on which either return is missing are not tested. For example, a
        fund return of $+6\%$ on a day when the benchmark returns $+0.5\%$ gives
        $\lvert g_{i,t} \rvert = 5.5$ pp $\geq 5$ pp, so the day is flagged as
        wide.

        ### 8.4 Outputs

        The step produces three outputs: (i) the number of wide days for each
        series; (ii) the run-level wide-day rate, defined as the total number of
        wide days divided by the total number of fund-days on which both returns
        are observed; and (iii) a sample-selection log for identifiers removed
        from the working panel after the screen (Table 8.3).
        """),
    )
    _wide = get_wide()
    if _wide is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to score days far from the index (§8.3)._"
            ),
            decision=stack(
                md(r"""
                ### 8.6 Decision

                Wide days that remain after §7 are treated as active risk when
                the series belongs in the S&P 500 total-return sample. Identifiers
                whose official Lipper benchmark is not S&P 500 TR are removed
                from the working selection (Table 8.3); their series are not
                rewritten.
                """),
                mo.md("_Decision pending until this step has run._"),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. No series is "
                    f"removed until this step has run."
                ),
            ),
        )
    else:
        _controls = _wide["controls"]
        _issue_summary = _wide["issue_summary"]
        _checks = _wide["checks"]
        _wide_table = flag_summary_table(_issue_summary, "wide")
        _tau_pp = 100.0 * float(_controls["index_gap"])
        _total_fund_days = (
            sum(int(check.months["usable"].sum()) for check in _checks.values())
            if _checks
            else 0
        )
        _total_wide_days = (
            int(_issue_summary["far_from_index"].sum())
            if len(_issue_summary)
            else 0
        )
        _wide_rate_pct = (
            100.0 * _total_wide_days / _total_fund_days
            if _total_fund_days
            else float("nan")
        )
        _wide_rate_txt = (
            f"{_wide_rate_pct:.3f}%" if _total_fund_days else "—"
        )
        _n_wide_series = int(len(_wide_table))
        _n_multi = (
            int((_wide_table["far_from_index"] >= 2).sum())
            if len(_wide_table)
            else 0
        )
        _n_single = _n_wide_series - _n_multi
        _cat = (
            _wide_table["category"].astype("string")
            if len(_wide_table)
            else pd.Series(dtype="string")
        )
        _n_passive_wide = int(
            _cat.str.contains("Passive", case=False, na=False).sum()
        )
        _n_active_wide = _n_wide_series - _n_passive_wide
        if _n_wide_series == 0:
            _class_phrase = (
                "No series has a day with a gap of "
                f"{_tau_pp:.0f} pp or more."
            )
        elif _n_passive_wide == 0:
            _class_phrase = (
                f"They fall on **{_n_wide_series:,} series**, and every "
                f"flagged series belongs to an active share class (active ETF "
                f"or active mutual fund). No passive series has a single day "
                f"with a gap of {_tau_pp:.0f} pp or more. This is consistent "
                f"with tight index replication by the passive funds once §7 "
                f"has been applied."
            )
        else:
            _class_phrase = (
                f"They fall on **{_n_wide_series:,} series** "
                f"({_n_active_wide:,} active, {_n_passive_wide:,} passive)."
            )

        _multi = (
            _wide_table.loc[_wide_table["far_from_index"] >= 2]
            .sort_values(["far_from_index", "id"], ascending=[False, True])
            .reset_index(drop=True)
            if len(_wide_table)
            else _wide_table
        )
        _multi_wide_days = (
            int(_multi["far_from_index"].sum()) if len(_multi) else 0
        )
        _multi_display = (
            pd.DataFrame(
                {
                    "Identifier": _multi["id"].astype("string").str.strip(),
                    "Class": _multi["category"].astype("string"),
                    "Observations": _multi["days"].astype(int),
                    "Wide days": _multi["far_from_index"].astype(int),
                }
            )
            if len(_multi)
            else pd.DataFrame(
                columns=["Identifier", "Class", "Observations", "Wide days"]
            )
        )

        if _n_wide_series == 0:
            _concentration = (
                "No series carries two or more wide days on this run."
            )
        elif _n_multi == 0:
            _concentration = (
                f"Each of the {_n_wide_series:,} flagged series has exactly "
                f"one wide day."
            )
        else:
            _concentration = (
                f"Wide days are concentrated in a few series. Table 8.2 lists "
                f"the {_n_multi:,} series with two or more wide days. Together "
                f"they account for {_multi_wide_days:,} of the "
                f"{_total_wide_days:,} wide days. Each of the other "
                f"{_n_single:,} series has one wide day."
            )

        _result_md = md(
            f"""
            ### 8.5 Results

            Wide days are very rare. Out of {_total_fund_days:,} fund-days
            tested, {_total_wide_days:,} are wide ({_wide_rate_txt}).
            {_class_phrase}

            *Table 8.1 — Summary of the far-from-index screen*

            | Quantity | Value |
            |---|---|
            | Gap threshold $\\tau$ | {_tau_pp:.0f} pp |
            | Fund-days tested | {_total_fund_days:,} |
            | Wide days | {_total_wide_days:,} |
            | Wide-day rate | {_wide_rate_txt} |
            | Series with at least one wide day | {_n_wide_series:,} |
            | of which with two or more wide days | {_n_multi:,} |
            | of which with exactly one wide day | {_n_single:,} |

            {_concentration}
            """
        )
        _table_note = md(
            r"""
            *Note:* all series are daily total return indices. "Observations"
            is the number of daily observations reported for the series.
            """
        )
        _drop_log = _wide.get("sample_drop_log")
        if _drop_log is None or not len(_drop_log):
            _drop_log = pd.DataFrame(
                columns=[
                    "isin",
                    "ticker",
                    "name",
                    "fund_type",
                    "benchmark_ticker",
                    "benchmark_name",
                    "series_removed",
                    "present",
                    "reason",
                ]
            )
        _dropped = _drop_log.loc[_drop_log["present"].astype(bool)].copy()
        _n_dropped_ids = int(len(_dropped))
        _n_dropped_series = (
            int(_dropped["series_removed"].sum()) if len(_dropped) else 0
        )
        _kept_catalog = _wide.get("catalog", catalog)
        _exit_n_ids = int(_kept_catalog["id"].nunique())
        _exit_n_cols = int(len(_kept_catalog))
        _exit_phrase = (
            f"{_exit_n_ids:,} fund and index identifiers "
            f"({_exit_n_cols:,} series)"
        )

        _drop_display = (
            pd.DataFrame(
                {
                    "Identifier": _dropped["isin"].astype("string"),
                    "Ticker": _dropped["ticker"].astype("string"),
                    "Fund": _dropped["name"].astype("string"),
                    "Fund type": _dropped["fund_type"].astype("string"),
                    "Lipper benchmark": _dropped["benchmark_ticker"].astype(
                        "string"
                    ),
                    "Series removed": _dropped["series_removed"].astype(int),
                }
            )
            if len(_dropped)
            else pd.DataFrame(
                columns=[
                    "Identifier",
                    "Ticker",
                    "Fund",
                    "Fund type",
                    "Lipper benchmark",
                    "Series removed",
                ]
            )
        )

        if _n_wide_series and _n_passive_wide == 0:
            _decision_sparse = (
                f"Wide days are sparse ({_wide_rate_txt} of fund-days, "
                f"Table 8.1) and occur only in active share classes."
            )
        elif _n_wide_series:
            _decision_sparse = (
                f"Wide days are sparse ({_wide_rate_txt} of fund-days, "
                f"Table 8.1)."
            )
        else:
            _decision_sparse = (
                "No wide days remain after §7 on this run (Table 8.1)."
            )

        _phdg = _dropped.loc[
            _dropped["isin"].astype("string").str.strip().eq("US46090A7054")
        ]
        if len(_phdg):
            _phdg_row = _phdg.iloc[0]
            _phdg_wide = 0
            if len(_wide_table):
                _phdg_match = _wide_table.loc[
                    _wide_table["id"].astype("string").str.strip().eq(
                        "US46090A7054"
                    ),
                    "far_from_index",
                ]
                _phdg_wide = (
                    int(_phdg_match.sum()) if len(_phdg_match) else 0
                )
            _phdg_justification = (
                f"*Invesco S&P 500 Downside Hedged ETF* (`PHDG`, "
                f"`US46090A7054`). Lipper classifies the fund as Alternatives "
                f"and assigns the benchmark `{_phdg_row['benchmark_ticker']}` "
                f"({_phdg_row['benchmark_name']}), not S&P 500 TR (`.SPXTR`). "
                f"The strategy allocates between equity, implied volatility and "
                f"cash in order to track the S&P 500 Dynamic VEQTOR Index, so "
                f"large daily gaps versus `S&P 500 TR %` are expected by design "
                f"(the fund accounts for {_phdg_wide:,} of the "
                f"{_total_wide_days:,} wide days in Table 8.2). The far-from-index "
                f"screen is therefore the wrong test for this series. The "
                f"identifier and its {_phdg_row['series_removed']:,} series are "
                f"removed from the working selection; no total-return values are "
                f"rewritten."
            )
        else:
            _phdg_justification = ""

        if _n_dropped_ids:
            _decision_md = md(
                f"""
                ### 8.6 Decision

                **Two principles.** (i) Wide days on series that belong in the
                S&P 500 total-return sample are treated as active risk, not as
                data errors, and those series are retained unadjusted.
                (ii) Identifiers whose official Lipper benchmark is not S&P 500
                TR are a sample-selection problem: they leave the working
                selection, and their series are not modified.

                {_decision_sparse} The retained flagged series therefore stay
                in the panel unadjusted.

                **Sample drop.** {_n_dropped_ids:,} identifier
                {"s are" if _n_dropped_ids != 1 else " is"} removed
                ({_n_dropped_series:,} series; Table 8.3).

                {_phdg_justification}
                """
            )
        else:
            _decision_md = md(
                f"""
                ### 8.6 Decision

                {_decision_sparse} Wide days on series that belong in the S&P 500
                total-return sample are treated as active risk, not as data
                errors. No identifier is removed on this run; every series is
                retained unadjusted.
                """
            )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                _result_md,
                (
                    review_table(
                        _multi_display,
                        "Table 8.2 — Series with two or more wide days",
                    )
                    if _n_multi
                    else None
                ),
                _table_note if _n_multi else None,
            ),
            decision=stack(
                _decision_md,
                (
                    review_table(
                        _drop_display,
                        "Table 8.3 — Identifiers removed from the S&P 500 sample",
                    )
                    if _n_dropped_ids
                    else None
                ),
                mo.md(
                    f"**Sample at exit.** {_exit_phrase}"
                    + (
                        f" (−{_n_dropped_ids:,} identifier"
                        f"{'s' if _n_dropped_ids != 1 else ''}, "
                        f"−{_n_dropped_series:,} series)."
                        if _n_dropped_ids
                        else ", unchanged from entry."
                    )
                ),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_wide, run_step_button, step_header):
    _ready_frozen = get_wide() is not None
    run_frozen = run_step_button(
        ready=_ready_frozen, tooltip=None if _ready_frozen else "Run step 8 first"
    )
    _header = step_header("## 9. Blank frozen tails", run_frozen)
    _header
    return (run_frozen,)


@app.cell
def _(catalog, get_wide, pd, run_frozen, set_frozen):
    if run_frozen.value:
        _wide = get_wide()
        if _wide is None:
            raise ValueError("Frozen step requires wide output")
        _repaired_observations = _wide["observations"]
        _catalog_frozen = _wide.get("catalog", catalog)

        def _blank_frozen_tails(source, catalog_frame, min_sessions=5):
            def _column_id(header):
                _match = catalog_frame.loc[catalog_frame["header"].eq(header), "column"]
                return None if _match.empty else int(_match.iloc[0])

            def _fund_label(isin):
                _names = catalog_frame.loc[catalog_frame["id"].eq(isin), "name"].astype("string")
                _label = str(_names.iloc[0]) if len(_names) else isin
                for _suffix in (" - TOT RETURN IND", " - PRICE", " - TOTAL NET ASSETS"):
                    if _label.endswith(_suffix):
                        return _label[: -len(_suffix)]
                return _label

            def _last_change(levels):
                _values = levels.dropna()
                _moved = _values.diff().fillna(0).ne(0)
                if not _moved.any():
                    return None
                return source.index.get_loc(_values.index[_moved.to_numpy()][-1])

            _market_return = source[_column_id("S&P 500 TR %")]
            _is_level = catalog_frame["note"].astype("string").eq("Total return index, daily")
            _cleaned = source.copy()
            _rows = []
            for _tr_row in catalog_frame.loc[_is_level].itertuples(index=False):
                _isin = str(_tr_row.id)
                if str(_tr_row.category) == "Index":
                    continue
                _tr_id = int(_tr_row.column)
                _tr_levels = _cleaned[_tr_id]
                _present = _tr_levels.notna().to_numpy()
                if _present.sum() < 2:
                    continue
                _first = int(_present.argmax())
                _last = len(_present) - 1 - int(_present[::-1].argmax())
                _tr_cut = _last_change(_tr_levels)
                _price_id = _column_id(f"{_isin} Price")
                _price_cut = (
                    None if _price_id is None else _last_change(_cleaned[_price_id])
                )
                # Never moves: TR flat over the full observed sample, and the
                # paired price flat when a price series exists. Absence of a
                # price series does not block the rule. Blank TR, TR %, Price
                # and Price % from first to last observation; leave total net
                # assets untouched; keep the identifier.
                _tr_flat_full_sample = _tr_cut is None
                _price_flat_or_absent = _price_cut is None
                _never_moves = _tr_flat_full_sample and _price_flat_or_absent
                if _never_moves:
                    _start = _first
                else:
                    _cuts = [
                        _cut
                        for _cut in (_tr_cut, _price_cut)
                        if _cut is not None
                    ]
                    if not _cuts:
                        continue
                    _start = max(_cuts) + 1
                if _start > _last:
                    continue
                _tail = _market_return.iloc[_start : _last + 1]
                _moved_sessions = int(_tail.fillna(0).ne(0).sum())
                if not _never_moves and _moved_sessions < min_sessions:
                    continue
                _blanked = 0
                # Return and price series only; total net assets stay as-is.
                for _header in (
                    f"{_isin} TR",
                    f"{_isin} TR %",
                    f"{_isin} Price",
                    f"{_isin} Price %",
                ):
                    _target = _column_id(_header)
                    if _target is None:
                        continue
                    _values = _cleaned[_target].to_numpy(dtype="float64", copy=True)
                    _blanked += int((_values[_start:] == _values[_start:]).sum())
                    _values[_start:] = float("nan")
                    _cleaned[_target] = _values
                _rows.append(
                    {
                        "isin": _isin,
                        "fund": _fund_label(_isin),
                        "pattern": (
                            "never moves" if _never_moves else "frozen tail"
                        ),
                        "last_real_print": (
                            None
                            if _never_moves
                            else source.index[_start - 1].strftime("%Y-%m-%d")
                        ),
                        "frozen_from": source.index[_start].strftime("%Y-%m-%d"),
                        "frozen_to": source.index[_last].strftime("%Y-%m-%d"),
                        "frozen_sessions": _last - _start + 1,
                        "sessions_where_sp500_moved": _moved_sessions,
                        "frozen_level": float(source[_tr_id].iloc[_last]),
                        "cells": _blanked,
                    }
                )
            _log = pd.DataFrame(
                _rows,
                columns=[
                    "isin",
                    "fund",
                    "pattern",
                    "last_real_print",
                    "frozen_from",
                    "frozen_to",
                    "frozen_sessions",
                    "sessions_where_sp500_moved",
                    "frozen_level",
                    "cells",
                ],
            )
            if len(_log):
                _log = _log.sort_values("frozen_sessions", ascending=False).reset_index(drop=True)
            return _cleaned, _log

        _cleaned_observations, _frozen_log = _blank_frozen_tails(
            _repaired_observations, _catalog_frozen
        )

        set_frozen(
            {
                "cleaned_observations": _cleaned_observations,
                "catalog": _catalog_frozen,
                "frozen_log": _frozen_log,
            }
        )
    return


@app.cell
def _(
    catalog,
    get_frozen,
    get_wide,
    md,
    mo,
    pd,
    review_table,
    stack,
    step_sections,
):
    mo.stop(
        get_wide() is None,
        mo.md("Run step 8 first. This step reads the wide-step observations."),
    )
    _wide_for_sample = get_wide()
    _catalog_step = (
        _wide_for_sample.get("catalog", catalog)
        if _wide_for_sample is not None
        else catalog
    )
    _n_ids = int(_catalog_step["id"].nunique())
    _n_cols = len(_catalog_step)
    _fund_mask = _catalog_step["category"].isin(
        ["Active MF", "Active ETF", "Passive MF", "Passive ETF", "To Check MF"]
    )
    _n_fund_ids = int(_catalog_step.loc[_fund_mask, "id"].nunique())
    _n_index_ids = int(
        _catalog_step.loc[_catalog_step["category"].eq("Index"), "id"].nunique()
    )
    _n_rf_ids = int(
        _catalog_step.loc[
            _catalog_step["category"].eq("Risk-free rate"), "id"
        ].nunique()
    )
    _sample_phrase = (
        f"{_n_ids:,} identifiers ({_n_fund_ids:,} funds, "
        f"{_n_index_ids:,} index series"
        + (
            f" and the risk-free rate"
            if _n_rf_ids
            else ""
        )
        + f"), {_n_cols:,} series"
    )
    _documentation = stack(
        mo.md(f"**Sample at entry.** {_sample_phrase}."),
        md(r"""
        ### §9.1 Objective

        This step removes artificial zero returns that appear in a series after
        the fund has stopped being priced. A zero return only counts as an
        observation when the fund was actually valued that day. Mechanical
        repeats of a stale level would distort every daily-return statistic
        used later in the analysis.

        ### §9.2 Background

        When a fund is closed or merged, Datastream often keeps repeating the
        last price and total-return level on every later calendar date. These
        repeats are not economic returns. They add a run of 0% daily returns
        that has no link to the market. In the regressions on the S&P 500 total
        return, this run pushes measured volatility and beta down and distorts
        tracking-error statistics. The right correction is to remove the stale
        observations, not to fill them in. No returns are invented, and the
        last genuine valuation is kept.

        ### §9.3 Method

        Let $L_{i,t}$ be the total-return level and $P_{i,t}$ the price of fund
        $i$ on session $t$. Let $m_t$ be the daily return of the S&P 500 total
        return. Let $T_i$ be the last date on which series $i$ is observed. A
        session is **informative** if the benchmark moved, $m_t \neq 0$.

        **Frozen tail.** The total-return series of fund $i$ has a frozen tail
        starting at $\tau_i$ if all three of the following conditions hold:

        1. **Flat level.** $L_{i,t} = L_{i,\tau_i-1}$ for every
           $t \in [\tau_i, T_i]$. The run extends to the last date of the
           series.
        2. **Minimum length.** The window contains at least five informative
           sessions:
        $$
        \#\{\, t \in [\tau_i, T_i] : m_t \neq 0 \,\} \;\geq\; 5 .
        $$
        3. **Flat price.** The paired price is flat over the same window:
           $P_{i,t} = P_{i,\tau_i-1}$ for every $t \in [\tau_i, T_i]$.

        If the total-return level is flat but the price still moves, the series
        is left unchanged. A fund moving to cash before liquidation is one
        example. The date $\tau_i - 1$ is the **last real print**.

        **Never moves.** Fund $i$ never moves when its total-return level is
        constant over the full observed sample **and** the paired price is
        likewise constant whenever a price series exists. Absence of a price
        series does not block the rule. The fund is treated as having no valid
        return or price observations: the total-return and price levels and
        their daily returns are blanked from the first to the last observation.
        Total net assets are left unchanged. The identifier is retained.

        **Treatment.** Table 9.1 sets out how each case is handled.

        *Table 9.1 — Classification and treatment*

        | Case | Condition | Treatment |
        |---|---|---|
        | Frozen tail | Conditions 1–3 hold | Last real print kept; total-return and price levels and their daily returns blanked from $\tau_i$ to $T_i$; total net assets unadjusted; identifier retained |
        | Flat level, moving price | Conditions 1–2 hold, condition 3 fails | Unadjusted |
        | Never moves | TR level constant over the full sample, and paired price constant when present | TR, TR %, Price and Price % blanked from first to last observation; total net assets unadjusted; identifier retained |
        | Total net assets | Monthly values repeated daily by construction | Unadjusted (out of scope) |

        ### §9.4 Outputs

        The Result (§9.5) lists the series flagged as frozen, the blanking
        window for each and the number of observations removed. It does not
        change the data. The Decision (§9.6) applies the blanking.
        """),
    )
    _frozen = get_frozen()
    if _frozen is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to screen for frozen post-closure tails "
                "(§9.3)._"
            ),
            decision=stack(
                md(r"""
                ### §9.6 Decision

                Frozen tails that meet the three conditions of §9.3 are blanked
                after the last real print. Series that never move are blanked
                entirely. Identifiers are retained whenever earlier observations
                remain usable. Nothing is written to disk until the export in
                Step 11.
                """),
                mo.md("_Decision pending until this step has run._"),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. No series is "
                    f"blanked until this step has run."
                ),
            ),
        )
    else:
        _frozen_log = _frozen["frozen_log"]
        _never_moving = _frozen_log.loc[_frozen_log["pattern"].eq("never moves")]
        _frozen_tails = _frozen_log.loc[_frozen_log["pattern"].eq("frozen tail")]
        _n_flagged = int(len(_frozen_log))
        _n_never = int(len(_never_moving))
        _n_tails = int(len(_frozen_tails))
        _n_blanked = (
            int(_frozen_log["cells"].sum()) if len(_frozen_log) else 0
        )

        if _n_flagged == 0:
            _headline = (
                "No series has a frozen tail, and no series is constant over "
                "the full sample."
            )
        elif _n_tails == 1 and _n_never == 0:
            _one = _frozen_tails.iloc[0]
            _headline = (
                "**One series has a frozen tail. No series is constant over "
                "the full sample.** The issue is marginal in this panel: "
                f"{_n_blanked:,} observation"
                f"{'s' if _n_blanked != 1 else ''} "
                f"{'are' if _n_blanked != 1 else 'is'} blanked, all belonging "
                f"to one fund (*{_one['fund']}*, `{_one['isin']}`)."
            )
        else:
            _headline = (
                f"**{_n_flagged:,}** series "
                f"{'are' if _n_flagged != 1 else 'is'} flagged as frozen "
                f"({_n_tails:,} frozen tail"
                f"{'s' if _n_tails != 1 else ''}, {_n_never:,} never-moving). "
                f"**{_n_blanked:,}** observations are blanked across "
                "total-return and price levels and their daily returns."
            )

        _result_md = md(
            f"""
            ### §9.5 Results

            {_headline}

            *Table 9.2 — Summary of the frozen-tail screen*

            | Outcome | Count |
            |---|---:|
            | Series flagged as frozen | {_n_flagged:,} |
            | Series that never move (TR and price blanked entirely; total net assets kept) | {_n_never:,} |
            | Series with a frozen tail (blanked after the last real print) | {_n_tails:,} |
            | Observations blanked (total-return and price levels, daily returns) | {_n_blanked:,} |
            """
        )

        _frozen_display = (
            pd.DataFrame(
                {
                    "Identifier": _frozen_tails["isin"].astype("string"),
                    "Fund": _frozen_tails["fund"].astype("string"),
                    "Last real print": _frozen_tails["last_real_print"].astype(
                        "string"
                    ),
                    "Frozen from": _frozen_tails["frozen_from"].astype("string"),
                    "Last date": _frozen_tails["frozen_to"].astype("string"),
                    "Frozen sessions": _frozen_tails["frozen_sessions"].astype(
                        int
                    ),
                    "Informative sessions": _frozen_tails[
                        "sessions_where_sp500_moved"
                    ].astype(int),
                    "Frozen level": _frozen_tails["frozen_level"]
                    .astype(float)
                    .round(2),
                    "Observations blanked": _frozen_tails["cells"].astype(int),
                }
            )
            if _n_tails
            else pd.DataFrame(
                columns=[
                    "Identifier",
                    "Fund",
                    "Last real print",
                    "Frozen from",
                    "Last date",
                    "Frozen sessions",
                    "Informative sessions",
                    "Frozen level",
                    "Observations blanked",
                ]
            )
        )

        if _n_tails == 1:
            _row = _frozen_tails.iloc[0]
            _sessions = int(_row["frozen_sessions"])
            _informative = int(_row["sessions_where_sp500_moved"])
            _cells = int(_row["cells"])
            _last_print = str(_row["last_real_print"])
            _frozen_to = str(_row["frozen_to"])
            _fund_name = str(_row["fund"])
            _fund_isin = str(_row["isin"]).strip()
            if _informative == _sessions:
                _info_phrase = "all informative"
            else:
                _info_phrase = (
                    f"{_informative:,} of them informative"
                )
            if _informative == 5:
                _min_phrase = "exactly the five-session minimum"
            elif _informative == 6:
                _min_phrase = "just above the five-session minimum"
            else:
                _min_phrase = "above the five-session minimum"
            if _fund_isin == "US00791R7807":
                _closure_note = (
                    f"The frozen window ends on {_frozen_to}, which is also "
                    f"the common Lipper fund end of the working panel. That "
                    f"coincidence does not imply a delayed Datastream feed: "
                    f"other fund series in the same extract continue to print "
                    f"new levels through that date. For *{_fund_name}* "
                    f"(`{_fund_isin}`), an SEC Form 497 supplement dated "
                    f"1 October 2026 announces that the fund is closed to "
                    f"new investment and is to liquidate on or about "
                    f"30 October 2026 (The Advisors' Inner Circle Fund II, "
                    f"2026). The flat run after {_last_print} is therefore a "
                    f"post-pricing artefact around a documented liquidation, "
                    f"not a panel-wide update lag."
                )
            else:
                _closure_note = (
                    f"The frozen window ends on {_frozen_to}. When that date "
                    f"coincides with the common fund panel end, a delayed "
                    f"Datastream update cannot be ruled out from the screen "
                    f"alone; the blanking still removes mechanical zero "
                    f"returns, which would otherwise bias volatility and beta."
                )
            _tail_note = md(
                f"""
                The tail covers {_sessions:,} session
                {"s" if _sessions != 1 else ""}, {_info_phrase}, which is
                {_min_phrase}. The {_cells:,} blanked observations equal
                {_sessions:,} sessions × 4 quantities (total-return level, price
                level and their two daily returns).

                {_closure_note}
                """
            )
        elif _n_tails > 1:
            _last_print = None
            _fund_isin = None
            _tail_note = md(
                """
                Each row of Table 9.3 reports the blanking window and the number
                of observations removed for one frozen tail. Observations
                blanked equal frozen sessions × up to four quantities
                (total-return level, price level and their two daily returns).
                When a frozen window ends on the common fund panel end, a
                delayed Datastream update cannot be ruled out from the screen
                alone unless an independent closure or merger notice is
                available.
                """
            )
        else:
            _last_print = None
            _fund_isin = None
            _tail_note = None

        if _n_tails == 0 and _n_never == 0:
            _decision_md = md(
                r"""
                ### §9.6 Decision

                No frozen tail and no never-moving series meet the conditions of
                §9.3 on this run. All series are retained unadjusted. The panel
                is passed on to Step 10. Nothing is written to disk until the
                export in Step 11.
                """
            )
        elif (
            _n_tails == 1
            and _n_never == 0
            and _last_print is not None
            and _fund_isin == "US00791R7807"
        ):
            _decision_md = md(
                f"""
                ### §9.6 Decision

                The frozen tail in Table 9.3 is blanked as described in §9.3.
                The blanking is retained because the fund has a documented
                liquidation on or about the panel end date (The Advisors'
                Inner Circle Fund II, 2026), so the repeated levels are not
                usable market returns. All {_n_cols:,} series are retained. No
                identifier is dropped, because the observations before
                {_last_print} are unaffected and stay usable. The corrected
                panel is passed on to Step 10. Nothing is written to disk until
                the export in Step 11.
                """
            )
        elif _n_tails == 1 and _n_never == 0 and _last_print is not None:
            _decision_md = md(
                f"""
                ### §9.6 Decision

                The frozen tail in Table 9.3 is blanked as described in §9.3.
                All {_n_cols:,} series are retained. No identifier is dropped,
                because the observations before {_last_print} are unaffected
                and stay usable. The corrected panel is passed on to Step 10.
                Nothing is written to disk until the export in Step 11.
                """
            )
        elif _n_tails and _n_never == 0:
            _decision_md = md(
                f"""
                ### §9.6 Decision

                The frozen tails in Table 9.3 are blanked as described in
                §9.3. All {_n_cols:,} series are retained. No identifier is
                dropped, because the observations before each last real print
                are unaffected and stay usable. The corrected panel is passed
                on to Step 10. Nothing is written to disk until the export in
                Step 11.
                """
            )
        else:
            _decision_md = md(
                f"""
                ### §9.6 Decision

                Frozen tails that meet the three conditions of §9.3 are blanked
                after the last real print (Table 9.3). Series that never move
                are blanked entirely. All {_n_ids:,} identifiers are retained
                whenever earlier observations remain usable. The corrected
                panel is passed on to Step 10. Nothing is written to disk until
                the export in Step 11.
                """
            )

        _exit_catalog = _frozen.get("catalog", _catalog_step)
        _exit_n_ids = int(_exit_catalog["id"].nunique())
        _exit_n_cols = int(len(_exit_catalog))
        _exit_fund_mask = _exit_catalog["category"].isin(
            [
                "Active MF",
                "Active ETF",
                "Passive MF",
                "Passive ETF",
                "To Check MF",
            ]
        )
        _exit_n_fund_ids = int(
            _exit_catalog.loc[_exit_fund_mask, "id"].nunique()
        )
        _exit_n_index_ids = int(
            _exit_catalog.loc[
                _exit_catalog["category"].eq("Index"), "id"
            ].nunique()
        )
        _exit_n_rf_ids = int(
            _exit_catalog.loc[
                _exit_catalog["category"].eq("Risk-free rate"), "id"
            ].nunique()
        )
        _exit_phrase = (
            f"{_exit_n_ids:,} identifiers ({_exit_n_fund_ids:,} funds, "
            f"{_exit_n_index_ids:,} index series"
            + (
                f" and the risk-free rate"
                if _exit_n_rf_ids
                else ""
            )
            + f"), {_exit_n_cols:,} series"
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                _result_md,
                (
                    review_table(
                        _frozen_display,
                        "Table 9.3 — Frozen series",
                    )
                    if _n_tails
                    else None
                ),
                _tail_note,
            ),
            decision=stack(
                _decision_md,
                mo.md(f"**Sample at exit.** {_exit_phrase}."),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_frozen, run_step_button, step_header):
    _ready_tbill = get_frozen() is not None
    run_tbill = run_step_button(ready=_ready_tbill, tooltip=None if _ready_tbill else "Run step 9 first")
    _header = step_header("## 10. Fill US T-Bill 3M", run_tbill)
    _header
    return (run_tbill,)


@app.cell
def _(catalog, get_frozen, pd, run_tbill, set_tbill):
    if run_tbill.value:
        _frozen = get_frozen()
        if _frozen is None:
            raise ValueError("T-Bill step requires frozen output")
        _cleaned_observations = _frozen["cleaned_observations"]
        _catalog_tbill = _frozen.get("catalog", catalog)

        from helpers.timeseries_functions.fred_dtb3_freeze import (
            fred_dtb3_download_date,
            load_frozen_fred_dtb3,
        )

        _matches = _catalog_tbill.loc[
            _catalog_tbill["header"].eq("US T-Bill 3M"), "column"
        ]
        if len(_matches) != 1:
            raise ValueError("Expected one US T-Bill 3M column")
        _rate_column = int(_matches.iloc[0])
        _rates = load_frozen_fred_dtb3()
        _dates = pd.DatetimeIndex(
            pd.to_datetime(_cleaned_observations.index)
        ).normalize()
        _aligned = _rates.reindex(_dates)
        _rated_observations = _cleaned_observations.copy()
        _rated_observations[_rate_column] = _aligned.to_numpy()
        _filled = int(_aligned.notna().sum())
        _blank = int(_aligned.isna().sum())
        _present = _aligned.dropna()

        set_tbill(
            {
                "rated_observations": _rated_observations,
                "catalog": _catalog_tbill,
                "filled": _filled,
                "blank": _blank,
                "first_print": _present.index[0] if len(_present) else None,
                "first_value": float(_present.iloc[0]) if len(_present) else None,
                "last_print": _present.index[-1] if len(_present) else None,
                "last_value": float(_present.iloc[-1]) if len(_present) else None,
                "download_date": fred_dtb3_download_date(),
                "source_series": "DTB3",
            }
        )
    return


@app.cell
def _(
    catalog,
    get_frozen,
    get_tbill,
    md,
    mo,
    stack,
    step_sections,
):
    mo.stop(
        get_frozen() is None,
        mo.md("Run step 9 first. This step reads the frozen-tail observations frame."),
    )
    _frozen_for_sample = get_frozen()
    _catalog_step = (
        _frozen_for_sample.get("catalog", catalog)
        if _frozen_for_sample is not None
        else catalog
    )
    _n_ids = int(_catalog_step["id"].nunique())
    _n_cols = len(_catalog_step)
    _sample_phrase = (
        f"{_n_ids:,} identifiers (funds and indices), {_n_cols:,} series"
    )
    _documentation = stack(
        mo.md(f"**Sample at entry.** {_sample_phrase}."),
        md(r"""
        ### §10.1 Objective

        Measures of risk-adjusted performance used in the thesis, such as the
        Sharpe ratio, need a short-term risk-free rate. This step fills the
        `US T-Bill 3M` series with a proxy for the three-month US Treasury bill
        rate. The series is the only one modified in this step. All fund and
        index series are left untouched.

        ### §10.2 Source of the problem and choice of proxy

        The `US T-Bill 3M` series arrives from LSEG Datastream with no
        observations, so a second source is needed. We use FRED series `DTB3`,
        the 3-Month Treasury Bill Secondary Market Rate on a discount basis
        (Board of Governors of the Federal Reserve System, H.15 Selected Interest
        Rates; distributed by FRED, Federal Reserve Bank of St. Louis). The
        series reports an annualised **bank discount rate** in percent on a
        360-day bank year. It is not a bond-equivalent (investment) yield. No
        rescaling is applied when the series is stored. Daily frequency lets the
        month-end print used for the Sharpe ratio be taken directly from the
        panel calendar.

        FRED `DTB3` is preferred to the CBOE / Yahoo `^IRX` quote because it is
        the standard academic source for the three-month bill rate and because
        the extract used here is frozen on disk with a recorded download date.

        Let $y_t$ denote the `DTB3` value on date $t$, expressed as an
        annualised bank discount rate in percent.

        ### §10.3 Rate convention

        This step stores $y_t$ as that annualised percent. Conversion to a
        per-period risk-free return is deferred to the performance calculations
        that consume the series.

        For the Sharpe ratio, the thesis takes the last available print in each
        calendar month, $y_m$, and converts it to a monthly simple return
        $$
        r_{f,m} = \left(1 + \frac{y_m}{100}\right)^{1/12} - 1 .
        $$
        Monthly fund returns are then measured in excess of $r_{f,m}$, and the
        ratio of mean excess return to its standard deviation is annualised by
        $\sqrt{12}$. The conversion treats $y_m$ as an effective annual
        percentage rate. It does **not** first translate the bank discount rate
        into a bond-equivalent yield; that approximation is accepted for the
        Sharpe calculation.

        The same series is not used to form daily excess returns. The alpha and
        beta regressions in the thesis are estimated on total (not excess)
        monthly returns, so they do not require a daily risk-free conversion of
        $y_t$.

        ### §10.4 Method

        The series is built in three stages:

        1. **Retrieval.** The frozen FRED `DTB3` CSV
           (`cache/fred-dtb3/DTB3.csv`) is loaded. The accompanying manifest
           records the series identity and the download date.
        2. **Alignment.** Observation dates are normalised to calendar dates, and
           the series is reindexed to the panel's date index.
        3. **Fill.** For each panel date $t$, the `US T-Bill 3M` series takes
           the value $y_t$ when FRED reports a print for that date. Dates with
           no FRED print, including US holidays, are left blank. **No
           carry-forward** is applied, so a missing value is never replaced by
           the previous print.

        ### §10.5 Outputs

        The step produces a single series, `US T-Bill 3M`, holding $y_t$ where
        available and blank elsewhere. It also produces a coverage summary
        (Table 10.1). The monthly conversion of §10.3 is applied only when
        Sharpe ratios are computed, not in this step.
        """),
    )
    _tbill = get_tbill()
    if _tbill is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to fill `US T-Bill 3M` from frozen FRED "
                "`DTB3` (§10.4)._"
            ),
            decision=stack(
                md(r"""
                ### §10.7 Decision

                The `US T-Bill 3M` series is replaced by the aligned FRED
                `DTB3` prints described in §10.4, with blanks kept as blanks.
                The annualised discount rate is stored as percent; the monthly
                conversion of §10.3 is left to the Sharpe calculation. No fund
                or index series is changed, and none is removed. The quality
                labels attached to this series are updated only when the dataset
                is exported (Step 11).
                """),
                mo.md("_Decision pending until this step has run._"),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. The `US T-Bill 3M` "
                    f"series is unchanged until this step has run."
                ),
            ),
        )
    else:
        _filled = int(_tbill["filled"])
        _blank = int(_tbill["blank"])
        _total = _filled + _blank
        _filled_share = 100.0 * _filled / _total if _total else 0.0
        _blank_share = 100.0 * _blank / _total if _total else 0.0
        _first_print = _tbill["first_print"]
        _first_value = _tbill["first_value"]
        _last_print = _tbill["last_print"]
        _last_value = _tbill["last_value"]
        _download_date = _tbill.get("download_date")
        _download_txt = (
            f" Freeze download date: **{_download_date}**."
            if _download_date
            else ""
        )
        _first_line = (
            f"| First print | {_first_print:%Y-%m-%d} | {_first_value:.2f}% |"
            if _first_print is not None and _first_value is not None
            else "| First print | — | — |"
        )
        _last_line = (
            f"| Last print | {_last_print:%Y-%m-%d} | {_last_value:.2f}% |"
            if _last_print is not None and _last_value is not None
            else "| Last print | — | — |"
        )
        _range_clause = (
            (
                f"The rate ranges from {_first_value:.2f}% at the first print "
                f"({_first_print:%-d %B %Y}) to {_last_value:.2f}% at the last "
                f"({_last_print:%-d %B %Y}). "
            )
            if (
                _first_print is not None
                and _first_value is not None
                and _last_print is not None
                and _last_value is not None
            )
            else ""
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=md(
                f"""
                ### §10.6 Results

                The frozen FRED `DTB3` series covers about {_filled_share:.0f}%
                of the sessions in the panel (Table 10.1).{_download_txt}
                {_range_clause}Because the Sharpe convention of §10.3 uses only
                the last print of each month, the {_blank:,} blank
                session{"s" if _blank != 1 else ""} do not leave any month
                without an observation, as long as each month has at least one
                FRED print.

                **Table 10.1 — Coverage of the `US T-Bill 3M` series after
                alignment**

                | | Sessions | Share of panel |
                |---|---:|---:|
                | Filled from FRED `DTB3` | {_filled:,} | {_filled_share:.1f}% |
                | Left blank (no FRED print) | {_blank:,} | {_blank_share:.1f}% |
                | **Total panel sessions** | **{_total:,}** | **100.0%** |

                | | Date | Value ($y_t$, annualised %) |
                |---|---|---:|
                {_first_line}
                {_last_line}
                """
            ),
            decision=stack(
                md(r"""
                ### §10.7 Decision

                The `US T-Bill 3M` series is replaced by the aligned FRED
                `DTB3` prints described in §10.4, with blanks kept as blanks.
                The annualised discount rate is stored as percent; the monthly
                conversion of §10.3 is left to the Sharpe calculation. No fund
                or index series is changed, and none is removed. The quality
                labels attached to this series are updated only when the dataset
                is exported (Step 11).
                """),
                mo.md(f"**Sample at exit.** {_sample_phrase}."),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_tbill, run_step_button, step_header):
    _ready_export = get_tbill() is not None
    run_export = run_step_button(
        ready=_ready_export,
        tooltip=None if _ready_export else "Run step 10 first",
    )
    _header = step_header("## 11. Export cleaned workbook", run_export)
    _header
    return (run_export,)


@app.cell
def _(
    catalog,
    drop_isins_from_funds_frame,
    enable_scale_shift,
    flag_summary_table,
    get_frozen,
    get_gap,
    get_holiday,
    get_level_jump,
    get_rebuild,
    get_scale,
    get_spike,
    get_tbill,
    get_wide,
    label_rows,
    observations,
    pd,
    run_export,
    set_export,
    sheet_name,
    workbook,
):
    if run_export.value:
        _tbill = get_tbill()
        if _tbill is None:
            raise ValueError("Export step requires T-Bill output")
        _holiday = get_holiday()
        _gap = get_gap()
        if enable_scale_shift.value:
            _scale = get_scale()
        else:
            _scale = {
                "observations": _gap["observations"],
                "controls": _gap["controls"],
                "issue_summary": _gap["issue_summary"],
            }
        _level_jump = get_level_jump()
        _rebuild = get_rebuild()
        _spike = get_spike()
        _wide = get_wide()
        _frozen = get_frozen()
        _required = (
            _holiday,
            _gap,
            _level_jump,
            _rebuild,
            _spike,
            _wide,
            _frozen,
            _tbill,
        )
        if enable_scale_shift.value:
            _required = (*_required, _scale)
        if None in _required:
            raise ValueError("Export step requires Steps 2–10 payloads")
        _cleaned_observations = _tbill["rated_observations"]
        _export_catalog = _tbill.get("catalog", catalog)

        def _build_run_summary():
            from helpers.timeseries_functions.rebuild_tr_from_distributions import (
                LIPPER_CLOSE_PP,
                LIPPER_TEST_HORIZONS,
                annotate_rebuild_log_lipper_status,
                lipper_test_status,
            )

            holiday_log = _holiday["correction_log"]
            gap_table = flag_summary_table(_gap["issue_summary"], "gaps")
            scale_table = flag_summary_table(_scale["issue_summary"], "scale_shift")
            jump_table = flag_summary_table(_level_jump["issue_summary"], "level_jumps")
            jump_isins = set(jump_table["id"].astype("string").str.strip())
            action_log = _level_jump["action_log"]
            pending = action_log.loc[~action_log["decision"].eq("already rescaled")]
            pending_isin = pending["isin"].astype("string").str.strip()
            decision_log = pending.loc[
                pending_isin.isin(jump_isins)
                | pending["decision"].isin(["rescaled", "kept"])
            ]
            rescaled = decision_log.loc[decision_log["decision"].eq("rescaled")]

            rebuild_log = _rebuild["rebuild_log"].copy()
            if (
                len(rebuild_log)
                and "lipper_fail_after" not in rebuild_log.columns
            ):
                rebuild_log = annotate_rebuild_log_lipper_status(
                    rebuild_log, close_pp=LIPPER_CLOSE_PP
                )
            adopted_mask = rebuild_log["decision"].eq("adopted") if len(rebuild_log) else None
            n_adopted = int(adopted_mask.sum()) if adopted_mask is not None else 0
            n_kept_ds = int(len(rebuild_log) - n_adopted) if len(rebuild_log) else 0

            ds_pass = ds_fail = ds_un = rb_pass = rb_fail = rb_un = 0
            post_pass = post_fail = post_un = 0
            lipper_fail_after = lipper_pass_after = lipper_dual_fail = 0
            if len(rebuild_log) and "datastream_vs_lipper" in rebuild_log.columns:
                ds_pass = int((rebuild_log["datastream_vs_lipper"] == "pass").sum())
                ds_fail = int((rebuild_log["datastream_vs_lipper"] == "fail").sum())
                ds_un = int((rebuild_log["datastream_vs_lipper"] == "unscored").sum())
                rb_pass = int((rebuild_log["rebuild_vs_lipper"] == "pass").sum())
                rb_fail = int((rebuild_log["rebuild_vs_lipper"] == "fail").sum())
                rb_un = int((rebuild_log["rebuild_vs_lipper"] == "unscored").sum())
                lipper_fail_after = int(rebuild_log["lipper_fail_after"].sum())
                lipper_pass_after = int(
                    (rebuild_log["lipper_status_after"] == "pass").sum()
                )
                lipper_dual_fail = int(rebuild_log["lipper_dual_fail"].sum())
                if adopted_mask is not None:
                    post_pass = int(
                        (
                            rebuild_log.loc[adopted_mask, "rebuild_vs_lipper"]
                            == "pass"
                        ).sum()
                    )
                    post_fail = int(
                        (
                            rebuild_log.loc[adopted_mask, "rebuild_vs_lipper"]
                            == "fail"
                        ).sum()
                    )
                    post_un = int(
                        (
                            rebuild_log.loc[adopted_mask, "rebuild_vs_lipper"]
                            == "unscored"
                        ).sum()
                    )

            spike_table = flag_summary_table(_spike["issue_summary"], "spikes")
            dist_log = _spike["distribution_log"]
            repaired = dist_log.loc[dist_log["decision"].eq("repaired")]
            kept_spikes = dist_log.loc[dist_log["decision"].eq("kept")]
            adj = repaired["adjustment"].astype("string")
            n_forward = int(adj.str.contains("S&P return", regex=False, na=False).sum())
            n_one_day = int(adj.str.contains("price return", regex=False, na=False).sum())

            wide_table = flag_summary_table(_wide["issue_summary"], "wide")
            issue_w = _wide["issue_summary"]
            total_days = int(issue_w["days"].sum()) if len(issue_w) else 0
            total_wide = int(issue_w["far_from_index"].sum()) if len(issue_w) else 0
            wide_rate = (total_wide / total_days) if total_days else float("nan")

            frozen_log = _frozen["frozen_log"]
            never_moves = (
                frozen_log.loc[frozen_log["pattern"].eq("never moves")]
                if len(frozen_log)
                else frozen_log
            )
            frozen_tails = (
                frozen_log.loc[frozen_log["pattern"].eq("frozen tail")]
                if len(frozen_log)
                else frozen_log
            )

            return {
                "holidays": int(len(_holiday["holiday_dates"])),
                "holiday_series_corrected": int(len(holiday_log)),
                "holiday_cells": int(holiday_log["cells_changed"].sum())
                if len(holiday_log)
                else 0,
                "series_checked": int(len(_gap["issue_summary"])),
                "gap_series": int(len(gap_table)),
                "scale_series": int(len(scale_table)),
                "scale_factor": _scale["controls"]["scale_factor"],
                "scale_window": _scale["controls"]["scale_window"],
                "level_jump_series": int(len(jump_table)),
                "level_jump_days": int(_level_jump["issue_summary"]["level_jumps"].sum()),
                "level_jump_funds_rescaled": int(rescaled["isin"].nunique())
                if len(rescaled)
                else 0,
                "level_jump_cells": int(rescaled["cells"].sum()) if len(rescaled) else 0,
                "rebuild_funds": int(len(rebuild_log)),
                "lipper_close_pp": float(LIPPER_CLOSE_PP),
                "datastream_pass": ds_pass,
                "datastream_fail": ds_fail,
                "datastream_unscored": ds_un,
                "rebuild_pass": rb_pass,
                "rebuild_fail": rb_fail,
                "rebuild_unscored": rb_un,
                "rebuild_adopted": n_adopted,
                "rebuild_kept_datastream": n_kept_ds,
                "post_adopt_pass": post_pass,
                "post_adopt_fail": post_fail,
                "post_adopt_unscored": post_un,
                "lipper_fail_after": lipper_fail_after,
                "lipper_pass_after": lipper_pass_after,
                "lipper_dual_fail": lipper_dual_fail,
                "spike_series": int(len(spike_table)),
                "spike_return": _spike["controls"]["spike_return"],
                "reversal_band": _spike["controls"]["reversal_band"],
                "spike_repaired_days": int(len(repaired)),
                "spike_forward": n_forward,
                "spike_one_day": n_one_day,
                "spike_kept_days": int(len(kept_spikes)),
                "spike_cells": int(repaired["cells"].sum()) if len(repaired) else 0,
                "wide_series": int(len(wide_table)),
                "index_gap": _wide["controls"]["index_gap"],
                "wide_days": total_wide,
                "fund_days": total_days,
                "wide_day_rate": wide_rate,
                "frozen_series": int(len(frozen_log)),
                "frozen_never_moves": int(len(never_moves)),
                "frozen_tails": int(len(frozen_tails)),
                "frozen_cells": int(frozen_log["cells"].sum()) if len(frozen_log) else 0,
                "tbill_filled": int(_tbill["filled"]),
                "tbill_blank": int(_tbill["blank"]),
            }

        def _save_cleaned_workbook():
            import os
            import shutil
            import tempfile
            from pathlib import Path as _Path

            _kept_columns = list(_cleaned_observations.columns)
            _missing = [
                column
                for column in _kept_columns
                if column not in observations.columns
            ]
            if _missing:
                raise ValueError(
                    "Corrected panel has columns absent from the loaded sheet"
                )
            if not _cleaned_observations.index.equals(observations.index):
                raise ValueError("Corrected dates do not match the loaded sheet")
            _catalog_columns = set(
                int(column) for column in _export_catalog["column"].tolist()
            )
            if set(int(column) for column in _kept_columns) != _catalog_columns:
                raise ValueError(
                    "Corrected panel columns do not match the working catalog"
                )

            _source = _Path(workbook).resolve()
            # Immutable input: write a sibling cleaned workbook, never replace
            # v2-funds-normalized.xlsx.
            _output = _source.with_name("v2-funds-normalized-cleaned.xlsx")

            # Dump catalog + cleaned panel only (kept series). Sample drops from
            # §8 are omitted. Other workbook sheets stay via the copy, then
            # Funds final is rewritten without the dropped identifiers.
            _meta = (
                _export_catalog.set_index("column")
                .loc[_cleaned_observations.columns]
                .copy()
            )
            _bill = _meta["header"].eq("US T-Bill 3M")
            _tbill_download = _tbill.get("download_date")
            _meta.loc[_bill, "name"] = (
                "3-Month Treasury Bill Secondary Market Rate (FRED DTB3)"
            )
            _meta.loc[_bill, "note"] = (
                "FRED DTB3, annualised bank discount rate in %. "
                "Blank when FRED has no print."
                + (
                    f" Freeze download date: {_tbill_download}."
                    if _tbill_download
                    else ""
                )
            )
            _n_series = len(_cleaned_observations.columns)
            _series = pd.DataFrame(
                index=range(label_rows + len(_cleaned_observations)),
                columns=range(1 + _n_series),
                dtype=object,
            )
            for _row, _field in enumerate(
                ("id", "name", "category", "fee", "note", "header")
            ):
                _series.iloc[_row, 1:] = _meta[_field].to_numpy()
            _series.iloc[label_rows:, 0] = _cleaned_observations.index.to_numpy()
            _series.iloc[label_rows:, 1:] = _cleaned_observations.to_numpy()

            _baseline = observations.loc[:, _cleaned_observations.columns]
            _difference = _baseline.sub(_cleaned_observations).abs()
            _changed = _difference.gt(1e-12) | (
                _baseline.isna() ^ _cleaned_observations.isna()
            )
            _corrected_cells = int(_changed.to_numpy().sum())

            _temporary_handle = tempfile.NamedTemporaryFile(
                prefix="v2-funds-normalized-cleaned-",
                suffix=".xlsx",
                delete=False,
                dir=_output.parent,
            )
            _temporary_path = _temporary_handle.name
            _temporary_handle.close()
            _funds_final_dropped = 0
            try:
                shutil.copyfile(_source, _temporary_path)
                with pd.ExcelWriter(
                    _temporary_path,
                    engine="openpyxl",
                    mode="a",
                    if_sheet_exists="replace",
                ) as writer:
                    _removed_raw_sheet = "D-Timeseries raw" in writer.book.sheetnames
                    if _removed_raw_sheet:
                        del writer.book["D-Timeseries raw"]
                    _series.to_excel(
                        writer, sheet_name=sheet_name, index=False, header=False
                    )
                    if "Funds final" in writer.book.sheetnames:
                        _funds_final = pd.read_excel(
                            _source, sheet_name="Funds final"
                        )
                        _n_before = len(_funds_final)
                        _funds_final = drop_isins_from_funds_frame(_funds_final)
                        _funds_final_dropped = _n_before - len(_funds_final)
                        _funds_final.to_excel(
                            writer, sheet_name="Funds final", index=False
                        )
                try:
                    os.replace(_temporary_path, _output)
                except OSError:
                    shutil.move(_temporary_path, _output)
            finally:
                if os.path.exists(_temporary_path):
                    os.remove(_temporary_path)
            return (
                _corrected_cells,
                _removed_raw_sheet,
                _output,
                _funds_final_dropped,
            )

        (
            _corrected_cells,
            _removed_raw_sheet,
            _output_path,
            _funds_final_dropped,
        ) = _save_cleaned_workbook()
        _run_summary = _build_run_summary()

        set_export(
            {
                "corrected_cells": _corrected_cells,
                "removed_raw_sheet": _removed_raw_sheet,
                "funds_final_dropped": _funds_final_dropped,
                "workbook": str(_output_path),
                "source_workbook": str(workbook),
                "sheet_name": sheet_name,
                "catalog": _export_catalog,
                "run_summary": _run_summary,
            }
        )
    return


@app.cell
def _(
    catalog,
    get_export,
    get_tbill,
    md,
    mo,
    stack,
    step_sections,
    workbook,
):
    mo.stop(
        get_tbill() is None,
        mo.md("Run step 10 first. This step writes the cleaned in-memory panel."),
    )
    _tbill_for_sample = get_tbill()
    _catalog_step = (
        _tbill_for_sample.get("catalog", catalog)
        if _tbill_for_sample is not None
        else catalog
    )
    _n_ids = int(_catalog_step["id"].nunique())
    _n_cols = len(_catalog_step)
    _sample_phrase = (
        f"{_n_ids:,} identifiers (funds and indices), {_n_cols:,} series"
    )
    _cleaned_name = "v2-funds-normalized-cleaned.xlsx"
    _cleaned_path = workbook.with_name(_cleaned_name)
    _documentation = stack(
        mo.md(f"**Sample at entry.** {_sample_phrase}."),
        md(f"""
        ### §11.1 Objective

        Steps 1–10 hold every repair and every sample decision in memory. This
        step is the sole write to disk: it persists the working catalog and the
        cleaned daily panel so that later notebooks can load a single,
        reproducible artefact without re-running the pipeline. The input
        workbook `{workbook.name}` is left unchanged.

        ### §11.2 Principles

        Three rules govern the export.

        1. **Immutable input.** The normalised extract is never opened for
           write. The cleaned panel is published as a sibling workbook,
           `{_cleaned_name}`, in the same folder. Re-runs overwrite only that
           sibling.
        2. **Kept series only.** Series dropped at load (for example net-asset
           series) and identifiers removed from the S&P 500 total-return sample
           in §8 are omitted from the exported panel. The sheet `Funds final` is
           rewritten without those identifiers so that the fund list matches the
           panel.
        3. **Documented provenance.** Label rows for `US T-Bill 3M` are updated
           to record the FRED `DTB3` source and, when available, the freeze
           download date from §10. Other sheets that are not rebuilt are carried
           over from the input copy.

        ### §11.3 Method

        The workbook is assembled in four stages.

        1. **Copy.** `{workbook.name}` is copied to a temporary file in the same
           folder. The input path is never opened for write.
        2. **Panel sheet.** The sheet `D-Timeseries final` is rebuilt from the
           working catalog labels and the cleaned observations for the retained
           series only. The `US T-Bill 3M` name and note rows are set to the
           FRED `DTB3` provenance described in §10.
        3. **Fund list.** When `Funds final` is present, identifiers removed in
           §8 are dropped so that the cleaned fund list matches the cleaned
           panel.
        4. **Publish.** The sheet `D-Timeseries raw`, when present, is removed
           from the copy. The temporary file then replaces `{_cleaned_name}`
           atomically. The input workbook remains unchanged.

        Cell-level differences between the loaded panel and the cleaned panel
        are counted for the Result summary; they are not written as a separate
        sheet.

        ### §11.4 Outputs

        The step produces one workbook, `{_cleaned_name}`, containing the
        rebuilt `D-Timeseries final` sheet (retained series only), an aligned
        `Funds final` sheet when that sheet exists in the input, and the other
        input sheets carried over from the copy. No series is modified beyond
        what Steps 1–10 already decided; this step only persists those
        decisions.
        """),
    )
    _export = get_export()
    if _export is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                f"_Click **Run step** to write the cleaned panel to "
                f"`{_cleaned_path}` (§11.3). The input `{workbook.name}` is "
                f"left unchanged._"
            ),
            decision=stack(
                md(r"""
                ### §11.6 Decision

                Artefact not yet published.
                """),
                mo.md("_Decision pending until this step has run._"),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. Unchanged until "
                    f"this step has run; the export does not add or remove "
                    f"identifiers."
                ),
            ),
        )
    else:
        _corrected_cells = _export["corrected_cells"]
        _removed_raw_sheet = _export["removed_raw_sheet"]
        _sheet = _export.get("sheet_name", "D-Timeseries final")
        _path = _export.get("workbook", str(_cleaned_path))
        _source = _export.get("source_workbook", str(workbook))
        _funds_dropped = int(_export.get("funds_final_dropped") or 0)
        _funds_line = (
            f"The sheet `Funds final` was rewritten without "
            f"{_funds_dropped:,} identifier"
            f"{'s' if _funds_dropped != 1 else ''} removed in §8. "
            if _funds_dropped
            else (
                "The sheet `Funds final` needed no further identifier "
                "removals on this run. "
            )
        )
        _raw_line = (
            "The sheet `D-Timeseries raw` was removed from the cleaned copy. "
            if _removed_raw_sheet
            else ""
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=md(
                f"""
                ### §11.5 Results

                The cleaned panel was written to `{_path}` as described in
                §11.3 (Table 11.1). Only retained series are included;
                identifiers removed in §8 are omitted from the panel.
                {_funds_line}{_raw_line}Relative to the panel loaded at
                Step 1, {_corrected_cells:,} cell
                {"s differ" if _corrected_cells != 1 else " differs"} after the
                repairs of Steps 1–10. The input workbook at `{_source}` was
                not modified and remains the immutable source for any re-run.

                **Table 11.1 — Export artefact**

                | Item | Value |
                |---|---|
                | Output workbook | `{_cleaned_name}` |
                | Panel sheet | `{_sheet}` |
                | Retained series | {_n_cols:,} |
                | Identifiers | {_n_ids:,} |
                | Cells different from the loaded panel | {_corrected_cells:,} |
                | Identifiers dropped from `Funds final` | {_funds_dropped:,} |
                | `D-Timeseries raw` removed | {"yes" if _removed_raw_sheet else "no"} |
                """
            ),
            decision=stack(
                md(
                    f"""
                    ### §11.6 Decision

                    Artefact published: `{_cleaned_name}`.
                    """
                ),
                mo.md(
                    f"**Sample at exit.** {_sample_phrase}. Unchanged from "
                    f"entry; this step persists the in-memory sample and does "
                    f"not add or remove identifiers."
                ),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Conclusion
    """)
    return


@app.cell
def _(get_export, md, mo):
    mo.stop(
        get_export() is None,
        mo.md(
            "_Run step 11 first to export the cleaned workbook and unlock "
            "the conclusion._"
        ),
    )
    _export = get_export()
    _s = _export.get("run_summary") or {}
    _wide_rate = _s.get("wide_day_rate")
    _wide_rate_txt = (
        f"{_wide_rate:.3%}"
        if isinstance(_wide_rate, (int, float)) and _wide_rate == _wide_rate
        else "n/a"
    )
    _index_gap = _s.get("index_gap")
    _index_gap_txt = (
        f"{_index_gap:.0%}"
        if isinstance(_index_gap, (int, float)) and _index_gap == _index_gap
        else "n/a"
    )
    _lipper_pp = _s.get("lipper_close_pp", 0.5)
    _corrected = int(_export.get("corrected_cells", 0) or 0)
    _funds_dropped = int(_export.get("funds_final_dropped") or 0)
    _out = _export.get(
        "workbook", "output-data/v2-funds-normalized-cleaned.xlsx"
    )
    _src = _export.get(
        "source_workbook", "output-data/v2-funds-normalized.xlsx"
    )
    _raw_note = (
        " The sheet `D-Timeseries raw` was removed from the cleaned copy."
        if _export.get("removed_raw_sheet")
        else ""
    )
    md(f"""
    ### Role in the thesis

    The thesis compares active and passive US funds against the S&P 500 total
    return. Cumulative performance, volatility and regression estimates are
    sensitive to errors in the daily panel. This notebook turns the provisional
    Datastream / Lipper extract into a regression-ready total-return sample by
    screening the pitfalls summarised in Table 0.1, applying only documented
    repairs, and restricting the working sample to funds whose Lipper
    benchmark is the S&P 500 total return (`.SPXTR`).

    ### What the pipeline does

    Eleven gated steps process the sheet `D-Timeseries final` in fixed order.
    **Repair** steps rewrite cells only when the Decision of that step
    documents the change: exchange-holiday blanks (§2), corporate-action level
    rescales (§5), Lipper-gated total-return rebuilds (§6), curated
    distribution-day spike repairs (§7), frozen post-closure tails (§9), and
    the US T-bill fill from FRED `DTB3` (§10). Step 1 may also replace selected
    series with Yahoo Finance when persistent Lipper level breaks cannot be
    repaired otherwise. **Diagnostic** steps score flags and never rewrite:
    gaps (§3) and the optional scale-shift check (§4). Step 8 scores
    divergence from the index and may remove identifiers whose Lipper
    benchmark is not `.SPXTR`. Each step reads only the prior step’s output.
    Step 11 is the sole write to disk (§11): it persists the retained series to
    a sibling cleaned workbook and leaves the input unchanged.

    ### Findings from this run

    Table C.1 summarises the gated payloads from Steps 2–11. Relative to the
    panel loaded at Step 1, {_corrected:,} cell
    {"s differ" if _corrected != 1 else " differs"} after all documented
    repairs. On the divergence screen, {_wide_rate_txt} of fund-days exceed
    the {_index_gap_txt} gap versus $m_t$
    ({_s.get("wide_days", 0):,} of {_s.get("fund_days", 0):,} fund-days;
    {_s.get("wide_series", 0):,} series with at least one wide day). Of the
    {_s.get("rebuild_funds", 0):,} funds assessed against Lipper’s 3-, 5- and
    10-year total returns (tolerance {_lipper_pp:g} percentage points),
    {_s.get("rebuild_adopted", 0):,} rebuilt series were adopted and
    {_s.get("rebuild_kept_datastream", 0):,} kept the Datastream path;
    {_s.get("lipper_fail_after", 0):,} still fail the Lipper gate on the series
    used downstream, while {_s.get("lipper_pass_after", 0):,} pass.

    **Table C.1 — Summary of this run**

    | Step | Headline |
    |---|---|
    | §2 Holidays | {_s.get("holidays", 0):,} S&P-flat dates; {_s.get("holiday_series_corrected", 0):,} level series blanked ({_s.get("holiday_cells", 0):,} cells) |
    | §3 Gaps | {_s.get("series_checked", 0):,} TR % series checked; {_s.get("gap_series", 0):,} with remaining gaps |
    | §4 Scale shift | {_s.get("scale_series", 0):,} series flagged (factor {_s.get("scale_factor", "n/a")}, window {_s.get("scale_window", "n/a")}) |
    | §5 Level jump | {_s.get("level_jump_series", 0):,} TR % series flagged; {_s.get("level_jump_funds_rescaled", 0):,} funds rescaled ({_s.get("level_jump_cells", 0):,} cells) |
    | §6 Lipper rebuild | Datastream {_s.get("datastream_pass", 0):,} pass / {_s.get("datastream_fail", 0):,} fail / {_s.get("datastream_unscored", 0):,} unscored; rebuild {_s.get("rebuild_pass", 0):,} / {_s.get("rebuild_fail", 0):,} / {_s.get("rebuild_unscored", 0):,}; {_s.get("rebuild_adopted", 0):,} adopted, {_s.get("rebuild_kept_datastream", 0):,} kept Datastream |
    | §7 Spikes | {_s.get("spike_series", 0):,} series flagged; {_s.get("spike_repaired_days", 0):,} distribution days repaired ({_s.get("spike_forward", 0):,} forward / S&P, {_s.get("spike_one_day", 0):,} one-day); {_s.get("spike_kept_days", 0):,} agreeing price–TR spikes retained |
    | §8 Far from index | {_s.get("wide_series", 0):,} series; {_wide_rate_txt} of fund-days wide (threshold {_index_gap_txt}) |
    | §9 Frozen tails | {_s.get("frozen_series", 0):,} series ({_s.get("frozen_never_moves", 0):,} never-move, {_s.get("frozen_tails", 0):,} tails; {_s.get("frozen_cells", 0):,} cells blanked) |
    | §10 US T-bill | {_s.get("tbill_filled", 0):,} sessions filled from FRED `DTB3`; {_s.get("tbill_blank", 0):,} left blank |
    | §11 Export | {_corrected:,} cells different from the loaded panel; {_funds_dropped:,} identifier{"s" if _funds_dropped != 1 else ""} dropped from `Funds final` |

    ### Interpretation of remaining flags

    Flags that remain after repair are not treated uniformly as data errors.
    Wide days on series that stay in the S&P 500 total-return sample are read
    as active risk when the fund-day rate is sparse (this run:
    {_wide_rate_txt}). Identifiers whose Lipper benchmark is not `.SPXTR`
    (currently PHDG) are removed from the working selection instead. Spikes
    where price and total return move together are retained as genuine NAV
    moves. Explained scale episodes — thin early NAV marking or
    pre-liquidation cash — are left as published. Distribution-day total-return
    repairs run only when the §7 eligibility gate still finds price–TR
    disagreement and a material market residual; forward cases without a
    confirmed cash amount use that day’s $m_t$ as the proxy.

    ### Deliverable

    Later analysis should use the **total-return** series for performance and
    for regressions on the S&P 500 total return. The paired **price** series
    remains the published NAV and still falls on distribution days. The cleaned
    panel is the sibling workbook `{_out}`; the immutable input is `{_src}`.
    {_raw_note}
    """)
    return


if __name__ == "__main__":
    app.run()
