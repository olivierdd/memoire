# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "altair>=6.3.0",
#     "marimo>=0.25.2",
#     "openpyxl>=3.1.5",
#     "pandas>=3.0.6",
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
        flag_summary_table,
        repair_distribution_day_tr,
        rescale_level_breaks,
        summarize_tr_consistency,
    )

    return (
        carry_holiday_placeholders,
        flag_summary_table,
        repair_distribution_day_tr,
        rescale_level_breaks,
        summarize_tr_consistency,
    )


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Load the daily series (V2)

    Load the `D-Timeseries final` sheet of `output-data/v2-funds-normalized.xlsx`. The sheet keeps six label rows, then one row per date.

    The first column is the date. Each other column is one series: an index, the risk-free rate, or a fund total return, price, or net assets.

    **Data sources.** The primary source is LSEG Datastream / Lipper, made
    available to Université libre de Bruxelles (ULB) students. Yahoo Finance is
    used only as a secondary source to correct or replace series where the
    Datastream path is unreliable (for example lasting level jumps, missing cash
    distributions for a TR rebuild, or the empty US T-Bill column filled from
    `^IRX`).

    **Why thorough verification and cleaning.** Equity Datastream research
    documents that naive use of price and total-return series can materially
    distort volatility, cumulative performance, and regression inference
    ([Ince & Porter, 2006](https://doi.org/10.1111/j.1475-6803.2006.00189.x);
    [Brückner, 2013](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2243816);
    [Landis & Skouras, 2021](https://doi.org/10.1016/j.jbankfin.2021.106128)).
    Four of those pitfalls transfer directly to our Lipper / Datastream fund
    panel; this notebook screens and, where Decision documents it, repairs each
    before export:

    1. **Holiday padding.** By default Datastream often repeats the last close
       across local non-trading weekdays, inserting artificial zero-return days
       that dilute measured volatility. Best practice is not to treat those
       dates as genuine observations.
       → **Steps 2–3:** blank Price/TR level and % on S&P-flat US holidays and
       recompute the next session’s return from the last trade; gap checks then
       treat those dates as non-trading, not missing data.

    2. **Stale prices after delisting / closure.** After a security stops
       trading, Datastream commonly carries the final price and return index
       forward indefinitely. Literature practice is to truncate or convert that
       trailing flat path to missing.
       → **Step 9:** blank frozen post-closure tails (and never-moving series)
       after the last real print.

    3. **Retroactive adjustments and rounding distortions.** Standard adjusted
       prices are rewritten for splits and capital changes; with limited
       decimal precision, heavily adjusted series can approach near-zero levels
       and produce spurious percentage jumps. Screens for extreme lasting breaks
       (and unadjusted prices when the traded level matters) are recommended.
       → **Steps 1, 4–5, 7:** Yahoo Price+TR replace where Lipper level jumps
       persist; diagnose scale shifts; rescale sticky corporate-action level
       breaks; flag / repair extreme spike days when they are data errors.

    4. **Return Index (RI) / dividend-adjustment errors.** Academic work finds
       occasional RI mistakes around ordinary and special dividends and
       spin-offs; compounded horizons then diverge from a correctly reinvested
       path. Cross-checking RI against an alternative construction is advised.
       → **Steps 6–7:** rebuild daily TR from price plus cash distributions
       (Yahoo/FMP) and adopt when a Lipper 3y/5y/10y gate prefers it; repair
       curated distribution-day TR errors that still disagree with Price and the
       market.

    Because this thesis measures fund performance from daily total returns and
    regresses them on the S&P 500, the extract is treated as provisional until
    those checks run.

    **Pipeline structure:** Step 1 loads the workbook on open (auto-run) and
    keeps only total returns, the primary `S&P 500 TR` / `TR %` (Lipper
    `.SPXTR` — the series used for QA and for regressions), the US T-Bill,
    paired Price series needed for repairs, and the Composite TR / `%` pair
    (kept for information and minor side work, e.g. Lipper `.INX`). Later
    steps are gated: each waits for its **Run step** button;
    Result and Decision stay empty until that button has been pressed; the next
    button stays disabled until the previous step has finished.

    - **Repair steps** (rewrite cells when Decision documents it): 2 Holiday,
      5 Level jump, 6 Rebuild TR, 7 Spike / distribution-day, 9 Frozen tails,
      10 US T-Bill fill.
    - **Diagnostic-only steps** (score flags; no rewrite): 3 Gap, 4 Scale
      shift, 8 Far from index.
    - **Export:** Step 11 is the sole workbook write.

    **Excel export:** Step 11 writes a **separate** cleaned workbook
    (`output-data/v2-funds-normalized-cleaned.xlsx`). The input
    `v2-funds-normalized.xlsx` is left unchanged. Earlier steps keep corrections
    in memory only. **Do not auto-write Excel on open.**
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        ## 1. Load daily series
        """
    )
    return


@app.cell
def _():
    from pathlib import Path

    import pandas as pd

    from helpers.timeseries_functions.replace_yahoo_tr import (
        YAHOO_TR_REPLACEMENTS,
        replace_datastream_tr_with_yahoo,
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
    _columns_on_sheet = int(len(_catalog_all))
    _columns_loaded = int(len(_catalog))
    _columns_skipped = _columns_on_sheet - _columns_loaded
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
    _first_date = pd.Series(pd.NaT, index=_observations.columns, dtype="datetime64[ns]")
    _last_date = pd.Series(pd.NaT, index=_observations.columns, dtype="datetime64[ns]")
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

    # Replace Datastream/Lipper Price + TR for funds where Yahoo is clean
    # (level jumps on Lipper). CFIMX is not in YAHOO_TR_REPLACEMENTS — Yahoo
    # still has a level jump there.
    _catalog, _observations, _yahoo_tr_log = replace_datastream_tr_with_yahoo(
        _catalog, _observations
    )

    label_rows = _label_rows
    workbook = _workbook
    sheet_name = _sheet_name
    catalog = _catalog
    observations = _observations
    columns_on_sheet = _columns_on_sheet
    columns_loaded = _columns_loaded
    columns_skipped = _columns_skipped
    yahoo_tr_log = _yahoo_tr_log
    yahoo_tr_replacements = YAHOO_TR_REPLACEMENTS

    return (
        catalog,
        columns_loaded,
        columns_on_sheet,
        columns_skipped,
        label_rows,
        observations,
        pd,
        sheet_name,
        workbook,
        yahoo_tr_log,
        yahoo_tr_replacements,
    )


@app.cell
def _(
    catalog,
    columns_loaded,
    columns_on_sheet,
    columns_skipped,
    md,
    mo,
    observations,
    review_table,
    selection_stats,
    sheet_name,
    stack,
    step_sections,
    workbook,
    yahoo_tr_log,
    yahoo_tr_replacements,
):
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _parsed_dates = observations.index.dropna()
    _missing_dates = int(observations.index.isna().sum())
    _note_counts = (
        catalog.groupby("note", dropna=False)
        .agg(columns=("column", "size"), ids=("id", "nunique"))
        .reset_index()
        .sort_values(["columns", "note"], ascending=[False, True])
    )
    _category_counts = (
        catalog.groupby("category", dropna=False)
        .agg(columns=("column", "size"), ids=("id", "nunique"))
        .reset_index()
        .sort_values(["columns", "category"], ascending=[False, True])
    )
    _yahoo_replaced = yahoo_tr_log.loc[yahoo_tr_log["status"].eq("replaced")]
    _yahoo_lines = [
        f"- `{row.isin}` → Yahoo `{row.ticker}`: "
        f"TR **{int(row.tr_days_filled):,}** filled / "
        f"**{int(row.tr_days_blank):,}** blank; "
        f"Price **{int(row.price_days_filled):,}** filled / "
        f"**{int(row.price_days_blank):,}** blank"
        for row in yahoo_tr_log.itertuples(index=False)
    ]
    _yahoo_list_md = (
        "\n".join(_yahoo_lines) if _yahoo_lines else "_No Yahoo Price+TR replacements._"
    )
    _ticker_bullets = "\n".join(
        f"- `{isin}` → `{ticker}`"
        for isin, ticker in sorted(yahoo_tr_replacements.items())
    )
    _step_view = step_sections(
        documentation=stack(
            selection_stats(_n_ids, _n_cols),
            md("""
            ### What and why

            Empirical chapters use daily **total returns**, the **S&P 500 TR**
            benchmark, and the **US T-Bill 3M** risk-free rate. The main S&P
            series for QA and for regressions is **`S&P 500 TR` / `S&P 500 TR %`**
            (Lipper `.SPXTR`). The workbook also carries an S&P **Composite** TR
            / `%` pair and a Composite price *level*; we keep the Composite TR /
            `%` columns for information and minor side work (e.g. funds whose
            Lipper benchmark is `.INX` → `S&P 500 C Price %`), not as the
            primary market reference. Holding every column in memory is
            unnecessary: this step therefore loads only the series the notebook
            and the study require (and skips TNA plus the Composite price
            *level*).

            For seven funds, Datastream/Lipper has lasting level jumps
            (corporate-action scaling), while Yahoo is clean under the same
            daily consistency checks. Those funds' primary `{ISIN} Price` /
            `{ISIN} Price %` and `{ISIN} TR` / `{ISIN} TR %` columns are
            **replaced with Yahoo** here so Price and TR stay a coherent pair
            for later QA/repair steps. The fund Clipper (`US1888501012` / CFIMX) is not
            replaced — both Datastream/Lipper and Yahoo have a level jump there and we will fix that series in a later step.
            """),
            md(
                "Hardcoded ISIN→ticker map (funds whose Datastream/Lipper "
                "Price + TR series were replaced with Yahoo Finance):"
            ),
            mo.md(_ticker_bullets),
            md("""
            ### How

            1. **Source.** Read sheet `D-Timeseries final` of
               `output-data/v2-funds-normalized.xlsx` with no header.
            2. **Label rows.** Rows 1–6 store `id`, `name`, `category`,
               `fee (%/year)`, `Note`, and the short header for each series
               column.
            3. **Column filter.** Keep:
               - every series whose note starts with `Total return` (fund TR
                 levels **and** `S&P 500 Composite TR`);
               - `S&P 500 TR` / `S&P 500 TR %` — primary benchmark for later QA
                 and for regressions (Lipper `.SPXTR`);
               - daily simple returns whose header contains ` TR %` or
                 ` Price %` (includes `S&P 500 C TR %` and `S&P 500 C Price %`);
               - `US T-Bill 3M`;
               - paired `Price` / `Price %` columns (inputs to distribution and
                 level-break repairs only).
               **Skip only:** total net assets (TNA) and the single
               `S&P 500 Composite Price` *price-index level*
               (`note = Price index, daily`). Skipped columns stay on the input
               workbook and are omitted from the cleaned export. The Composite
               **TR** level and Composite **%** returns stay loaded for
               information / minor side work (e.g. `.INX` →
               `S&P 500 C Price %`); they are **not** the QA or regression
               benchmark — that is `S&P 500 TR %` (`.SPXTR`).
            4. **Catalog and observations.** Turn the filtered sheet into two
               working tables, then free the full Excel frame:
               - **Catalog** — one row per kept series: id, name, category,
                 fee, note, header, and Excel column index. Coverage is
                 computed on the kept columns and stored on this same table
                 (`observations` count, `first_date`, `last_date`).
               - **Observations** — the daily numeric panel (date index × kept
                 columns). Dates are parsed and values coerced to numbers;
                 unreadable cells become blank (`NaN`).
               - **Memory.** Drop the full-sheet frame (`_raw`) so later steps
                 hold only catalog + observations. Export dumps those two
                 tables into a cleaned workbook (kept columns only; skipped
                 series are not written).
            5. **Yahoo Price + TR replace.** For the seven ISINs above, fetch
               Yahoo unadjusted Close (`auto_adjust=False`) into Price / Price %,
               and adjusted Close (`auto_adjust=True`) into TR / TR %. Align both
               to the panel dates; S&P-flat holidays are left NA (Step 2 also
               normalises the full panel). Daily returns use session-to-session
               `P(t)/P(last trade) - 1` after skipping closure rows
               (avoids a second missing return on the next session). Other dates
               without a Yahoo print stay blank. Headers stay the primary
               `{ISIN} Price` / `{ISIN} TR` names.
            """),
        ),
        result=stack(
            mo.md(
                f"- **File:** `{workbook}`, sheet `{sheet_name}` \n"
                f"- **{len(observations):,}** dates, from "
                f"**{_parsed_dates.min():%Y-%m-%d}** to "
                f"**{_parsed_dates.max():%Y-%m-%d}** \n"
                f"- **{_missing_dates:,}** rows have no date \n"
                f"- **{columns_on_sheet:,}** series on the sheet → "
                f"**{columns_loaded:,}** loaded, **{columns_skipped:,}** skipped "
                f"(TNA + `S&P 500 Composite Price` level only; Composite TR / "
                f"C % remain loaded for info / side work, not as `.SPXTR` "
                f"benchmark) \n"
                f"- **{_n_cols:,}** series columns in memory, **{_n_ids:,}** ids \n"
                f"- **Yahoo Price+TR replace:** **{len(_yahoo_replaced):,}** of "
                f"**{len(yahoo_tr_replacements):,}** funds replaced \n"
            ),
            md("### Yahoo Price + TR replacements"),
            mo.md(_yahoo_list_md),
            review_table(yahoo_tr_log, "Yahoo Price+TR replacement log"),
            review_table(_note_counts, "Loaded columns by note"),
            review_table(_category_counts, "Loaded columns by category"),
            review_table(catalog, "Daily series catalog (loaded)"),
        ),
        decision=stack(
            md("""
            The working sample is the filtered panel: total returns, primary
            **`S&P 500 TR` / `TR %`** (Lipper `.SPXTR` — the series used for QA
            and for regressions), US T-Bill 3M, paired Price series for repairs,
            and the Composite TR / `%` pair (kept for information and minor side
            work such as `.INX` → `S&P 500 C Price %`). **Not loaded:** TNA and
            the `S&P 500 Composite Price` price-index level only. Later
            QA/repair steps and the main regressions compare funds to
            **`S&P 500 TR %`**, not to the Composite series.

            **Yahoo Price + TR:** replaced Datastream/Lipper Price and total
            return with Yahoo for the funds below (unadjusted Close → Price;
            adjusted Close → TR). Later level-break rescales skip these ISINs so
            Datastream corporate-action factors are not applied to Yahoo history.
            CFIMX is still Datastream (Yahoo not clean).
            """),
            mo.md(_yahoo_list_md),
            selection_stats(_n_ids, _n_cols, when="end"),
        ),
    )
    _step_view
    return


@app.cell(hide_code=True)
def _(mo, run_step_button, step_header):
    run_holiday = run_step_button()
    _header = step_header("## 2. Holiday calendar", run_holiday)
    _header
    return (run_holiday,)


@app.cell
def _(
    catalog,
    carry_holiday_placeholders,
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
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _documentation = stack(
        selection_stats(_n_ids, _n_cols),
        md("""
        ### What and why

        Exchange closures still leave a date row in the panel. Datastream padding
        often repeats levels with a **zero** return; Yahoo may omit the print.
        For **every** index and fund Price/TR pair in the working panel, Step 2
        sets **level and daily % to NA** on US exchange holidays so non-trading
        days are not treated as observations. The **next session’s %** is
        recomputed from the last trade (`level_t / level_{last trade} - 1`).
        Later gap checks exempt those dates via the S&P-flat holiday calendar.

        ### Holiday rule

        A date is an exchange holiday when the S&P 500 TR level equals the prior
        close (within tolerance). On that date, for every paired level / % column:
        set level = NA and return = NA; on the following session with a valid
        level, set return from the prior **trading** close. Series already NA on
        a holiday (e.g. Yahoo) are still walked; `cells_changed` only counts
        values that actually differed.
        """),
    )
    _holiday = get_holiday()
    if _holiday is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to identify S&P-flat holidays and blank "
                "level/% on those dates for all paired series._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _correction_log = _holiday["correction_log"]
        _holiday_dates = _holiday["holiday_dates"]
        _holiday_count = len(_holiday_dates)
        _n_series_blanked = len(_correction_log)
        _n_ids_blanked = (
            int(_correction_log["id"].nunique()) if len(_correction_log) else 0
        )
        _n_cells = (
            int(_correction_log["cells_changed"].sum()) if len(_correction_log) else 0
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{_holiday_count:,}** S&P-flat exchange holidays identified \n"
                    f"- **{_n_series_blanked:,}** level series blanked on those dates "
                    f"(**{_n_ids_blanked:,}** ids; each row is one Price or TR level, "
                    f"with its paired %) \n"
                    f"- **{_n_cells:,}** cells whose values changed (holiday level/% "
                    f"set to NA, and/or next-session % recomputed; already-NA cells "
                    f"do not increment this count) \n"
                ),
                review_table(_correction_log, "Series with holiday NA applied"),
            ),
            decision=stack(
                md("""
                **Decision:** keep every series column. Blank **all** paired
                Price/TR levels and daily % on every S&P-flat holiday; recompute
                the next session’s % from the last trading close. No ids are
                dropped. The post-holiday observations frame is retained for the
                gap check and later consistency steps.
                """),
                mo.md(
                    f"- **{_holiday_count:,}** holidays blanked across the panel \n"
                    f"- **{_n_series_blanked:,}** level series / **{_n_ids_blanked:,}** "
                    f"ids touched; **{_n_cells:,}** cells changed \n"
                ),
                review_table(_correction_log, "Holiday blanking log"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_holiday, mo, run_step_button, step_header):
    _ready = get_holiday() is not None
    run_gap = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 2 first")
    _header = step_header("## 3. Gap", run_gap)
    _header
    return (run_gap,)


@app.cell
def _(
    catalog,
    get_holiday,
    run_gap,
    set_gap,
    summarize_tr_consistency,
):
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
    get_gap,
    get_holiday,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
    flag_summary_table,
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
def _(get_gap, mo, run_step_button, step_header):
    _ready = get_gap() is not None
    run_scale = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 3 first")
    _header = step_header("## 4. Scale shift", run_scale)
    _header
    return (run_scale,)


@app.cell
def _(catalog, get_gap, run_scale, set_scale, summarize_tr_consistency):
    if run_scale.value:
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
    get_gap,
    get_scale,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
    flag_summary_table,
):
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

        **Question asked:** did the fund's *usual* daily move size permanently
        change (wrong units, or a lasting new volatility scale)? Re-check on the
        post-holiday panel. No series is rewritten here.

        This step’s Result is diagnostic. Later level-jump and spike screens do
        **not** read a stored split date from this payload. When those steps call
        `summarize_tr_consistency`, scale is **re-detected as a prerequisite** on
        the current panel (`_FLAG_REQUIRES`), and that fresh split suppresses
        post-split level jumps / spikes for that scoring pass only.

        **Idea:** compare median `|return|` locally (126 days before vs after a
        candidate split) and globally (prefix vs suffix medians). Flag only when
        both local and global folds are ≥ 5× or both ≤ 1/5.
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
                a stored state. When Steps 5 and 7 score level jumps / spikes,
                they re-detect scale on the current panel as a prerequisite and
                use that fresh split to suppress post-split regimes for that
                pass only.
                """),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_scale, mo, run_step_button, step_header):
    _ready = get_scale() is not None
    run_level_jump = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 4 first")
    _header = step_header("## 5. Level jump", run_level_jump)
    _header
    return (run_level_jump,)


@app.cell
def _(
    catalog,
    get_scale,
    rescale_level_breaks,
    run_level_jump,
    set_level_jump,
    summarize_tr_consistency,
):
    if run_level_jump.value:
        _scale = get_scale()
        if _scale is None:
            raise ValueError("Level jump step requires scale output")
        _observations = _scale["observations"]
        _controls, _issue_summary, _checks = summarize_tr_consistency(
            catalog, _observations, flags=("level_jump",)
        )
        _adjusted, _action_log = rescale_level_breaks(catalog, _observations)
        set_level_jump(
            {
                "observations": _adjusted,
                "controls": _controls,
                "issue_summary": _issue_summary,
                "checks": _checks,
                "action_log": _action_log,
            }
        )
    return


@app.cell
def _(
    catalog,
    get_scale,
    get_level_jump,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
    flag_summary_table,
):
    mo.stop(
        get_scale() is None,
        mo.md("Run step 4 first."),
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

        **Question asked:** is there a day so large that the series looks
        *permanently* relocated — a broken level, unadjusted split/rebase, or
        master-portfolio switch — rather than a one-day spike that reverses?

        Spikes (≥10%, often with a give-back) and “far from index” (≥5%) are
        handled in later steps. Level jump is reserved for sticky, market-odd
        breaks that would corrupt every later cumulative return if left alone.

        ### Dual detectors (Result vs repair)

        This step uses **two** related detectors on purpose. They share the same
        economic thresholds but differ in universe and side-effects:

        1. **Detector A — Result** (`summarize_tr_consistency` →
           `locate_series_issues` with ``flags=("level_jump",)``). Scores every
           fund **TR %** series versus S&P 500 TR % (including Yahoo
           replacements from Step 1). Scale is pulled in as a prerequisite so
           days on or after a detected scale-shift split are **not** re-flagged
           as level jumps. Result tables come only from Detector A.

        2. **Detector B — repair scan** (`lasting_breaks` inside
           `rescale_level_breaks`). Scans both **Price %** and **TR %** for the
           same sticky break shape (`|return| ≥ 50%`, `|return − S&P| ≥ 25%`,
           compounded follow-through ≥ half the jump). It does **not** suppress
           post-scale regimes. Hand-coded corporate-action rules fire only when
           Detector B still sees the break on the current panel.

        **Decision reconciliation:** keep every series; list only funds that
        **Detector A flagged** (same ISIN set as Result). For those funds, apply
        the matching `level_actions` / `kept_distributions` rule when Detector B
        still sees the break (rescale / keep), or note that no rule applied
        (`not adjusted`). Yahoo-replaced ISINs have no Datastream
        corporate-action entries in `level_actions` (Step 1 already swapped
        those series). Pure **Price-only** Detector B hits that never appear in
        Detector A (distribution NAV drops without a TR level jump) stay out of
        both Result and Decision by design.

        ### Detection rule (shared thresholds)

        A day is a **level jump** when all of the following hold:

        1. fund `|return| ≥ 50%`;
        2. `|fund − S&P 500 TR %| ≥ 25%`;
        3. the move **sticks**: compounded return over the next sessions stays
           at least half as large as the initial jump;
        4. **Detector A only:** the day is **not** on or after a detected
           scale-shift split.

        The 50% / 25% bar is intentionally high: it targets corporate-action
        mis-scaling (often near ±50% or larger), not ordinary crash volatility.
        """),
        mo.mermaid(
            _mermaid_init
            + """
flowchart LR
  subgraph jump["Level jump — move sticks"]
    direction LR
    j1["… +1%"] --> j2["+60% vs S&P"] --> j3["+2%"] --> j4["+1%"]
  end
  subgraph notjump["Not a level jump — reverses"]
    direction LR
    n1["… +1%"] --> n2["+60%"] --> n3["−55%"] --> n4["+1%"]
  end
"""
        ),
    )
    _level_jump = get_level_jump()
    if _level_jump is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to score level jumps and rescale breaks._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _issue_summary = _level_jump["issue_summary"]
        _jump_table = flag_summary_table(_issue_summary, "level_jumps")
        _action_log = _level_jump["action_log"]
        # Decision mirrors Result (Detector A): same ISIN set as the level-jump table.
        _jump_isins = set(_jump_table["id"].astype("string").str.strip())
        _decision_log = _action_log.loc[
            _action_log["isin"].astype("string").str.strip().isin(_jump_isins)
            & ~_action_log["decision"].eq("already rescaled")
        ].reset_index(drop=True)
        _rescaled = _decision_log.loc[_decision_log["decision"].eq("rescaled")]
        _kept = _decision_log.loc[_decision_log["decision"].eq("kept")]
        _not_adjusted = _decision_log.loc[_decision_log["decision"].eq("not adjusted")]
        _rescaled_funds = int(_rescaled["isin"].nunique()) if len(_rescaled) else 0
        _kept_funds = int(_kept["isin"].nunique()) if len(_kept) else 0
        _not_adjusted_funds = (
            int(_not_adjusted["isin"].nunique()) if len(_not_adjusted) else 0
        )
        # Detector B hits on this run (lasting_breaks → action_log.detected).
        _detected_log = _action_log.loc[_action_log["detected"].astype(bool)].copy()
        _detector_b_isins = (
            set(_detected_log["isin"].astype("string").str.strip())
            if len(_detected_log)
            else set()
        )
        _price_only_b = sorted(_detector_b_isins - _jump_isins)
        _covered_isins = set(_decision_log["isin"].astype("string").str.strip())
        _context_lines = []
        for _row in (
            _decision_log.sort_values(["date", "isin", "series"])
            .drop_duplicates(subset=["isin", "date"], keep="first")
            .itertuples(index=False)
        ):
            _context_lines.append(
                f"- **{_row.fund}** (`{_row.isin}`), {_row.date} — "
                f"{_row.decision}: {_row.why}"
            )
        for _isin in sorted(_jump_isins - _covered_isins):
            _fund_rows = catalog.loc[
                catalog["id"].astype("string").str.strip().eq(_isin), "name"
            ]
            _fund = (
                str(_fund_rows.iloc[0]) if len(_fund_rows) else _isin
            )
            _context_lines.append(
                f"- **{_fund}** (`{_isin}`) — flagged in Result (Detector A); "
                f"no corporate-action rule applied this run"
            )
        _context_md = (
            "### Corporate-action context (by fund)\n\n" + "\n".join(_context_lines)
            if _context_lines
            else "_No level-jump flags in Result — nothing to decide._"
        )
        _decision_bullets = [
            f"- **Detector A (Result):** **{len(_jump_table):,}** TR % series "
            f"with a level-jump flag",
            f"- **Detector B (repair scan):** **{len(_detector_b_isins):,}** "
            f"ISINs with a lasting Price/TR break still detected this run",
            f"- **Decision set:** Result ISINs only "
            f"(**{len(_jump_isins):,}** funds); "
            f"**{len(_price_only_b):,}** Detector-B-only "
            f"(Price-side) ISINs excluded from Decision",
        ]
        if _rescaled_funds:
            _decision_bullets.append(
                f"- **{_rescaled_funds:,}** funds rescaled "
                f"(**{len(_rescaled):,}** Price/TR columns), "
                f"**{int(_rescaled['cells'].sum()) if len(_rescaled) else 0:,}** "
                f"cells changed"
            )
        if _kept_funds:
            _decision_bullets.append(
                f"- **{_kept_funds:,}** funds with distribution / liquidation "
                f"price drops kept unchanged"
            )
        if _not_adjusted_funds:
            _decision_bullets.append(
                f"- **{_not_adjusted_funds:,}** funds with a lasting break and "
                f"no corporate-action rule (left unchanged)"
            )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **Detector A** (`locate_series_issues` on TR %): "
                    f"**{len(_jump_table):,}** series with level-jump flags "
                    f"(includes Yahoo replacements) \n"
                    f"- **{int(_issue_summary['level_jumps'].sum()):,}** flagged "
                    f"days (sum) \n"
                    f"- **Detector B** (`lasting_breaks` on Price % and TR %) "
                    f"drives which corporate-action rules still fire; Decision "
                    f"keeps only Detector A ISINs (see Decision) \n"
                ),
                review_table(_jump_table, "Series with level jumps (Detector A)"),
            ),
            decision=stack(
                md("""
                Keep all series. **Decision = Detector A ISINs** (Result). For
                each, apply the matching corporate-action rule when Detector B
                still sees the break (rescale), or leave unchanged when the rule
                says keep / no rule (`not adjusted`). Yahoo-replaced funds are
                not in `level_actions`.

                Price-only Detector B hits that never flag as TR level jumps in
                Result do not appear here.
                """),
                mo.md("\n".join(_decision_bullets) + "\n"),
                md(_context_md),
                review_table(_decision_log, "Level break actions (Result funds)"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_level_jump, mo, run_step_button, step_header):
    _ready = get_level_jump() is not None
    run_rebuild = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 5 first")
    _header = step_header("## 6. Rebuild TR from distributions (Lipper gate)", run_rebuild)
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
    selection_stats,
    stack,
    step_sections,
):
    mo.stop(
        get_level_jump() is None,
        mo.md("Run step 5 first."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _documentation = stack(
        selection_stats(_n_ids, _n_cols),
        md("""
        ### What and why

        **Question asked:** for each fund, do the **3-year, 5-year, and 10-year
        cumulative total returns** implied by our daily TR series match the
        **Lipper published** 3y / 5y / 10y total returns for that same fund?

        Lipper is the external reference. The gap on each horizon is:

        `gap = (return from our daily TR series) − (Lipper published return)`
        in percentage points. Both sides are measured through
        **`LIPPER_AS_OF = 2026-09-30`** (the Funds-sheet Lipper month-end used by
        `regress_daily_to_benchmark.py`); daily TR is clipped to that date before
        compounding to months.

        Some Datastream TR paths are wrong on distribution reinvestment days.
        For every fund we therefore also build a **candidate** daily TR from
        Datastream price/NAV plus cash distributions (Yahoo first, then FMP
        cache) via `r_t = (P_t + D_t) / P_{t-1} − 1`, and score that candidate
        the same way against Lipper.

        ### Pass / fail rule (Result)

        Tolerance is **0.5 pp** (`LIPPER_CLOSE_PP`). All three horizons are
        measured; scoring uses the **longest available** gap:

        1. **10y** when Lipper 10y exists and the series has ≥120 months
        2. else **5y** when that window is available
        3. else **3y**
        4. else **unscored** (no Lipper figure and/or too little history)

        - **Pass** — `|gap| ≤ 0.5` pp on the chosen horizon
        - **Fail** — `|gap| > 0.5` pp on the chosen horizon
        - **Unscored** — none of 10y / 5y / 3y can be scored

        Result reports how Datastream TR and the rebuild candidate each score
        on that test. It does **not** choose which series to keep.

        ### Decision policy (production)

        Keep every fund in the panel. Replace Datastream TR with the
        distribution rebuild when the Lipper gate says the candidate is already
        within 0.5 pp on its primary available horizon (10y → 5y → 3y), or
        improves that shared gap (shorter horizons break ties). Otherwise keep
        Datastream TR. See
        `helpers/timeseries_functions/rebuild_tr_from_distributions.py`.

        **Hard no-distribution veto.** If neither Yahoo nor the FMP cache
        supplies any cash distribution for the fund (`dist_source == "none"`)
        **and** the fund is not treated as index-like, adoption is **forced
        off** — Datastream TR is kept even when the Lipper close-or-improve
        comparison would otherwise prefer the candidate. Index-like names with
        no distributions may still fill missed ex-days from S&P before the gate.

        **Post-adopt transparency.** After the production gate runs, Decision
        reports how many *adopted* rebuild paths still **fail** Lipper
        (`|gap| > 0.5` pp on the primary horizon). Those are improvements that
        remain outside tolerance — not passes.

        **Sensitivity (not applied).** An adopt-only-if-pass counterfactual
        would adopt only when the rebuild already passes. Decision reports how
        many production adopts that stricter rule would refuse. The panel keeps
        the production (close-or-improve) rule; the sensitivity is diagnostic.
        """),
    )
    _rebuild = get_rebuild()
    if _rebuild is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to score Datastream and rebuilt TR "
                "against Lipper 3y / 5y / 10y._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        from helpers.timeseries_functions.rebuild_tr_from_distributions import (
            LIPPER_CLOSE_PP as _LIPPER_CLOSE_PP,
            LIPPER_TEST_HORIZONS as _LIPPER_TEST_HORIZONS,
            lipper_test_status as _lipper_test_status,
            summarize_rebuild_gate_transparency as _summarize_rebuild_gate,
        )

        _rebuild_log = _rebuild["rebuild_log"].copy()
        _adopted = (
            int(_rebuild_log["decision"].eq("adopted").sum()) if len(_rebuild_log) else 0
        )
        _kept = len(_rebuild_log) - _adopted

        def _gaps_from_row(row: "pd.Series", *, side: str) -> dict[str, float]:
            return {
                horizon: row.get(f"gap_{horizon}_{side}")
                for horizon in _LIPPER_TEST_HORIZONS
            }

        if len(_rebuild_log) and "gap_10y_before" in _rebuild_log.columns:
            _ds_status = []
            _ds_horizon = []
            _rb_status = []
            _rb_horizon = []
            _sort_gap = []
            for _row in _rebuild_log.itertuples(index=False):
                _row_s = pd.Series(_row._asdict())
                _ds_s, _ds_h = _lipper_test_status(_gaps_from_row(_row_s, side="before"))
                _rb_s, _rb_h = _lipper_test_status(_gaps_from_row(_row_s, side="after"))
                _ds_status.append(_ds_s)
                _ds_horizon.append(_ds_h if _ds_h is not None else pd.NA)
                _rb_status.append(_rb_s)
                _rb_horizon.append(_rb_h if _rb_h is not None else pd.NA)
                if _ds_h is not None:
                    _sort_gap.append(abs(float(_row_s[f"gap_{_ds_h}_before"])))
                else:
                    _sort_gap.append(float("nan"))
            _rebuild_log = _rebuild_log.assign(
                datastream_vs_lipper=pd.Series(_ds_status, dtype="string"),
                datastream_lipper_horizon=pd.Series(_ds_horizon, dtype="string"),
                rebuild_vs_lipper=pd.Series(_rb_status, dtype="string"),
                rebuild_lipper_horizon=pd.Series(_rb_horizon, dtype="string"),
            )
            _ds_pass = int((_rebuild_log["datastream_vs_lipper"] == "pass").sum())
            _ds_fail = int((_rebuild_log["datastream_vs_lipper"] == "fail").sum())
            _ds_unscored = int(
                (_rebuild_log["datastream_vs_lipper"] == "unscored").sum()
            )
            _rb_pass = int((_rebuild_log["rebuild_vs_lipper"] == "pass").sum())
            _rb_fail = int((_rebuild_log["rebuild_vs_lipper"] == "fail").sum())
            _rb_unscored = int((_rebuild_log["rebuild_vs_lipper"] == "unscored").sum())
            _sorted = _rebuild_log.assign(_abs_gap=_sort_gap).sort_values(
                "_abs_gap", ascending=False
            ).drop(columns="_abs_gap")
        else:
            _ds_pass = _ds_fail = _ds_unscored = 0
            _rb_pass = _rb_fail = _rb_unscored = 0
            _sorted = _rebuild_log

        _gate_summary, _adopted_still_fail = _summarize_rebuild_gate(
            _rebuild_log, close_pp=_LIPPER_CLOSE_PP
        )
        _decision_parts = [
            md("""
            Keep all series. Where the Lipper gate prefers the distribution
            rebuild over Datastream, replace that fund’s TR % / TR level with
            the rebuilt path; otherwise leave Datastream TR unchanged. Horizons
            are evaluated through **`LIPPER_AS_OF = 2026-09-30`**. Funds with
            **no Yahoo/FMP distributions** and not index-like never adopt
            (hard veto), regardless of the close-or-improve comparison.

            Production rule remains **close-or-improve** subject to that veto.
            The counts below disclose residual Lipper fails among adopts and the
            adopt-only-if-pass counterfactual (not applied to the panel).
            """),
            mo.md(
                f"- **{_adopted:,}** adopted the distribution rebuild \n"
                f"- **{_kept:,}** kept Datastream TR \n"
                f"- **Post-adopt Lipper status (among adopted):** "
                f"**{_gate_summary['adopted_pass']:,}** pass, "
                f"**{_gate_summary['adopted_fail']:,}** fail, "
                f"**{_gate_summary['adopted_unscored']:,}** unscored "
                f"(tolerance **{_LIPPER_CLOSE_PP:g} pp**) \n"
                f"- **Sensitivity — adopt-only-if-pass (not applied):** "
                f"would adopt **{_gate_summary['strict_would_adopt']:,}**, "
                f"keep **{_gate_summary['strict_would_keep']:,}**; "
                f"**{_gate_summary['adopted_under_both']:,}** overlap with "
                f"production; **{_gate_summary['adopted_only_under_production']:,}** "
                f"production adopts the stricter rule would refuse \n"
            ),
        ]
        if len(_adopted_still_fail):
            _decision_parts.extend(
                [
                    md(
                        "### Adopted rebuilds that still fail Lipper\n\n"
                        "These funds were adopted because the rebuild **improved** "
                        "the gap (or tied through shorter horizons) but the "
                        "candidate remains outside **0.5 pp**. Under "
                        "adopt-only-if-pass they would keep Datastream TR."
                    ),
                    review_table(
                        _adopted_still_fail,
                        "Production adopts still failing Lipper",
                    ),
                ]
            )
        else:
            _decision_parts.append(
                md(
                    "_No production adopts still fail Lipper on the primary "
                    "horizon — every adopted rebuild is a pass or unscored._"
                )
            )
        _decision_parts.append(selection_stats(_n_ids, _n_cols, when="end"))

        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{len(_rebuild_log):,}** funds scored vs Lipper "
                    f"(pass/fail on longest available of **10y → 5y → 3y**, "
                    f"tolerance **{_LIPPER_CLOSE_PP:g} pp**) \n"
                    f"- **Datastream TR:** **{_ds_pass:,}** pass, "
                    f"**{_ds_fail:,}** fail, **{_ds_unscored:,}** unscored \n"
                    f"- **Rebuild candidate** (NAV + distributions): "
                    f"**{_rb_pass:,}** pass, **{_rb_fail:,}** fail, "
                    f"**{_rb_unscored:,}** unscored \n"
                    f"- **Unscored** means none of 10y / 5y / 3y could be "
                    f"tested — almost always because Lipper has **no published "
                    f"performance** on those horizons for the fund (fallback "
                    f"cannot help when every Lipper figure is missing); rarely "
                    f"because the daily series is shorter than 3 years \n"
                ),
                review_table(_sorted, "Lipper horizon test (Datastream vs rebuild)"),
            ),
            decision=stack(*_decision_parts),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_rebuild, mo, run_step_button, step_header):
    _ready = get_rebuild() is not None
    run_spike = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 6 first")
    _header = step_header("## 7. Spike", run_spike)
    _header
    return (run_spike,)


@app.cell
def _(
    catalog,
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
            catalog, _observations, flags=("spikes",)
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
    get_rebuild,
    get_spike,
    md,
    mo,
    pd,
    review_table,
    selection_stats,
    stack,
    step_sections,
    flag_summary_table,
):
    mo.stop(
        get_rebuild() is None,
        mo.md("Run step 6 first."),
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

        **Question asked:** is there an abnormal large day that reverses the
        next day or is largely not shared with the S&P? **Reversal:** `|r| ≥ 10%`,
        opposite sign next day, two-day compound inside ±15%, S&P does not show
        the same reversal (`|m| ≥ 5%` with give-back). **Isolated:** `|r| ≥ 10%`
        and `|fund − S&P| ≥ |fund| / 2`.

        **Suppressions (automated screen).** A day is **not** flagged as a spike
        when it falls on/after a re-detected scale-shift split (`~on_new_scale`)
        or on a day already flagged as a level jump (`~level_shift`), or when it
        is the second day of a reversal pair. Scale and level-jump are pulled in
        as prerequisites of `flags=("spikes",)` and recomputed on this panel.

        ### Result vs Decision (two complementary views)

        Result and Decision are **not** the same filter. They must be read
        together via the crosswalk table after Run:

        1. **Result — automated spike screen, scored pre-repair.** Every fund
           TR % is scored with the shared helper (`flags=("spikes",)`) **before**
           `repair_distribution_day_tr` runs. Ordinary spike flags are
           **diagnostic**: they are not auto-rewritten, and Result does **not**
           re-score after curated repairs.
        2. **Decision — curated distribution-day list + kept genuine spikes.**
           A hand-reviewed repair list (and a kept list) is applied only when
           the eligibility gate still fails on the **current** panel. A Decision
           day may therefore be **Result-only**, **Decision-only**, or **both**.

        Typical **Decision-only** cases: distribution-day TR errors that fail
        the Price/TR + market-residual gate screen used for repair eligibility
        but do not meet the automated spike predicates (or no longer do after
        Yahoo / rebuild). Typical **Result-only** cases: genuine large days
        left untouched because they are not on the curated repair list.
        """),
        mo.mermaid(
            _mermaid_init
            + """
flowchart TB
  subgraph rev["Reversal spike"]
    direction LR
    r1["Day t: fund +12%"] --> r2["Day t+1: fund −11%"]
  end
  subgraph iso["Isolated spike"]
    direction LR
    i1["Day t: fund +12%"] --> i2["S&P only +1%"]
  end
"""
        ),
    )
    _decision_policy = md("""
        Keep all series. Curated distribution-day TR errors are rewritten only
        when still defective; ordinary Result spike flags without a curated
        rule are left alone.

        **Eligibility gate (required for rewrite).** A curated day is rewritten
        only if both hold on the **current** panel (after Yahoo replace /
        rebuild): `|TR% − Price%| ≥ 1%` **and** `|TR% − S&P 500 TR %| ≥ 1%`.
        Correct ex-distribution days (Price down, TR ≈ market) fail the
        market-residual gate and are logged as `skipped — already clean`. Days
        that left the panel are skipped silently.

        **Why defective days look wrong.** On an ex-distribution day the
        published NAV (price) falls by roughly the cash amount. A correct
        total-return series should add that cash back, so TR moves with the
        market. Defective prints disagree: either the distribution was never
        added (TR too low while price crashed), or it was added at the wrong
        scale (TR spikes while price falls a few percent).

        **How the repair works (when the gate passes).**

        1. **Forward (most cases).** Set that day’s TR % to the S&P 500 TR %
           and rescale every later TR level so the bad day does not stay in
           the path forever. Use this when the error is baked into subsequent
           levels (typical omitted / mis-scaled distribution add-back).
        2. **One-day.** Replace only that day’s TR level / return with the
           fund’s own price return, then recompute the next return. Use this
           when the spike reverses the next day and later levels are already
           right (American Growth, Dec 2025).

        **Why the S&P return is the proxy.** For the forward cases we do not
        have a confirmed cash amount that would rebuild TR from NAV +
        distribution on that single day. Index-like and broad equity funds
        should track the market within a few percent on a distribution day;
        substituting the S&P TR for that one session is the least-assuming
        fix on days that still fail the eligibility gate.

        **What we keep.** Spikes where price and TR move together (March 2020
        crash days, hedge payoffs, lasting NAV jumps) are genuine moves —
        logged as kept, not rewritten. The Result↔Decision crosswalk marks
        these as overlapping when the same ISIN also carries a Result spike
        flag.
        """)
    _spike = get_spike()
    if _spike is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to score the pre-repair spike screen "
                "(scale / level-jump days suppressed), apply gated distribution "
                "repairs, and build the Result↔Decision crosswalk._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                _decision_policy,
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _controls = _spike["controls"]
        _spike_table = flag_summary_table(_spike["issue_summary"], "spikes")
        _distribution_log = _spike["distribution_log"].copy()
        _result_isins = set(_spike_table["id"].astype("string").str.strip())
        _distribution_log["in_result_spikes"] = (
            _distribution_log["isin"].astype("string").str.strip().isin(_result_isins)
        )
        _repaired_rows = _distribution_log.loc[_distribution_log["decision"].eq("repaired")]
        _skipped_clean = _distribution_log.loc[
            _distribution_log["decision"].eq("skipped — already clean")
        ]
        _kept_rows = _distribution_log.loc[_distribution_log["decision"].eq("kept")]
        _adj = _repaired_rows["adjustment"].astype("string")
        _n_forward = int(_adj.str.contains("S&P return", regex=False, na=False).sum())
        _n_one_day = int(_adj.str.contains("price return", regex=False, na=False).sum())
        _n_already = int(_adj.eq("already matches").sum())

        # Crosswalk: Result spike ISINs ∪ Decision log ISINs.
        _decision_isins = set(_distribution_log["isin"].astype("string").str.strip())
        _cross_rows = []
        for _isin in sorted(_result_isins | _decision_isins):
            _in_result = _isin in _result_isins
            _in_decision = _isin in _decision_isins
            if _in_result and _in_decision:
                _overlap = "both"
            elif _in_result:
                _overlap = "result_only"
            else:
                _overlap = "decision_only"
            _fund_rows = catalog.loc[
                catalog["id"].astype("string").str.strip().eq(_isin), "name"
            ]
            _fund = str(_fund_rows.iloc[0]) if len(_fund_rows) else _isin
            for _suffix in (
                " - TOT RETURN IND",
                " - PRICE",
                " - TOTAL NET ASSETS",
            ):
                if _fund.endswith(_suffix):
                    _fund = _fund[: -len(_suffix)]
                    break
            _spike_count = 0
            if _in_result:
                _spike_count = int(
                    _spike_table.loc[
                        _spike_table["id"].astype("string").str.strip().eq(_isin),
                        "spikes",
                    ].sum()
                )
            _dec_part = _distribution_log.loc[
                _distribution_log["isin"].astype("string").str.strip().eq(_isin)
            ]
            _n_rep = int(_dec_part["decision"].eq("repaired").sum()) if len(_dec_part) else 0
            _n_skip = (
                int(_dec_part["decision"].eq("skipped — already clean").sum())
                if len(_dec_part)
                else 0
            )
            _n_kept = int(_dec_part["decision"].eq("kept").sum()) if len(_dec_part) else 0
            _cross_rows.append(
                {
                    "isin": _isin,
                    "fund": _fund,
                    "overlap": _overlap,
                    "result_spikes": _spike_count,
                    "decision_repaired": _n_rep,
                    "decision_skipped_clean": _n_skip,
                    "decision_kept": _n_kept,
                }
            )
        _crosswalk = pd.DataFrame(_cross_rows)
        if len(_crosswalk):
            _overlap_order = {"both": 0, "result_only": 1, "decision_only": 2}
            _crosswalk = _crosswalk.assign(
                _ord=_crosswalk["overlap"].map(_overlap_order)
            ).sort_values(["_ord", "isin"]).drop(columns="_ord").reset_index(drop=True)
        _n_both = int((_crosswalk["overlap"] == "both").sum()) if len(_crosswalk) else 0
        _n_result_only = (
            int((_crosswalk["overlap"] == "result_only").sum()) if len(_crosswalk) else 0
        )
        _n_decision_only = (
            int((_crosswalk["overlap"] == "decision_only").sum()) if len(_crosswalk) else 0
        )

        _context_lines = []
        for _row in (
            _distribution_log.sort_values(["date", "isin"])
            .itertuples(index=False)
        ):
            _flag = "also in Result" if _row.in_result_spikes else "Decision only"
            _context_lines.append(
                f"- **{_row.fund}** (`{_row.isin}`), {_row.date} — "
                f"{_row.decision} ({_row.adjustment}) [{_flag}]: {_row.why}"
            )
        _context_md = (
            "### Reviewed days (by fund)\n\n" + "\n".join(_context_lines)
            if _context_lines
            else "_No documented distribution days matched this panel._"
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{len(_spike_table):,}** series with automated spike "
                    f"flags (**pre-repair** Result screen; scale / level-jump "
                    f"days suppressed) \n"
                    f"- Controls: spike {_controls['spike_return']:.0%}, "
                    f"reversal band {_controls['reversal_band']:.0%} \n"
                    f"- **Result↔Decision crosswalk:** **{_n_both:,}** both, "
                    f"**{_n_result_only:,}** Result only, "
                    f"**{_n_decision_only:,}** Decision only \n"
                ),
                review_table(
                    _spike_table,
                    "Series with spikes (pre-repair Result screen)",
                ),
                review_table(
                    _crosswalk,
                    "Result↔Decision crosswalk (by ISIN)",
                ),
            ),
            decision=stack(
                _decision_policy,
                mo.md(
                    f"- **{len(_repaired_rows):,}** distribution days rewritten "
                    f"(**{_n_forward:,}** forward / S&P proxy, "
                    f"**{_n_one_day:,}** one-day"
                    + (
                        f", **{_n_already:,}** already matching"
                        if _n_already
                        else ""
                    )
                    + ") \n"
                    f"- **{len(_skipped_clean):,}** curated days skipped — "
                    f"already clean (TR≈market or Price≈TR) \n"
                    f"- **{int(_repaired_rows['cells'].sum()) if len(_repaired_rows) else 0:,}** "
                    f"cells changed \n"
                    f"- **{len(_kept_rows):,}** agreeing price+TR spikes left "
                    f"unchanged \n"
                    f"- **Crosswalk:** **{_n_both:,}** ISINs in both Result and "
                    f"Decision, **{_n_result_only:,}** Result only (no curated "
                    f"action), **{_n_decision_only:,}** Decision only "
                    f"(curated day without a current Result spike flag) \n"
                ),
                md(_context_md),
                review_table(
                    _crosswalk,
                    "Result↔Decision crosswalk (by ISIN)",
                ),
                review_table(
                    _distribution_log,
                    "Distribution-day repair log (in_result_spikes marks Result overlap)",
                ),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_spike, mo, run_step_button, step_header):
    _ready = get_spike() is not None
    run_wide = run_step_button(ready=_ready, tooltip=None if _ready else "Run step 7 first")
    _header = step_header("## 8. Far from index", run_wide)
    _header
    return (run_wide,)


@app.cell
def _(catalog, get_spike, run_wide, set_wide, summarize_tr_consistency):
    if run_wide.value:
        _spike = get_spike()
        if _spike is None:
            raise ValueError("Wide step requires spike output")
        _observations = _spike["observations"]
        _controls, _issue_summary, _checks = summarize_tr_consistency(
            catalog, _observations, flags=("wide",)
        )
        set_wide(
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
    get_spike,
    get_wide,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
    flag_summary_table,
):
    mo.stop(
        get_spike() is None,
        mo.md("Run step 7 first."),
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

        **Question asked:** on this day, did the fund simply disagree with the
        S&P by a lot? Flag `|fund − S&P| ≥ 5%` whenever both returns exist. On
        daily data this is a rare notable-day screen (Result reports the
        fund-day rate for this run), not a routine tracking-error band.

        After spike and distribution repairs, remaining wide days are treated as
        **active risk** or residual tracking — no automatic rewrite.
        """),
        mo.mermaid(
            _mermaid_init
            + """
flowchart LR
  f["Fund day: +6%"] --> gap["|6% − 0.5%| = 5.5%"]
  s["S&P day: +0.5%"] --> gap
  gap --> wide["≥ 5% → flag wide"]
"""
        ),
    )
    _wide = get_wide()
    if _wide is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to re-score days far from the index._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _controls = _wide["controls"]
        _issue_summary = _wide["issue_summary"]
        _wide_table = flag_summary_table(_issue_summary, "wide")
        _total_fund_days = int(_issue_summary["days"].sum()) if len(_issue_summary) else 0
        _total_wide_days = (
            int(_issue_summary["far_from_index"].sum()) if len(_issue_summary) else 0
        )
        _wide_rate_pct = (
            100.0 * _total_wide_days / _total_fund_days if _total_fund_days else float("nan")
        )
        _wide_rate_text = (
            f"**{_wide_rate_pct:.3f}%** of fund-days "
            f"({_total_wide_days:,} / {_total_fund_days:,})"
            if _total_fund_days
            else "_no fund-days scored_"
        )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{len(_wide_table):,}** series with at least one wide day \n"
                    f"- Index gap threshold {_controls['index_gap']:.0%} \n"
                    f"- Wide-day rate this run: {_wide_rate_text} \n"
                ),
                review_table(_wide_table, "Series far from index"),
            ),
            decision=stack(
                md("""
                Diagnostic only. Sparse wide flags over the panel window are
                interpreted as active risk rather than data errors; no series are
                dropped or rewritten here. The Result rate above is the
                quantitative support for “sparse” on this run.
                """),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_wide, mo, run_step_button, step_header):
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
                _price_cut = None if _price_id is None else _last_change(_cleaned[_price_id])
                _cuts = [_cut for _cut in (_tr_cut, _price_cut) if _cut is not None]
                _never_moves = not _cuts
                _start = _first if _never_moves else max(_cuts) + 1
                if _start > _last:
                    continue
                _tail = _market_return.iloc[_start : _last + 1]
                _moved_sessions = int(_tail.fillna(0).ne(0).sum())
                if not _never_moves and _moved_sessions < min_sessions:
                    continue
                _blanked = 0
                for _header in (f"{_isin} TR", f"{_isin} TR %", f"{_isin} Price", f"{_isin} Price %"):
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
                        "pattern": "never moves" if _never_moves else "frozen tail",
                        "last_real_print": None if _never_moves else source.index[_start - 1].strftime("%Y-%m-%d"),
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

        _cleaned_observations, _frozen_log = _blank_frozen_tails(_repaired_observations, catalog)

        set_frozen(
            {
                "cleaned_observations": _cleaned_observations,
                "frozen_log": _frozen_log,
            }
        )
    return


@app.cell
def _(
    catalog,
    get_wide,
    get_frozen,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    mo.stop(
        get_wide() is None,
        mo.md("Run step 8 first. This step reads the wide-step observations."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _documentation = stack(
        selection_stats(_n_ids, _n_cols),
        md("""
        ### What and why

        After closure or merger, Datastream often repeats the last price and
        total-return level on every later calendar date. Those repeats are not
        economic returns: they insert a mechanical 0% daily return and bias
        volatility and beta downward. Blanking the frozen tail (while keeping
        the last real print) removes that artefact without inventing returns.

        ### How

        1. **Detect.** A total-return series is frozen when its level is flat for
           at least five sessions on which the S&P 500 moved, through the last
           date of the series, and the paired price is flat over the same
           window. If the price still moves (for example a fund shifting to cash
           before liquidation), the path is left unchanged.
        2. **Blank tail.** Keep the last real print; blank every later
           total-return and price level and their daily returns.
        3. **Never moves.** A series that never changes is blanked entirely.
           Total net assets are monthly values repeated daily and are left
           untouched.
        """),
    )
    _frozen = get_frozen()
    if _frozen is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to blank frozen post-closure tails._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _frozen_log = _frozen["frozen_log"]
        _never_moving = _frozen_log.loc[_frozen_log["pattern"].eq("never moves")]
        _frozen_tails = _frozen_log.loc[_frozen_log["pattern"].eq("frozen tail")]
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{len(_frozen_log):,}** frozen series identified \n"
                    f"- **{len(_never_moving):,}** funds never move and are "
                    f"blanked entirely \n"
                    f"- **{len(_frozen_tails):,}** funds have a frozen tail, "
                    f"blanked after their last real print \n"
                    f"- **{int(_frozen_log['cells'].sum()) if len(_frozen_log) else 0:,}** "
                    f"cells blanked across total return, price, and daily returns \n"
                ),
                review_table(_frozen_log, "Frozen series"),
            ),
            decision=stack(
                md("""
                Keep all series columns. Frozen tails are blanked so they do not
                contribute mechanical 0% returns. The cleaned observations frame
                stays in memory.
                """),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_frozen, mo, run_step_button, step_header):
    _ready_tbill = get_frozen() is not None
    run_tbill = run_step_button(ready=_ready_tbill, tooltip=None if _ready_tbill else "Run step 9 first")
    _header = step_header("## 10. Fill US T-Bill 3M (^IRX)", run_tbill)
    _header
    return (run_tbill,)


@app.cell
def _(catalog, get_frozen, pd, run_tbill, set_tbill):
    if run_tbill.value:
        _frozen = get_frozen()
        if _frozen is None:
            raise ValueError("T-Bill step requires frozen output")
        _cleaned_observations = _frozen["cleaned_observations"]

        import yfinance as yf

        _matches = catalog.loc[catalog["header"].eq("US T-Bill 3M"), "column"]
        if len(_matches) != 1:
            raise ValueError("Expected one US T-Bill 3M column")
        _rate_column = int(_matches.iloc[0])
        _start = pd.Timestamp(_cleaned_observations.index.min())
        _end = pd.Timestamp(_cleaned_observations.index.max()) + pd.Timedelta(days=1)
        _history = yf.Ticker("^IRX").history(
            start=_start,
            end=_end,
            interval="1d",
            auto_adjust=False,
            repair=False,
        )
        if _history.empty:
            raise ValueError("Yahoo returned no ^IRX history")
        _history.index = _history.index.tz_localize(None).normalize()
        _close = _history["Close"].astype(float)
        _dates = pd.DatetimeIndex(pd.to_datetime(_cleaned_observations.index)).normalize()
        _aligned = _close.reindex(_dates)
        _rated_observations = _cleaned_observations.copy()
        _rated_observations[_rate_column] = _aligned.to_numpy()
        _filled = int(_aligned.notna().sum())
        _blank = int(_aligned.isna().sum())
        _present = _aligned.dropna()

        set_tbill(
            {
                "rated_observations": _rated_observations,
                "filled": _filled,
                "blank": _blank,
                "first_print": _present.index[0] if len(_present) else None,
                "first_value": float(_present.iloc[0]) if len(_present) else None,
                "last_print": _present.index[-1] if len(_present) else None,
                "last_value": float(_present.iloc[-1]) if len(_present) else None,
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
    selection_stats,
    stack,
    step_sections,
):
    mo.stop(
        get_frozen() is None,
        mo.md("Run step 9 first. This step reads the frozen-tail observations frame."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _documentation = stack(
        selection_stats(_n_ids, _n_cols),
        md("""
        ### What and why

        Risk-adjusted performance in the thesis uses a short-rate proxy. The
        Datastream column `US T-Bill 3M` arrives empty. Yahoo `^IRX` (CBOE
        13-week Treasury bill yield) is already quoted as an annualised percent
        and matches the Sharpe convention of taking the last print in each month.

        ### How

        1. **Fetch.** Download daily `^IRX` history with yfinance over the panel
           date span (`auto_adjust=False`).
        2. **Align.** Normalise Yahoo timestamps to calendar dates and reindex
           to the sheet's date index.
        3. **Fill.** Write the aligned close into the `US T-Bill 3M` column.
           Dates Yahoo skips (including US holidays) remain blank; no
           carry-forward is applied.
        """),
    )
    _tbill = get_tbill()
    if _tbill is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to fill `US T-Bill 3M` from Yahoo `^IRX`._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _filled = _tbill["filled"]
        _blank = _tbill["blank"]
        _first_print = _tbill["first_print"]
        _first_value = _tbill["first_value"]
        _last_print = _tbill["last_print"]
        _last_value = _tbill["last_value"]
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                f"- **{_filled:,}** sessions filled from Yahoo `^IRX` \n"
                f"- **{_blank:,}** sessions left blank \n"
                + (
                    f"- First print {_first_print:%Y-%m-%d}: "
                    f"**{_first_value:.2f}%** \n"
                    if _first_print is not None
                    else ""
                )
                + (
                    f"- Last print {_last_print:%Y-%m-%d}: "
                    f"**{_last_value:.2f}%** \n"
                    if _last_print is not None
                    else ""
                )
            ),
            decision=stack(
                md("""
                Keep all series. The `US T-Bill 3M` column now holds Yahoo `^IRX`
                closes where available. The rated observations frame stays in
                memory; labels for this column are updated only when the workbook
                is exported.
                """),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(get_tbill, mo, run_step_button, step_header):
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
        _scale = get_scale()
        _level_jump = get_level_jump()
        _rebuild = get_rebuild()
        _spike = get_spike()
        _wide = get_wide()
        _frozen = get_frozen()
        if None in (
            _holiday,
            _gap,
            _scale,
            _level_jump,
            _rebuild,
            _spike,
            _wide,
            _frozen,
            _tbill,
        ):
            raise ValueError("Export step requires Steps 2–10 payloads")
        _cleaned_observations = _tbill["rated_observations"]

        def _build_run_summary():
            from helpers.timeseries_functions.rebuild_tr_from_distributions import (
                LIPPER_CLOSE_PP,
                LIPPER_TEST_HORIZONS,
                lipper_test_status,
            )

            holiday_log = _holiday["correction_log"]
            gap_table = flag_summary_table(_gap["issue_summary"], "gaps")
            scale_table = flag_summary_table(_scale["issue_summary"], "scale_shift")
            jump_table = flag_summary_table(_level_jump["issue_summary"], "level_jumps")
            jump_isins = set(jump_table["id"].astype("string").str.strip())
            action_log = _level_jump["action_log"]
            decision_log = action_log.loc[
                action_log["isin"].astype("string").str.strip().isin(jump_isins)
                & ~action_log["decision"].eq("already rescaled")
            ]
            rescaled = decision_log.loc[decision_log["decision"].eq("rescaled")]

            rebuild_log = _rebuild["rebuild_log"].copy()
            adopted_mask = rebuild_log["decision"].eq("adopted") if len(rebuild_log) else None
            n_adopted = int(adopted_mask.sum()) if adopted_mask is not None else 0
            n_kept_ds = int(len(rebuild_log) - n_adopted) if len(rebuild_log) else 0

            def _gaps_from_row(row, *, side: str):
                return {
                    horizon: row.get(f"gap_{horizon}_{side}")
                    for horizon in LIPPER_TEST_HORIZONS
                }

            ds_pass = ds_fail = ds_un = rb_pass = rb_fail = rb_un = 0
            post_pass = post_fail = post_un = 0
            if len(rebuild_log) and "gap_10y_before" in rebuild_log.columns:
                for row in rebuild_log.itertuples(index=False):
                    row_s = pd.Series(row._asdict())
                    ds_s, _ = lipper_test_status(_gaps_from_row(row_s, side="before"))
                    rb_s, _ = lipper_test_status(_gaps_from_row(row_s, side="after"))
                    ds_pass += ds_s == "pass"
                    ds_fail += ds_s == "fail"
                    ds_un += ds_s == "unscored"
                    rb_pass += rb_s == "pass"
                    rb_fail += rb_s == "fail"
                    rb_un += rb_s == "unscored"
                for row in rebuild_log.loc[adopted_mask].itertuples(index=False):
                    row_s = pd.Series(row._asdict())
                    status, _ = lipper_test_status(_gaps_from_row(row_s, side="after"))
                    post_pass += status == "pass"
                    post_fail += status == "fail"
                    post_un += status == "unscored"

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

            if not _cleaned_observations.columns.equals(observations.columns):
                raise ValueError("Corrected columns do not match the loaded sheet")
            if not _cleaned_observations.index.equals(observations.index):
                raise ValueError("Corrected dates do not match the loaded sheet")

            _source = _Path(workbook).resolve()
            # Immutable input: write a sibling cleaned workbook, never replace
            # v2-funds-normalized.xlsx.
            _output = _source.with_name("v2-funds-normalized-cleaned.xlsx")

            # Dump catalog + cleaned panel only (kept series). Skipped input
            # columns are not written. Other workbook sheets stay via the copy.
            _meta = catalog.set_index("column").loc[_cleaned_observations.columns].copy()
            _bill = _meta["header"].eq("US T-Bill 3M")
            _meta.loc[_bill, "name"] = "CBOE 13-week Treasury bill (^IRX)"
            _meta.loc[_bill, "note"] = (
                "Yahoo ^IRX close, annualised rate in %. Blank when Yahoo has no print."
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

            _difference = observations.sub(_cleaned_observations).abs()
            _changed = _difference.gt(1e-12) | (
                observations.isna() ^ _cleaned_observations.isna()
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
                try:
                    os.replace(_temporary_path, _output)
                except OSError:
                    shutil.move(_temporary_path, _output)
            finally:
                if os.path.exists(_temporary_path):
                    os.remove(_temporary_path)
            return _corrected_cells, _removed_raw_sheet, _output

        _corrected_cells, _removed_raw_sheet, _output_path = _save_cleaned_workbook()
        _run_summary = _build_run_summary()

        set_export(
            {
                "corrected_cells": _corrected_cells,
                "removed_raw_sheet": _removed_raw_sheet,
                "workbook": str(_output_path),
                "source_workbook": str(workbook),
                "sheet_name": sheet_name,
                "run_summary": _run_summary,
            }
        )
    return


@app.cell
def _(
    catalog,
    get_tbill,
    get_export,
    md,
    mo,
    selection_stats,
    stack,
    step_sections,
    workbook,
):
    mo.stop(
        get_tbill() is None,
        mo.md("Run step 10 first. This step writes the cleaned in-memory panel."),
    )
    _n_ids = int(catalog["id"].nunique())
    _n_cols = len(catalog)
    _cleaned_name = "v2-funds-normalized-cleaned.xlsx"
    _cleaned_path = workbook.with_name(_cleaned_name)
    _documentation = stack(
        selection_stats(_n_ids, _n_cols),
        md(f"""
        ### What and why

        Earlier repairs lived only in memory. This step is the sole workbook
        write: it dumps the in-memory catalog and cleaned daily panel to a
        **separate** file, `{_cleaned_name}`, beside the immutable input
        `{workbook.name}`. Only kept series are written — columns skipped at
        load (e.g. TNA) are omitted. Other sheets (e.g. `Funds final`) are
        carried over from the input copy. Closed / unusable funds are already
        excluded upstream in the funds notebook. Idempotent re-runs overwrite
        only the cleaned sibling.

        ### How

        1. **Copy input → temp.** Copy `{workbook.name}` to a temporary file in
           the same folder (input path is never opened for write).
        2. **`D-Timeseries final`.** Rebuild the sheet from catalog labels +
           cleaned observations (kept columns only). Update `US T-Bill 3M`
           label rows to document the Yahoo `^IRX` source.
        3. **Cleanup + atomic publish.** Remove `D-Timeseries raw` when present;
           atomically replace `{_cleaned_name}` only. The input workbook stays
           unchanged.
        """),
    )
    _export = get_export()
    if _export is None:
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                f"_Click **Run step** to dump the cleaned panel to "
                f"`{_cleaned_path}` (input `{workbook}` is left unchanged)._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    else:
        _corrected_cells = _export["corrected_cells"]
        _removed_raw_sheet = _export["removed_raw_sheet"]
        _sheet = _export.get("sheet_name", "D-Timeseries final")
        _path = _export.get("workbook", str(_cleaned_path))
        _source = _export.get("source_workbook", str(workbook))
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                f"- Wrote `{_sheet}` in `{_path}` "
                f"(**{_n_cols:,}** kept series; "
                f"**{_corrected_cells:,}** cells different from the loaded panel) \n"
                f"- Input left unchanged: `{_source}` \n"
                + (
                    "- Removed `D-Timeseries raw` from the cleaned copy \n"
                    if _removed_raw_sheet
                    else ""
                )
            ),
            decision=stack(
                md(f"""
                Cleaned workbook exported to `{_cleaned_name}`. `D-Timeseries
                final` is a dump of the in-memory catalog and cleaned panel
                (kept columns only; skipped series omitted). Other sheets such
                as `Funds final` come from the input copy. The input
                `{workbook.name}` was not overwritten.
                """),
                selection_stats(_n_ids, _n_cols, when="end"),
            ),
        )
    _step_view
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        """
        ## Conclusion
        """
    )
    return


@app.cell
def _(get_export, md, mo):
    mo.stop(
        get_export() is None,
        mo.md("_Run step 11 first to export the cleaned workbook and unlock the conclusion._"),
    )
    _export = get_export()
    _s = _export.get("run_summary") or {}
    _wide_rate = _s.get("wide_day_rate")
    _wide_rate_txt = (
        f"{_wide_rate:.3%}"
        if isinstance(_wide_rate, (int, float)) and _wide_rate == _wide_rate
        else "n/a"
    )
    md(f"""
    ### Purpose and contribution

    This notebook turns the funds-notebook timeseries panel into a regression-ready
    daily total-return sample. Starting from `D-Timeseries final`, it diagnoses
    inconsistencies versus the S&P 500 total-return index, blanks exchange
    holidays (level and %), repairs corporate-action level breaks, and
    distribution-day spikes,
    optionally rebuilds total returns from cash distributions under a Lipper
    horizon gate, blanks frozen post-closure tails, and fills the three-month
    T-bill from Yahoo `^IRX`. Closed funds without a usable series are already
    excluded upstream in the funds notebook.

    ### This run (from Steps 2–11 payloads)

    - **Holiday:** **{_s.get("holidays", 0):,}** S&P-flat dates; **{_s.get("holiday_series_corrected", 0):,}**
      level series blanked (level/% → NA; **{_s.get("holiday_cells", 0):,}** cells changed)
    - **Gap / scale:** **{_s.get("series_checked", 0):,}** TR % series checked;
      **{_s.get("gap_series", 0):,}** with gaps; **{_s.get("scale_series", 0):,}** with a
      scale shift (factor {_s.get("scale_factor", "n/a")}, window {_s.get("scale_window", "n/a")})
    - **Level jump:** **{_s.get("level_jump_series", 0):,}** TR % series flagged;
      **{_s.get("level_jump_funds_rescaled", 0):,}** funds rescaled
      (**{_s.get("level_jump_cells", 0):,}** cells)
    - **Rebuild (Lipper {_s.get("lipper_close_pp", 0.5):g} pp):** Datastream
      **{_s.get("datastream_pass", 0):,}** pass / **{_s.get("datastream_fail", 0):,}** fail /
      **{_s.get("datastream_unscored", 0):,}** unscored; rebuild candidate
      **{_s.get("rebuild_pass", 0):,}** / **{_s.get("rebuild_fail", 0):,}** /
      **{_s.get("rebuild_unscored", 0):,}**; **{_s.get("rebuild_adopted", 0):,}** adopted,
      **{_s.get("rebuild_kept_datastream", 0):,}** kept Datastream; post-adopt among
      adopted **{_s.get("post_adopt_pass", 0):,}** pass /
      **{_s.get("post_adopt_fail", 0):,}** fail /
      **{_s.get("post_adopt_unscored", 0):,}** unscored
    - **Spike:** **{_s.get("spike_series", 0):,}** series with Result flags
      (spike {_s.get("spike_return", 0):.0%}, reversal {_s.get("reversal_band", 0):.0%});
      **{_s.get("spike_repaired_days", 0):,}** distribution days rewritten
      (**{_s.get("spike_forward", 0):,}** forward / S&P,
      **{_s.get("spike_one_day", 0):,}** one-day; **{_s.get("spike_cells", 0):,}** cells);
      **{_s.get("spike_kept_days", 0):,}** agreeing price+TR spikes kept
    - **Wide:** **{_s.get("wide_series", 0):,}** series;
      **{_wide_rate_txt}** of fund-days
      (**{_s.get("wide_days", 0):,}** / **{_s.get("fund_days", 0):,}**;
      threshold {_s.get("index_gap", 0):.0%})
    - **Frozen tails:** **{_s.get("frozen_series", 0):,}** series
      (**{_s.get("frozen_never_moves", 0):,}** never-move,
      **{_s.get("frozen_tails", 0):,}** tails; **{_s.get("frozen_cells", 0):,}** cells blanked)
    - **T-Bill:** **{_s.get("tbill_filled", 0):,}** sessions filled from `^IRX`,
      **{_s.get("tbill_blank", 0):,}** left blank
    - **Export:** dumped kept series to the cleaned workbook;
      **{_export.get("corrected_cells", 0):,}** cells different from the loaded
      panel
      {"(removed `D-Timeseries raw`)" if _export.get("removed_raw_sheet") else ""}

    ### Construction protocol

    Repair steps rewrite cells when Decision documents it: **2** exchange-holiday
    NA, **5** level-jump rescales, **6** Lipper-gated TR rebuild,
    **7** curated distribution-day spikes, **9** frozen post-closure tails,
    **10** US T-Bill fill. Diagnostic-only steps score flags and never rewrite:
    **3** gap, **4** scale shift, **8** far from index. Each gated step reads
    only the prior step’s output and does not reopen earlier drops. Step **11**
    is the sole workbook write: it dumps catalog + cleaned observations into
    `D-Timeseries final` (kept columns only; updated T-bill labels;
    `D-Timeseries raw` removed when present) and leaves the input workbook
    unchanged. Counts above are taken only from this run’s gated payloads.

    ### Residual flags and interpretation

    After repair, remaining “far from index” flags are treated as active risk
    rather than data errors when Step 8’s Result shows a sparse fund-day rate
    (this run: **{_wide_rate_txt}**). Spikes where price and total return move
    together are kept as genuine NAV moves. Explained scale episodes (thin early
    NAV marking, pre-liquidation cash) are left as published. Distribution-day TR
    repairs run only when the Step 7 eligibility gate still finds Price/TR
    disagreement and a material market residual on the current panel; forward
    cases without a confirmed cash amount use that day’s S&P 500 TR % as the proxy.

    ### Artefact

    Use the **total-return** column for performance and S&P 500 regressions. The
    price column remains the published NAV and still falls on distribution days.
    The cleaned panel lives in `{_export.get("workbook", "output-data/v2-funds-normalized-cleaned.xlsx")}`
    (input: `{_export.get("source_workbook", "output-data/v2-funds-normalized.xlsx")}`).
    """)
    return


if __name__ == "__main__":
    app.run()
