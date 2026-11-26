# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo>=0.25.2",
#     "pandas>=3.0.6",
#     "openpyxl>=3.1.5",
#     "requests",
#     "python-dotenv",
#     "edgartools>=5.62.0",
#     "lxml",
#     "typesafe-sdk>=0.7.5",
#     "yfinance>=1.7.0",
#     "pymupdf>=2.0",
# ]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Load and analyze funds (V2)")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    # Run buttons reset after their cells finish. These values keep each step's
    # tables on screen, and they give the next step a stable input.
    get_cusip_fill, set_cusip_fill = mo.state(None)
    get_openfigi, set_openfigi = mo.state(None)
    get_edgar, set_edgar = mo.state(None)
    get_nport_check, set_nport_check = mo.state(None)
    get_primary, set_primary = mo.state(None)
    get_style, set_style = mo.state(None)
    get_timeseries, set_timeseries = mo.state(None)
    get_spxtr_screen, set_spxtr_screen = mo.state(None)
    get_final, set_final = mo.state(None)
    get_daily_series, set_daily_series = mo.state(None)
    return (
        get_cusip_fill,
        get_daily_series,
        get_edgar,
        get_final,
        get_openfigi,
        get_nport_check,
        get_primary,
        get_spxtr_screen,
        get_style,
        get_timeseries,
        set_cusip_fill,
        set_daily_series,
        set_edgar,
        set_final,
        set_openfigi,
        set_nport_check,
        set_primary,
        set_spxtr_screen,
        set_style,
        set_timeseries,
    )


@app.cell
def _(mo):
    import textwrap

    def md(text: str):
        """Render markdown after stripping common indentation (avoids code blocks)."""
        return mo.md(textwrap.dedent(text).strip())

    def review_table(frame, columns, label):
        present = [column for column in columns if column in frame.columns]
        view = frame.loc[:, present].copy() if present else frame.copy()
        view = view.reset_index(drop=True)
        return mo.ui.table(
            view,
            label=label,
            selection=None,
            pagination=len(view) > 12,
            page_size=12,
            max_height=420,
        )

    def selection_stats(n_funds: int, *, when: str = "start"):
        if when == "start":
            text = f"**Selection at the start of this step:** {n_funds:,} funds."
        else:
            text = f"**Selection remaining after this step:** {n_funds:,} funds."
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


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Load and analyze funds (V2)

    Goal: produce a clean fund set for the master thesis.

    Step 1 loads the workbook on open. Each later step waits for its **Run step** button. A step's Result and Decision stay empty until that button has been pressed, and the next step's button stays disabled until the previous step has finished. `selected_funds` stays the sheet selection. Enrichment starts from a copy, `selected_funds_modified`. Further steps use additional copies: `funds_openfigi`, `funds_edgar`, `funds_classified`, `funds_with_timeseries`, `funds_final`, and `daily_timeseries_final`.

    **Selection rule:** when a step drops funds, they leave the working selection permanently. Later steps read only the kept frame from the previous step — they never re-open or re-analyse removed ISINs.

    **Excel export:** intermediate steps keep sheets in memory only. The normalized workbook `output-data/v2-funds-normalized.xlsx` is written once at the end (step 8).

    **Each step has three collapsible sections:**

    1. **Documentation** — *What and why* (thesis objective) and *How* (sources, enrichments, algorithms, parameters), plus the selection size at the start of the step.
    2. **Result** — tables and metrics produced by the step (only funds still in the selection).
    3. **Decision** — what is kept or dropped, plus the number of funds remaining in the selection.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    def same_size_label(text: str) -> str:
        width = 24
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if len(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return (
            "<div style='height:4.7em; display:flex; align-items:center; "
            "justify-content:center; text-align:center; line-height:1.35; "
            "white-space:normal'>"
            + "<br/>".join(lines)
            + "</div>"
        )

    steps = [
        "1. Load all funds and keep the selected funds",
        "2. Verify there are no double counts or missing data",
        "3. Match with OpenFIGI and enrich with name and market identifier",
        "4. Match with EDGAR and enrich with CIK and series",
        "5. Keep one primary share class per series and wrapper",
        "6. Check Fund Type",
        "7. Check if TR timeseries available",
        "7b. Restrict Active ETFs to S&P 500 TR",
        "8. Export final Excel",
    ]
    nodes = "\n".join(
        f'    step{index}["{same_size_label(label)}"]'
        for index, label in enumerate(steps, start=1)
    )
    links = " --> ".join(f"step{index}" for index in range(1, len(steps) + 1))
    mo.mermaid(
        "%%{init: "
        '{"flowchart": {"padding": 6, "nodeSpacing": 8, "rankSpacing": 16}}'
        "}%%\n"
        "flowchart LR\n"
        f"{nodes}\n"
        f"    {links}\n",
        theme_variables={"fontSize": "12px"},
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("## 1. Load the data")
    return


@app.cell
def _():
    import io
    import sys
    from contextlib import redirect_stdout
    from pathlib import Path

    import pandas as pd

    class _PrintCapture:
        def __init__(self, echo):
            self.echo = echo
            self.buffer = io.StringIO()

        def write(self, data):
            self.echo.write(data)
            self.echo.flush()
            self.buffer.write(data)
            return len(data)

        def flush(self):
            self.echo.flush()

    def capture_prints():
        capture = _PrintCapture(sys.stdout)
        return capture.buffer, redirect_stdout(capture)

    def _ensure_helpers_importable() -> None:
        start = Path.cwd().resolve()
        for directory in [start, *start.parents]:
            if (directory / "helpers").is_dir():
                root = str(directory)
                if root not in sys.path:
                    sys.path.insert(0, root)
                return
        raise FileNotFoundError(f"Could not find helpers/, starting from {start}")

    _ensure_helpers_importable()

    from helpers.funds_functions.load_workbook import (
        add_prefixed_columns,
        find_workbook,
        load_workbook,
        normalize_columns,
    )
    from helpers.funds_functions.write_excel import write_excel_sheets

    NORMALIZED_XLSX = "v2-funds-normalized.xlsx"
    NORMALIZED_XLSX_LABEL = f"output-data/{NORMALIZED_XLSX}"

    def write_sheets(sheets: dict, filename: str, *, no_header: tuple = ()) -> Path:
        start = Path.cwd().resolve()
        for directory in [start, *start.parents]:
            if (directory / "helpers").is_dir():
                return write_excel_sheets(
                    sheets,
                    directory / "output-data" / filename,
                    no_header=no_header,
                )
        raise FileNotFoundError(f"Could not find helpers/, starting from {start}")

    FILENAME = "CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx"
    workbook = find_workbook(Path("input-data") / FILENAME)
    funds = load_workbook(workbook)
    # Normalized copy for the eventual export. `funds` keeps the original names
    # that later steps read. The workbook is written once at step 8.
    funds_normalized = normalize_columns(funds, prefix="ds.")
    selected_funds = funds.loc[
        funds["fund_type"].notna()
        & funds["fund_type"].astype("string").str.strip().ne("")
    ].copy()
    return (
        NORMALIZED_XLSX,
        NORMALIZED_XLSX_LABEL,
        add_prefixed_columns,
        capture_prints,
        funds,
        funds_normalized,
        pd,
        selected_funds,
        workbook,
        write_sheets,
    )


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    funds,
    mo,
    review_table,
    selected_funds,
    selection_stats,
    stack,
    step_sections,
    workbook,
):
    fund_type_counts = (
        selected_funds["fund_type"]
        .value_counts()
        .rename_axis("fund_type")
        .reset_index(name="funds")
    )
    step_sections(
        documentation=stack(
            selection_stats(len(funds)),
            mo.md(f"""
            ### What and why

            This thesis studies mutual-fund and ETF total returns classified by
            management style and wrapper. The first task is to open the Lipper /
            Datastream extract and define a transparent working sample. Without a
            clear cross-section, later identifier, EDGAR, and timeseries steps
            have no well-defined universe.

            ### How

            1. **Source.** Read the **Funds** sheet of
               `input-data/CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx` (full Lipper /
               Datastream extract).
            2. **Normalization.** Rename columns to lowercase snake_case and
               prefix them with `ds.` so sheet fields stay distinguishable from
               later enrichments. The normalized `Funds` sheet is kept in memory
               and written to `{NORMALIZED_XLSX_LABEL}` only at the end of the
               notebook (step 8).
            3. **Working selection.** Keep rows whose asset-class `fund_type` is
               non-empty (Equity, Alternatives, …). That field is *not* the
               Active/Passive label; style classification comes later. The
               resulting frame is `selected_funds`.
            """),
        ),
        result=stack(
            mo.md(
                f"- Loaded `{workbook}` \n"
                f"- **Total number of funds:** {len(funds):,} rows, {len(funds.columns)} columns \n"
                f"- Normalized columns (prefix `ds.`) prepared in memory for `{NORMALIZED_XLSX_LABEL}` (written at step 8)"
            ),
        ),
        decision=stack(
            mo.md("""
            Keep rows with a non-empty `fund_type` as the working selection
            (`selected_funds`). Rows without `fund_type` are out of scope for all
            later steps. Enrichment proceeds on copies of this selection only.
            """),
            selection_stats(len(selected_funds), when="end"),
            review_table(
                fund_type_counts,
                ["fund_type", "funds"],
                "selected_funds by fund_type",
            ),
        ),
    )
    return


@app.cell(hide_code=True)
def _(mo, run_step_button, step_header):
    run_step_2 = run_step_button()
    step_header("## 2. Verify if ISIN and CUSIP are unique", run_step_2)
    return (run_step_2,)


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    capture_prints,
    funds_normalized,
    run_step_2,
    selected_funds,
    set_cusip_fill,
):
    if run_step_2.value:
        from helpers.funds_functions.check_openfigi_isin import (
            record_from_job,
            same_openfigi_record,
        )
        from helpers.funds_functions.map_market_identifiers import (
            cusip_shape_ok,
            post_mapping,
        )

        def _blank_identifier(series):
            values = series.astype("string").str.strip()
            return values.isna() | values.eq("") | values.str.lower().eq("<na>")

        def _cusip_from_us_isin(isin):
            if not isinstance(isin, str) or len(isin) != 12 or not isin.startswith("US"):
                return None
            cusip = isin[2:11]
            return cusip if cusip_shape_ok(cusip) else None

        _funds = selected_funds.copy()
        _log_buffer, _redirect = capture_prints()
        with _redirect:
            isin_text = _funds["ISIN"].astype("string").str.strip().str.upper()
            candidate = isin_text.map(_cusip_from_us_isin)
            blank_cusip = _blank_identifier(_funds["CUSIP"])
            targets = _funds.loc[blank_cusip & candidate.notna(), ["Name", "ISIN"]].copy()
            targets["CUSIP"] = candidate.loc[targets.index]
            if targets.empty:
                message = "No missing CUSIP can be read from a US ISIN"
            else:
                isins = list(dict.fromkeys(targets["ISIN"].astype(str)))
                cusips = list(dict.fromkeys(targets["CUSIP"].astype(str)))
                isin_records = {
                    isin: record_from_job(job)
                    for isin, job in zip(isins, post_mapping(isins, "ID_ISIN"))
                }
                cusip_records = {
                    cusip: record_from_job(job)
                    for cusip, job in zip(cusips, post_mapping(cusips, "ID_CUSIP"))
                }
                confirmed = [
                    same_openfigi_record(isin_records.get(isin), cusip_records.get(cusip))
                    for isin, cusip in zip(
                        targets["ISIN"].astype(str), targets["CUSIP"].astype(str)
                    )
                ]
                targets["openfigi_ticker"] = [
                    (cusip_records.get(cusip) or {}).get("ticker") if ok else None
                    for cusip, ok in zip(targets["CUSIP"].astype(str), confirmed)
                ]
                targets["openfigi_name"] = [
                    (cusip_records.get(cusip) or {}).get("name") if ok else None
                    for cusip, ok in zip(targets["CUSIP"].astype(str), confirmed)
                ]
                targets["filled"] = confirmed
                accepted = targets.index[targets["filled"]]
                _funds.loc[accepted, "CUSIP"] = targets.loc[accepted, "CUSIP"].astype(
                    "string"
                )
                message = f"Filled {len(accepted)} of {len(targets)} missing CUSIPs"
            # Same index as `funds`, so the enriched CUSIPs land on the right rows.
            _normalized = funds_normalized.copy()
            _normalized["ds.cusip"] = _normalized["ds.cusip"].astype("string")
            _filled = _funds["CUSIP"].astype("string")
            _current = _normalized["ds.cusip"].reindex(_filled.index)
            _changed = (_filled.notna() & (_current.isna() | _filled.ne(_current))).fillna(
                False
            ).astype(bool)
            _normalized.loc[_changed.index[_changed], "ds.cusip"] = _filled.loc[_changed]
        set_cusip_fill(
            {
                "funds": _funds,
                "targets": targets,
                "message": message,
                "normalized": _normalized,
                "normalized_export": NORMALIZED_XLSX_LABEL,
                "log": _log_buffer.getvalue(),
            }
        )
    return


@app.cell
def _(
    get_cusip_fill,
    mo,
    review_table,
    selected_funds,
    selection_stats,
    stack,
    step_sections,
):
    def _filled_identifier(series):
        values = series.astype("string").str.strip()
        blank = values.isna() | values.eq("") | values.str.lower().eq("<na>")
        return values.mask(blank)

    def _identifier_label(isin_flag, cusip_flag):
        parts = []
        if isin_flag:
            parts.append("ISIN")
        if cusip_flag:
            parts.append("CUSIP")
        return " & ".join(parts)

    _n_start = len(selected_funds)
    _documentation = stack(
        selection_stats(_n_start),
        mo.md("""
        ### What and why

        Cross-sectional joins later in the thesis rely on ISIN and CUSIP as
        stable keys. Duplicate or missing identifiers would create double counts
        or silent join failures when matching OpenFIGI, EDGAR, and Datastream
        series. This step audits those keys and, where possible, fills missing
        US CUSIPs before those joins.

        ### How

        1. **Uniqueness and coverage checks.** On `selected_funds`, treat blank /
           `<NA>` strings as missing. Report, for ISIN and for CUSIP: number of
           non-empty values, unique values, duplicates, and missing counts. List
           funds that share an identifier or lack one.
        2. **Enrichment — missing CUSIP from US ISIN (source: OpenFIGI).**
           A US ISIN is `US` + 9-character CUSIP + check digit. For each selected
           fund with an empty CUSIP and a 12-character US ISIN whose middle nine
           characters pass CUSIP shape checks:
           - Query OpenFIGI with `ID_ISIN` on the ISIN and `ID_CUSIP` on the
             derived CUSIP.
           - Fill `CUSIP` only when both jobs return the **same** listing
             (same OpenFIGI record). Otherwise leave blank.
        3. **Working copy.** Copy `selected_funds` → `selected_funds_modified`
           and update `ds.cusip` on the in-memory normalized `Funds` frame (Excel
           write deferred to step 8). The original `selected_funds` is never
           mutated; later steps read the modified copy.
        """),
    )
    cusip_fill = get_cusip_fill()
    if cusip_fill is None:
        selected_funds_modified = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to check identifier uniqueness and fill missing CUSIPs._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        selected_funds_modified = cusip_fill["funds"]
        isin = _filled_identifier(selected_funds["ISIN"])
        cusip = _filled_identifier(selected_funds["CUSIP"])
        lines = []
        for column, values in (("ISIN", isin), ("CUSIP", cusip)):
            filled = values.dropna()
            repeated = filled[filled.duplicated(keep=False)]
            status = (
                "unique"
                if repeated.empty
                else f"{repeated.nunique()} repeated values"
            )
            lines.append(
                f"- **{column}:** {filled.nunique()} unique values among {len(filled)} "
                f"non-empty ({values.isna().sum()} missing) — {status} \n"
            )

        isin_shared = isin.notna() & isin.duplicated(keep=False)
        cusip_shared = cusip.notna() & cusip.duplicated(keep=False)
        shared_funds = selected_funds.loc[
            isin_shared | cusip_shared, ["Name", "ISIN", "CUSIP", "fund_type"]
        ].copy()
        uniqueness_blocks = [mo.md("\n\n".join(lines))]
        if shared_funds.empty:
            uniqueness_blocks.append(mo.md("- No funds share an ISIN or a CUSIP. \n"))
        else:
            shared_funds.insert(
                0,
                "shared_identifier",
                [
                    _identifier_label(isin_flag, cusip_flag)
                    for isin_flag, cusip_flag in zip(
                        isin_shared.loc[shared_funds.index],
                        cusip_shared.loc[shared_funds.index],
                    )
                ],
            )
            shared_funds = (
                shared_funds.assign(_sort=isin.where(isin_shared, cusip))
                .sort_values(["_sort", "Name"])
                .drop(columns="_sort")
            )
            shared_count = len(shared_funds)
            shared_verb = "fund shares" if shared_count == 1 else "funds share"
            uniqueness_blocks.append(
                mo.md(f"- **{shared_count} {shared_verb} an ISIN or a CUSIP** \n")
            )
            uniqueness_blocks.append(
                review_table(
                    shared_funds,
                    ["shared_identifier", "Name", "ISIN", "CUSIP", "fund_type"],
                    "Shared ISIN or CUSIP",
                )
            )

        missing_isin = isin.isna()
        missing_cusip = cusip.isna()
        missing_funds = selected_funds.loc[
            missing_isin | missing_cusip, ["Name", "ISIN", "CUSIP", "fund_type"]
        ].copy()
        if missing_funds.empty:
            uniqueness_blocks.append(
                mo.md("- No funds are missing an ISIN or a CUSIP. \n")
            )
        else:
            missing_funds.insert(
                0,
                "missing_identifier",
                [
                    _identifier_label(isin_flag, cusip_flag)
                    for isin_flag, cusip_flag in zip(
                        missing_isin.loc[missing_funds.index],
                        missing_cusip.loc[missing_funds.index],
                    )
                ],
            )
            missing_funds = missing_funds.sort_values(["missing_identifier", "Name"])
            missing_count = len(missing_funds)
            missing_verb = "fund is" if missing_count == 1 else "funds are"
            uniqueness_blocks.append(
                mo.md(
                    f"- **{missing_count} {missing_verb} missing an ISIN or a CUSIP** \n"
                )
            )
            uniqueness_blocks.append(
                review_table(
                    missing_funds,
                    ["missing_identifier", "Name", "ISIN", "CUSIP", "fund_type"],
                    "Missing ISIN or CUSIP",
                )
            )

        cusip_blocks = [
            mo.md(
                f"**{cusip_fill['message']}** \n\n"
                f"Updated `ds.cusip` on the in-memory `Funds` sheet "
                f"(written to `{cusip_fill['normalized_export']}` at step 8)"
            )
        ]
        if cusip_fill["log"].strip():
            cusip_blocks.append(mo.plain_text(cusip_fill["log"].strip()))
        if not cusip_fill["targets"].empty:
            cusip_blocks.append(
                review_table(
                    cusip_fill["targets"],
                    [
                        "Name",
                        "ISIN",
                        "CUSIP",
                        "openfigi_ticker",
                        "openfigi_name",
                        "filled",
                    ],
                    "CUSIP candidates",
                )
            )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md("### Identifier uniqueness"),
                *uniqueness_blocks,
                mo.md("### CUSIP fill from OpenFIGI"),
                *cusip_blocks,
            ),
            decision=stack(
                mo.md(
                    f"""
                    **Decision:** correct the dataset and add the missing CUSIPs.

                    - {cusip_fill["message"]}.
                    - Confirmed CUSIPs are written into `selected_funds_modified` and into
                      in-memory `ds.cusip` (exported to `{cusip_fill["normalized_export"]}`
                      at step 8).
                    - No funds are removed. Later steps read `selected_funds_modified`
                      (same row set as `selected_funds`).
                    """
                ),
                selection_stats(len(selected_funds_modified), when="end"),
            ),
        )
    _step_view
    return (selected_funds_modified,)


@app.cell(hide_code=True)
def _(get_cusip_fill, mo, run_step_button, step_header):
    cusips_ready = get_cusip_fill() is not None
    run_step_3 = run_step_button(
        ready=cusips_ready,
        tooltip=None if cusips_ready else "Run step 2 first",
    )
    step_header(
        "## 3. Verify selected funds and enrich dataset with OpenFIGI",
        run_step_3,
    )
    return (run_step_3,)


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    add_prefixed_columns,
    capture_prints,
    get_cusip_fill,
    pd,
    run_step_3,
    set_openfigi,
):
    if run_step_3.value:
        openfigi_input = get_cusip_fill()
        if openfigi_input is not None:
            from helpers.funds_functions.check_openfigi_isin import check_openfigi_isins
            from helpers.funds_functions.openfigi_unmatched_decisions import (
                DROP_ISINS as _drop_isins,
                KEEP_ISIN as _keep_isin_apply,
                apply_openfigi_unmatched_decisions,
            )

            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _funds = check_openfigi_isins(openfigi_input["funds"])
                _kept_funds, _decision_log = apply_openfigi_unmatched_decisions(_funds)
            _remaining_unmatched = _kept_funds.loc[~_kept_funds["isin_found"]].copy()
            # Rows share the index of `funds_normalized`, so the new columns line up.
            normalized_openfigi = add_prefixed_columns(
                openfigi_input["normalized"],
                _funds,
                "openfigi.",
                source_columns=openfigi_input["funds"].columns,
                source_prefix="openfigi_",
            )
            normalized_openfigi["openfigi.identity_quality"] = (
                _kept_funds["openfigi_identity_quality"].reindex(
                    normalized_openfigi.index
                )
            )
            _unmatched_decision = pd.Series(
                pd.NA, index=normalized_openfigi.index, dtype="object"
            )
            _isin_all = (
                _funds["ISIN"].astype("string").str.strip().str.upper()
            )
            _unmatched_decision.loc[_isin_all.index[_isin_all.isin(_drop_isins)]] = (
                "Drop"
            )
            _unmatched_decision.loc[
                _isin_all.index[_isin_all.eq(_keep_isin_apply)]
            ] = "Keep (caveat)"
            normalized_openfigi["openfigi.unmatched_decision"] = _unmatched_decision
            openfigi_sheets = {
                "Funds": normalized_openfigi,
                "No matching OPENFIGI": normalized_openfigi.loc[
                    _remaining_unmatched.index
                ],
            }
            set_openfigi(
                {
                    "funds": _kept_funds,
                    "unmatched": _remaining_unmatched,
                    "normalized": normalized_openfigi,
                    "sheets": openfigi_sheets,
                    "export": NORMALIZED_XLSX_LABEL,
                    "log": _log_buffer.getvalue(),
                    "unmatched_resolved": True,
                    "dropped_unmatched": int(_isin_all.isin(_drop_isins).sum()),
                    "decision_log": _decision_log,
                }
            )
    return


@app.cell
def _(
    get_cusip_fill,
    get_openfigi,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    cusip_state = get_cusip_fill()
    mo.stop(
        cusip_state is None,
        mo.md("Run step 2 first. This step reads `selected_funds_modified`."),
    )
    _n_start = len(cusip_state["funds"])
    openfigi_result = get_openfigi()
    _documentation = stack(
        selection_stats(_n_start),
        mo.md("""
        ### What and why

        Lipper names alone are not enough to link a fund to market and regulatory
        identifiers. OpenFIGI supplies a vendor-neutral market ticker and a
        canonical short name. Those fields are required to join the SEC fund
        reference (EDGAR) by ticker and to audit that the sheet row is the same
        listing as the CUSIP. Funds with no FIGI match need an explicit keep/drop
        rule so dead identifiers do not pollute the thesis sample.

        ### How

        1. **Source — OpenFIGI Mapping API.**
           - Product site: [https://www.openfigi.com/](https://www.openfigi.com/)
           - API documentation: [https://www.openfigi.com/api](https://www.openfigi.com/api)
             (official examples: [OpenFIGI/api-examples](https://github.com/OpenFIGI/api-examples)).
           - Access in this thesis: HTTP `POST` to
             `https://api.openfigi.com/v3/mapping` via the Python `requests`
             library (no dedicated OpenFIGI SDK); unauthenticated rate limit of
             10 jobs per request and 25 requests per minute, with retry on HTTP 429.
           - `ID_ISIN` for every selected ISIN (cached in
             `cache/cache-isin-openfigi-record.json`).
           - `ID_CUSIP` for every non-empty file CUSIP (cached in
             `cache/cache-cusip-openfigi.json`).
        2. **Fields added** (exported as `openfigi.*` on sheet `Funds`):
           - `openfigi_market_id`, `openfigi_name` — ticker and name from the
             ISIN record (overwrites a conflicting prior value and logs an alert).
           - `isin_found` — true if OpenFIGI returns a record.
           - `name_matches` — sheet name vs OpenFIGI name; short forms such as
             `LRG`, `INST`, `AMER FND` count as the same token; a different
             economic word (e.g. Core vs Growth) does **not**.
           - `cusip_matches` — true only if the CUSIP lookup returns the **same**
             FIGI listing as the ISIN; missing CUSIP, miss, or different listing
             → false.
        3. **Unmatched review algorithm.** Rows with `isin_found=False` are listed
           on sheet `No matching OPENFIGI`. Documented rule: **drop** six closed /
           merged ISINs from the working selection; **keep** John Hancock US
           Sector Rotation Fund;NAV with `openfigi_identity_quality` = no OpenFIGI
           match; EDGAR-only identity. Dropped ISINs leave permanently — later
           steps read only `funds_openfigi` and never reopen them.
        """),
    )
    if openfigi_result is None:
        funds_openfigi = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to match OpenFIGI and apply unmatched decisions._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        funds_openfigi = openfigi_result["funds"]
        openfigi_found = int(funds_openfigi["isin_found"].sum())
        openfigi_name_matches = int(funds_openfigi["name_matches"].sum())
        openfigi_cusip_matches = int(funds_openfigi["cusip_matches"].sum())
        from helpers.funds_functions.openfigi_unmatched_decisions import (
            KEEP_ISIN as _keep_isin,
            unmatched_review_frame,
        )

        unmatched_analysis = unmatched_review_frame()
        _n_still_unmatched = len(openfigi_result["unmatched"])
        _n_dropped = int(openfigi_result.get("dropped_unmatched") or 0)
        _n_reviewed = _n_dropped + _n_still_unmatched

        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                md(
                    f"""
                    ### OpenFIGI match summary

                    - Entered with **{_n_start:,}** funds; after this step **{len(funds_openfigi):,}** remain
                    - Among the **remaining** selection:
                      - **{openfigi_found}** of {len(funds_openfigi)} ISINs found in OpenFIGI
                      - **{openfigi_name_matches}** of {len(funds_openfigi)} names match the OpenFIGI record
                      - **{openfigi_cusip_matches}** of {len(funds_openfigi)} CUSIPs return the same OpenFIGI record as the ISIN
                      - **{_n_still_unmatched}** still has no OpenFIGI match (kept with caveat)
                    - **{_n_reviewed}** unmatched ISINs were reviewed before the drop
                      ({_n_dropped} drop + {_n_still_unmatched} keep)
                    - Prepared sheet `No matching OPENFIGI` and `openfigi.*` columns
                      on `Funds` in memory (written to `{openfigi_result['export']}` at step 8)
                    """
                ),
                md(
                    f"""
                    ### {_n_reviewed} unmatched funds (review before drop)

                    OpenFIGI returned no record for these ISINs. The table records
                    the keep/drop decision applied in this step. Dropped rows leave
                    the selection and are not inputs to later steps.
                    """
                ),
                review_table(
                    unmatched_analysis,
                    [
                        "Name",
                        "ISIN",
                        "Status in pipeline",
                        "Why it fails downstream",
                        "Decision",
                    ],
                    f"{_n_reviewed} funds with no OpenFIGI match",
                ),
                md(
                    f"""
                    ### Impact of no OpenFIGI match (on the kept caveat fund)

                    For John Hancock (`{_keep_isin}`), which stays in `funds_openfigi`:

                    - **No market identifier** (`openfigi.market_id`) — weaker
                      cross-vendor identity; harder to re-query OpenFIGI / exchange /
                      composite ids later.
                    - **FIGI is not required for EDGAR** — EDGAR can still resolve via
                      ISIN/name (applied in the next step).
                    - The {_n_dropped} closed/merged unmatched funds are **removed here**
                      and are out of scope for EDGAR, primary-class, classification,
                      and timeseries steps.
                    """
                ),
            ),
            decision=stack(
                md(
                    f"""
                    ### Decision: drop {_n_dropped}, keep {_n_still_unmatched}

                    - **Drop {_n_dropped}** closed/merged funds (Johnson Disciplined
                      Large-Cap; Fifth Third Equity Index A; Fidelity Advisor Series
                      Growth & Income; Aberdeen US Equity II A; Fifth Third Structured
                      Large Cap Plus A; Fifth Third Dividend Growth A).
                      They leave the working selection permanently.
                    - **Keep {_n_still_unmatched}** — John Hancock US Sector Rotation
                      Fund;NAV (`{_keep_isin}`) — with identity-quality caveat
                      `openfigi_identity_quality` = no OpenFIGI match; EDGAR-only
                      identity.

                    ### Outcome

                    - Working set after this step: `funds_openfigi` ({len(funds_openfigi):,} funds).
                    - Later steps (EDGAR onward) read only this kept frame.
                    """
                ),
                selection_stats(len(funds_openfigi), when="end"),
            ),
        )
    _step_view
    return (funds_openfigi,)


@app.cell(hide_code=True)
def _(get_openfigi, mo, run_step_button, step_header):
    openfigi_ready = get_openfigi() is not None
    run_step_4 = run_step_button(
        ready=openfigi_ready,
        tooltip=None if openfigi_ready else "Run step 3 first",
    )
    step_header("## 4. Verify and enrich ISINs with EDGAR", run_step_4)
    return (run_step_4,)


@app.cell
def _(NORMALIZED_XLSX_LABEL, add_prefixed_columns):
    def build_edgar_workbook(openfigi_state, funds_edgar):
        """Add the edgar.* columns to Funds in memory (Excel written at step 8)."""
        normalized = add_prefixed_columns(
            openfigi_state["normalized"],
            funds_edgar,
            "edgar.",
            source_columns=openfigi_state["funds"].columns,
            source_prefix=("edgartools_", "edgar_"),
        )
        not_found = ~funds_edgar["edgar_isin_found"].fillna(False).astype(bool)
        sheets = {
            **openfigi_state["sheets"],
            "Funds": normalized,
            "No matching EDGAR": normalized.loc[funds_edgar.index[not_found]],
        }
        return normalized, sheets, NORMALIZED_XLSX_LABEL

    return (build_edgar_workbook,)


@app.cell
def _(
    build_edgar_workbook,
    capture_prints,
    get_openfigi,
    run_step_4,
    set_edgar,
):
    if run_step_4.value:
        edgar_input = get_openfigi()
        if edgar_input is not None:
            from helpers.funds_functions.edgar_unmatched_corrections import (
                apply_edgar_unmatched_corrections,
            )
            from helpers.funds_functions.map_edgar_tickers import (
                load_all_fund_reference_data,
            )
            from helpers.funds_functions.match_edgar_identifiers import (
                match_edgar_identifiers,
            )

            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _funds = match_edgar_identifiers(edgar_input["funds"])
                enriched_edgar = apply_edgar_unmatched_corrections(
                    _funds,
                    load_all_fund_reference_data(),
                )
            still_unmatched = ~enriched_edgar["edgar_isin_found"].astype(bool)
            remaining_unmatched = enriched_edgar.loc[still_unmatched].copy()
            edgar_normalized, edgar_sheets, edgar_export = build_edgar_workbook(
                edgar_input, enriched_edgar
            )
            set_edgar(
                {
                    "funds": enriched_edgar,
                    "unmatched": remaining_unmatched,
                    "base": edgar_input,
                    "normalized": edgar_normalized,
                    "sheets": edgar_sheets,
                    "export": edgar_export,
                    "log": _log_buffer.getvalue(),
                    "corrections_applied": True,
                }
            )
    return


@app.cell
def _(
    get_edgar,
    get_openfigi,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    openfigi_state = get_openfigi()
    mo.stop(
        openfigi_state is None,
        mo.md("Run step 3 first. This step reads `funds_openfigi`."),
    )
    _n_start = len(openfigi_state["funds"])
    _documentation = stack(
        selection_stats(_n_start),
        mo.md("""
        ### What and why

        Regulatory data for US funds lives on the SEC’s **EDGAR** system
        (Electronic Data Gathering, Analysis, and Retrieval). Filings are
        organised hierarchically: a **registrant** (CIK — the investment
        company), one or more **series** (each series is one portfolio / fund),
        and one or more **share classes** inside a series (fee/distribution
        variants of the same portfolio). Linking each Lipper row to those
        identifiers is required to (i) detect multiple selected classes of the
        same portfolio, (ii) classify Active/Passive from census or prospectus
        text, and (iii) keep a survivorship-aware history when a series has left
        the current SEC file.

        **EDGAR sources used in this thesis (and where they matter):**

        - **SEC fund reference (series / class table).** The bulk open-end
          investment-company directory keyed by ticker (and by series/class id).
          It is the join target in *this* step: CIK, series id, class id, and
          series/class names. It is not a periodic filing; it is the reference
          map that later filings hang off.
        - **Form N-CEN** (annual census of registered investment companies).
          Reports operational facts by series — fund type, whether the series is
          an index fund (`indexFundInfo`), ETF flags, advisers, etc. Used later
          to assign Active / Passive / Other when the series is on the latest
          census.
        - **Form N-PORT** (monthly portfolio report for each series). Lists
          holdings (`invstOrSec`) and monthly total-return lines by class. Used
          later to confirm that several selected classes really share one series
          on the registrant’s filing.
        - **Prospectus filings (Forms 485BPOS / 485APOS, and 497K summaries).**
          Narrative investment objective and principal strategy. Used later,
          via Jev, when N-CEN does not decide Active vs Passive.

        This step only attaches the **fund-reference** identifiers. N-CEN,
        N-PORT, and prospectus text are consumed in later steps once CIK /
        series / class are known.

        ### How

        1. **Source — SEC fund reference via [edgartools](https://github.com/dgunning/edgartools)**
           ([docs](https://edgartools.readthedocs.io/), PyPI package `edgartools`).
           - Load the SEC investment-company series/class table with
             `get_fund_reference_data()` (cached in
             `cache/cache-edgar-fund-data.json`). Identity for SEC requests comes
             from `SEC_USER_AGENT` in `.env`.
           - **Join key = market ticker.** For each selected ISIN, take the
             OpenFIGI ticker from the ISIN cache
             (`cache/cache-isin-openfigi-record.json`) and look it up in the
             fund-reference table (one SEC row per non-blank ticker). The CUSIP
             resolves to the same OpenFIGI ticker, so it is **not** looked up
             separately. ISIN and CUSIP are never joined directly to EDGAR.
        2. **Fields added** (prefix `edgar.` / `edgartools_*` on sheet `Funds`):
           - `edgar_isin_found` — OpenFIGI ticker hits an EDGAR row.
           - `edgar_name`, `edgar_name_match` — series + class name; same name
             logic as OpenFIGI (short forms OK; different economic word ≠ match).
           - `edgartools_cik`, `edgar_company_name` — registrant.
           - `edgartools_series_id`, `edgar_series_name` — series inside the CIK.
           - `edgartools_class_id`, `edgar_class_name` — share class inside the
             series.
           - `edgar_match_status`, `edgar_match_note` — how the row was resolved
             (`ticker`, `name`, `closed`, or `unmatchable`).
        3. **Correction algorithm for ticker misses (keep all rows still in the
           selection).** After the ticker join, every remaining miss among
           *current* funds is classified by a hand-reviewed ISIN catalog
           (`helpers/funds_functions/edgar_unmatched_corrections.py`). This step
           does not drop rows. Funds already removed in step 3 (OpenFIGI) are
           not in `funds_openfigi` and are not reconsidered here. For each
           selected fund, in order:
           1. If its ISIN is in **NAME_CORRECTIONS** — look up the catalogued
              `(edgartools_class_id, edgartools_series_id)` in the fund-reference
              table; require exactly one matching SEC row; copy CIK / series /
              class / names; set `edgar_isin_found=True`,
              `edgar_match_status=name`, and store the resolution note. Used when
              the series is live but the SEC ticker cell is blank or wrong
              (examples: Invesco Main Street All Cap Y vs OpenFIGI’s class-A
              name; HAWG ticker assigned to a different series).
           2. Else if its ISIN is in **CLOSED_CORRECTIONS** — clear EDGAR
              identifiers; set `edgar_match_status=closed`. In the current
              pipeline those closed/merged ISINs were already dropped in step 3,
              so this branch is only defensive if one were still present.
           3. Else if its ISIN is in **UNMATCHABLE_CORRECTIONS** — clear
              identifiers; set `edgar_match_status=unmatchable` (e.g. UITs such
              as SPY / Voya Corporate Leaders Trust Series B, or a class id
              present on the ticker list but absent from the series-and-class
              file). No N-CEN series path.
           4. Else if the ticker join already succeeded — set
              `edgar_match_status=ticker` and leave identifiers unchanged.
           Non-matches are also prepared as sheet `No matching EDGAR` in memory.
           Output frame: `funds_edgar`.
        """),
    )
    edgar_result = get_edgar()
    if edgar_result is None:
        funds_edgar = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to match EDGAR and apply corrections._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        funds_edgar = edgar_result["funds"]
        from helpers.funds_functions.edgar_unmatched_corrections import (
            STATUS_CLOSED,
            STATUS_NAME,
            STATUS_TICKER,
            STATUS_UNMATCHABLE,
        )

        match_status = funds_edgar["edgar_match_status"].astype("string")
        ticker_funds = funds_edgar.loc[match_status.eq(STATUS_TICKER)].copy()
        name_funds = funds_edgar.loc[match_status.eq(STATUS_NAME)].copy()
        closed_funds = funds_edgar.loc[match_status.eq(STATUS_CLOSED)].copy()
        unmatchable_funds = funds_edgar.loc[match_status.eq(STATUS_UNMATCHABLE)].copy()
        no_status = funds_edgar.loc[
            match_status.isna() | match_status.eq("<NA>") | match_status.eq("")
        ].copy()
        n_ticker = len(ticker_funds)
        n_name = len(name_funds)
        n_closed = len(closed_funds)
        n_unmatchable = len(unmatchable_funds)
        n_with_edgar = int(funds_edgar["edgar_isin_found"].fillna(False).astype(bool).sum())
        n_name_ok = int(
            funds_edgar.loc[
                funds_edgar["edgar_isin_found"].fillna(False).astype(bool),
                "edgar_name_match",
            ]
            .fillna(False)
            .astype(bool)
            .sum()
        )
        ticker_columns = [
            "Name",
            "ISIN",
            "openfigi_market_id",
            "edgar_name",
            "edgar_name_match",
            "edgartools_cik",
            "edgartools_series_id",
            "edgartools_class_id",
        ]
        name_columns = [
            "Name",
            "ISIN",
            "openfigi_market_id",
            "edgar_name",
            "edgartools_series_id",
            "edgartools_class_id",
            "edgar_match_note",
        ]
        miss_columns = [
            "Name",
            "ISIN",
            "openfigi_market_id",
            "edgar_isin_found",
            "edgar_match_status",
            "edgar_match_note",
        ]

        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                md(
                    f"""
                    ### EDGAR matching outcome

                    Of **{len(funds_edgar):,}** funds still in the selection after
                    step 3 (funds dropped earlier are not reconsidered):

                    - **{n_ticker:,}** matched by **ticker** (`edgar_match_status=ticker`)
                    - **{n_name:,}** matched by **name** correction (`edgar_match_status=name`)
                    - **{n_unmatchable:,}** did **not** match — **unmatchable** (no
                      series/class row; identifiers empty)
                    - **{n_with_edgar:,}** have EDGAR identifiers (`edgar_isin_found=True`);
                      **{n_name_ok:,}** of those have a sheet name that matches the EDGAR name
                    - Prepared sheet `No matching EDGAR`
                      ({len(edgar_result['unmatched'])} rows) in memory
                      (written to `{edgar_result['export']}` at step 8)
                    """
                ),
                md(
                    f"""
                    ### Matched by ticker ({n_ticker:,})

                    OpenFIGI market ticker found a non-blank ticker row in the SEC
                    fund-reference table.
                    """
                ),
                review_table(
                    ticker_funds, ticker_columns, f"Matched by ticker ({n_ticker})"
                ),
                md(
                    f"""
                    ### Matched by name correction ({n_name:,})

                    Ticker join missed; ISIN is in `NAME_CORRECTIONS` and identifiers
                    were filled from the catalogued `(class_id, series_id)`.
                    """
                ),
                review_table(
                    name_funds, name_columns, f"Matched by name ({n_name})"
                ),
                md(
                    f"""
                    ### Did not match — unmatchable ({n_unmatchable:,})

                    No open-end series/class row to attach (e.g. UITs). Identifiers
                    stay empty; N-CEN classification will not run for these rows.
                    They remain in the selection for this and later steps until a
                    later step explicitly drops them.
                    """
                ),
                review_table(
                    unmatchable_funds,
                    miss_columns,
                    f"Unmatchable / no EDGAR series ({n_unmatchable})",
                ),
                (
                    stack(
                        md(
                            f"""
                            ### Closed still in selection ({n_closed:,})

                            Unexpected: these closed/merged ISINs were expected to
                            leave in step 3. Identifiers empty.
                            """
                        ),
                        review_table(
                            closed_funds, miss_columns, f"Closed ({n_closed})"
                        ),
                    )
                    if n_closed
                    else None
                ),
                (
                    stack(
                        md(
                            f"""
                            ### No match status ({len(no_status):,})

                            Rows in the working set without an `edgar_match_status`.
                            """
                        ),
                        review_table(
                            no_status,
                            miss_columns,
                            f"No match status ({len(no_status)})",
                        ),
                    )
                    if len(no_status)
                    else None
                ),
            ),
            decision=stack(
                md(
                    f"""
                    ### Decision

                    No funds are removed in this step. All {len(funds_edgar):,} rows
                    that entered from `funds_openfigi` stay in `funds_edgar`.

                    - **{n_ticker:,} ticker matches** and **{n_name:,} name corrections**
                      carry full CIK / series / class identifiers for later N-PORT,
                      primary-class, and N-CEN steps.
                    - **{n_unmatchable:,} unmatchable** funds stay with empty EDGAR
                      identifiers (e.g. UITs); they cannot use the series-based
                      classification path unless a later step drops them.

                    Special name-correction notes: Invesco Main Street All Cap;Y is
                    class Y in the SEC file (OpenFIGI name says A); HAWG is stored as
                    the HCM Hedged Equity ETF series (SEC ticker list currently
                    assigns HAWG to a different series).
                    """
                ),
                selection_stats(len(funds_edgar), when="end"),
            ),
        )
    _step_view
    return (funds_edgar,)


@app.cell(hide_code=True)
def _(get_edgar, mo, run_step_button, step_header):
    nport_ready = get_edgar() is not None
    run_step_5 = run_step_button(
        ready=nport_ready,
        tooltip=None if nport_ready else "Run step 4 first",
    )
    step_header("## 5. Verify if some funds belong to the same series", run_step_5)
    return (run_step_5,)


@app.cell
def _():
    def series_groups(funds_edgar):
        class_id = funds_edgar["edgartools_class_id"].astype("string").str.strip()
        has_class_id = (
            class_id.notna() & class_id.ne("") & class_id.str.lower().ne("<na>")
        )
        missing_class_id = funds_edgar.loc[
            ~has_class_id,
            [
                "Name",
                "ISIN",
                "openfigi_market_id",
                "edgartools_cik",
                "edgartools_series_id",
            ],
        ]
        cik = funds_edgar["edgartools_cik"].astype("string").str.strip()
        series_id = funds_edgar["edgartools_series_id"].astype("string").str.strip()
        has_pair = (
            cik.notna()
            & cik.ne("")
            & cik.str.lower().ne("<na>")
            & series_id.notna()
            & series_id.ne("")
            & series_id.str.lower().ne("<na>")
        )
        pair = cik + " ; " + series_id
        pair_counts = pair.loc[has_pair].value_counts()
        shared_pairs = pair_counts.loc[pair_counts.gt(1)]
        same_cik_series = funds_edgar.loc[pair.isin(shared_pairs.index)].sort_values(
            ["edgartools_cik", "edgartools_series_id", "Name"]
        )
        return missing_class_id, same_cik_series

    return (series_groups,)


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    add_prefixed_columns,
    capture_prints,
    get_edgar,
    run_step_5,
    series_groups,
    set_nport_check,
):
    if run_step_5.value:
        nport_input = get_edgar()
        if nport_input is not None:
            from helpers.funds_functions.confirm_nport_series_classes import (
                add_nport_same_series,
            )

            _missing_class_id, _same_cik_series = series_groups(nport_input["funds"])
            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _checked = add_nport_same_series(_same_cik_series)
            _same_cik_series = _same_cik_series.copy()
            _same_cik_series["nport_same_series"] = (
                _checked["nport_same_series"]
                .reindex(_same_cik_series.index)
                .fillna("not checked")
            )
            _same_cik_series["AUM"] = _same_cik_series[
                "Fund Total Assets under Management"
            ]
            _series_normalized = add_prefixed_columns(
                nport_input["normalized"],
                _checked[["nport_same_series"]],
                "edgar.",
                source_columns=[],
            )
            _series_sheets = {
                **nport_input["sheets"],
                "Funds": _series_normalized,
                "No EDGAR share class": _series_normalized.loc[_missing_class_id.index],
                "Common fund series": _series_normalized.loc[_same_cik_series.index],
            }
            set_nport_check(
                {
                    "funds": _checked,
                    "log": _log_buffer.getvalue(),
                    "missing_class_id": _missing_class_id,
                    "same_cik_series": _same_cik_series,
                    "sheets": _series_sheets,
                    "export": NORMALIZED_XLSX_LABEL,
                    "started": len(nport_input["funds"]),
                }
            )
    return


@app.cell
def _(
    get_edgar,
    get_nport_check,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    series_input = get_edgar()
    mo.stop(
        series_input is None,
        mo.md("Run step 4 first. This step reads `funds_edgar`."),
    )
    _n_start = len(series_input["funds"])
    _documentation = stack(
        selection_stats(_n_start),
        mo.md("""
        ### What and why

        One EDGAR series is one portfolio. The thesis needs one performance path
        per portfolio, so multiple selected share classes of the same CIK + series
        must be detected before collapsing to a primary class. An N-PORT check
        confirms that the reference-table grouping matches what the registrant
        actually filed.

        ### How

        Operates only on `funds_edgar` (funds already dropped in earlier steps
        are not present). No rows are removed here.

        1. **Detect shared series.** Group current selection by
           `edgartools_cik` + `edgartools_series_id`. Flag pairs with count > 1
           and rows missing a class id. Prepare in-memory sheets
           `Common fund series` and `No EDGAR share class`.
        2. **Enrichment — N-PORT confirmation (source: latest N-PORT XML for the
           series).** For each shared-series class still in the selection:
           - `genInfo/seriesId` must equal `edgartools_series_id`.
           - `edgartools_class_id` must appear on a `monthlyTotReturn` of that
             filing (else try the previous N-PORT).
           - The filing has one `invstOrSec` holdings list for the series.
           - Set `nport_same_series` = `confirmed` + report date when both
             checks hold (column `edgar.nport_same_series` on `Funds`).
        3. **AUM context.** Sheet column Fund Total Assets under Management is
           the Lipper figure for that row (classes of one series can differ;
           blank ≠ zero). It is shown for review; secondary classes are dropped
           in the next step only.
        """),
    )
    nport_check = get_nport_check()
    if nport_check is None:
        missing_class_id = None
        same_cik_series = None
        series_sheets = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to list shared series and confirm classes on N-PORT._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        missing_class_id = nport_check["missing_class_id"]
        same_cik_series = nport_check["same_cik_series"]
        series_sheets = nport_check["sheets"]
        class_count = len(missing_class_id)
        class_verb = "fund has" if class_count == 1 else "funds have"
        series_count = len(same_cik_series)
        series_verb = "fund shares" if series_count == 1 else "funds share"
        confirmed_count = int(
            same_cik_series["nport_same_series"]
            .astype("string")
            .str.startswith("confirmed")
            .sum()
        )
        series_columns = [
            "edgartools_cik",
            "edgar_company_name",
            "edgartools_series_id",
            "edgar_series_name",
            "edgartools_class_id",
            "edgar_class_name",
            "Name",
            "ISIN",
            "AUM",
            "nport_same_series",
        ]
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{class_count} {class_verb} no EDGAR share class id** \n"
                    f"- Prepared sheet `No EDGAR share class` ({class_count} rows) in memory "
                    f"(written to `{nport_check['export']}` at step 8) \n"
                ),
                review_table(
                    missing_class_id,
                    [
                        "Name",
                        "ISIN",
                        "openfigi_market_id",
                        "edgartools_cik",
                        "edgartools_series_id",
                    ],
                    "Missing EDGAR share class id",
                ),
                mo.md(
                    f"- **{series_count} {series_verb} a CIK and series with another selected fund** \n"
                    f"- Prepared sheet `Common fund series` ({series_count} rows) and "
                    f"`edgar.nport_same_series` on `Funds` in memory "
                    f"(written to `{nport_check['export']}` at step 8) \n"
                    f"- **{confirmed_count}** of {series_count} classes are confirmed on the series N-PORT. \n"
                ),
                review_table(same_cik_series, series_columns, "Same CIK and series"),
            ),
            decision=stack(
                mo.md("""
                No funds are removed in this step. The selection stays `funds_edgar`.
                Shared series are flagged so the next step can drop secondary share
                classes; until then every current row remains in scope.
                """),
                selection_stats(_n_start, when="end"),
            ),
        )
    _step_view
    return missing_class_id, same_cik_series, series_sheets


@app.cell(hide_code=True)
def _(get_nport_check, mo, run_step_button, step_header):
    primary_ready = get_nport_check() is not None
    run_step_5b = run_step_button(
        ready=primary_ready,
        tooltip=None if primary_ready else "Run step 5 first",
    )
    step_header(
        "## 5b. Keep the primary share class per series and wrapper",
        run_step_5b,
    )
    return (run_step_5b,)


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    get_edgar,
    get_nport_check,
    pd,
    run_step_5b,
    set_primary,
):
    if run_step_5b.value:
        _primary_input = get_edgar()
        _series_state = get_nport_check()
        if _primary_input is not None and _series_state is not None:
            from helpers.funds_functions.select_primary_share_class import (
                select_primary_share_class,
            )

            _series_sheets = _series_state["sheets"]
            _funds_primary, _dropped_classes = select_primary_share_class(
                _primary_input["funds"]
            )
            _collapsed = (
                _dropped_classes["edgartools_series_id"].nunique()
                if len(_dropped_classes)
                else 0
            )
            _primary_normalized = _series_sheets["Funds"].copy()
            _primary_flag = pd.Series(
                pd.NA, index=_primary_normalized.index, dtype="boolean"
            )
            _primary_flag.loc[_funds_primary.index] = True
            _primary_flag.loc[_dropped_classes.index] = False
            _primary_normalized["edgar.primary_share_class"] = _primary_flag
            _primary_normalized["edgar.primary_rule"] = _funds_primary[
                "primary_rule"
            ].reindex(_primary_normalized.index)
            _dropped_sheet = _primary_normalized.loc[_dropped_classes.index].copy()
            _dropped_sheet["edgar.kept_isin"] = _dropped_classes["kept_isin"]
            _primary_sheets = {
                **_series_sheets,
                "Funds": _primary_normalized,
                "Dropped share classes": _dropped_sheet,
            }
            set_primary(
                {
                    "funds": _funds_primary,
                    "dropped": _dropped_classes,
                    "collapsed": _collapsed,
                    "sheets": _primary_sheets,
                    "export": NORMALIZED_XLSX_LABEL,
                    "started": len(_primary_input["funds"]),
                }
            )
    return


@app.cell
def _(
    get_nport_check,
    get_primary,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    series_state = get_nport_check()
    mo.stop(
        series_state is None,
        mo.md("Run step 5 first. This step reads the shared-series check."),
    )
    primary_result = get_primary()
    _n_start = series_state["started"]
    _documentation = stack(
        selection_stats(_n_start),
        mo.md(r"""
        ### What and why

        The thesis compares management style **and** distribution wrapper (mutual
        fund versus ETF). Performance should therefore be measured once per
        portfolio **within** each wrapper: keeping every fee-differentiated
        share class of the same series would overweight multi-class families,
        but collapsing an ETF and a mutual fund that share an EDGAR series into
        a single row would erase the wrapper dimension of the design. This step
        retains one primary share class per EDGAR series **and** Lipper
        `fund_wrapper`, and leaves singleton and series-less rows untouched.

        ### How

        **Competition unit.** Classes that remain in the selection compete only
        when they share the same `edgartools_series_id` **and** the same
        normalised wrapper (`ETF` versus `mutual fund`). An ETF share class and
        a mutual-fund share class of one series therefore both survive this
        step (each as the primary of its own wrapper group). The deciding rule
        within a group is stored in `primary_rule`.

        1. **Largest AUM** (`primary_rule = largest aum`).
           Compare Lipper Fund Total Assets under Management inside the
           (series, wrapper) group. Blank AUM is ignored (never treated as
           zero). If at least one class has a numeric AUM, keep the unique class
           with the maximum. If several classes share that maximum, fall through
           to rule 2 on that tied subset. If **no** class in the group has AUM,
           fall through to rule 2 on the whole group.

        2. **EDGAR class-name preference** (`primary_rule = class rank`).
           Used only when AUM is missing for every class in the group, or when
           several classes share the largest AUM. The goal is to keep the class
           that best represents a **retail investor** holding of that portfolio
           (not an institutional, retirement-plan, 529, or advisor-channel
           variant). Each candidate gets a priority score from its EDGAR
           `edgar_class_name` (and, for Gabelli AAA, company/series context).
           Names are normalised (lowercase, punctuation stripped, `&` → `and`).
           **Lower score wins.** A class is assigned the **first** tier below
           that matches it; tiers are tried in this order so more universal /
           retail-default labels beat niche or restricted ones:

           | Priority | Tier | Match rule | Why this tier and this order |
           |---:|---|---|---|
           | 0 | Unsuffixed / retail default | `edgar_class_name` equals `edgar_series_name` **and** the class name does **not** contain the token `advisor`. | Many funds (especially older ones) never lettered their original retail class; the class row simply repeats the series name. That unsuffixed row is the historical “main” share class. **Advisor** classes often reuse the same series wording but are sold through intermediaries with different fees, so they are deliberately excluded from this top tier. |
           | 1 | Investor / Ordinary | Tokens include `investor` or `ordinary`, or the name is exactly `inv`. | Explicit retail labels used by large families (e.g. Vanguard/Fidelity “Investor”; some “Ordinary” share classes). Preferred next because the name itself signals the individual-investor share class, even when it does not equal the series name. |
           | 2 | Gabelli Class AAA | Tokens include `aaa` **and** `gabelli` appears in company, series, or class name. | Gabelli’s flagship retail class is branded **AAA**, not Class A. The Gabelli context check avoids treating unrelated “AAA” strings as this product. Placed **before** generic Class A so Gabelli’s true retail default wins when both patterns could otherwise compete in the same family. |
           | 3 | Class A (non-529) | Tokens look like Class A (`a`, `class a`, `a shares`, …) **and** do **not** include `529`. | Across most broker-sold open-end funds, **Class A** is the standard front-end retail class and the usual published comparison share. **529** college-savings A shares are a different distribution channel (state plans), so they are kept out of this tier even if the name ends in “A”. Ranked after Investor/Gabelli AAA because those labels are more specific retail defaults when present. |
           | 4 | Admiral | Tokens include `admiral` (e.g. Vanguard Admiral). | Vanguard’s lower-expense retail class for larger account balances — still aimed at individuals, but brand-specific and usually not the only retail option. Prefer Class A / Investor when those exist; prefer Admiral over Institutional when choosing among remaining retail-ish names. |
           | 5 | Institutional / Class I | Tokens include `institutional`, or end with Class I / I shares. | Lower expense ratios, but typically high minimums or institutional eligibility. Useful when no clearer retail class remains, yet not preferred for a thesis sample meant to reflect individual-investor share classes. |
           | 6 | Class Y | Tokens look like Class Y (`y`, `class y`, `y shares`, …). | Often an omnibus / intermediary / platform class rather than a direct retail offering. Kept as a named preference only after Institutional so a Y class can still win over an unlabeled catch-all, but never over clearer retail or institutional labels. |
           | 7 | Any other class | Everything else (Class C, R, R6, NAV, Advisor-only names, 529-A, etc.). | Catch-all for higher-fee retail (e.g. C), retirement-plan (R/R6), NAV, advisor-only, 529, and odd EDGAR labels. These are last because they are channel-specific, fee-distorted, or not the intended open-end retail comparison unit. |

           After scoring, keep the unique class with the **best** (lowest)
           priority. If several classes share that best tier, fall through to
           rule 3.

        3. **Smallest `edgartools_class_id`** (`primary_rule = smallest class id`).
           Numeric part of the class id (e.g. `C000209245` → 209245); the
           smallest wins. This is only a final tie-break.

        **Scope.** Only classes still in the incoming selection that share a
        series **and** wrapper compete. A fund that is the only selected class
        of its (series, wrapper) group stays (`primary_rule = only class`). A
        fund with no series id stays (`primary_rule = no series`). Classes
        dropped here leave the working selection permanently — later steps read
        only `funds_primary`.

        **Outputs.** Kept rows → `funds_primary`. Flags
        `edgar.primary_share_class` / `edgar.primary_rule` on `Funds`; removed
        classes → sheet `Dropped share classes` with `edgar.kept_isin` (the
        primary ISIN within the same series–wrapper group; audit only; not
        re-selected later).
        """),
    )
    if primary_result is None:
        funds_primary = None
        primary_sheets = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to keep one primary share class "
                "per series and wrapper._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        funds_primary = primary_result["funds"]
        dropped_classes = primary_result["dropped"]
        primary_sheets = primary_result["sheets"]
        primary_from_series = funds_primary.loc[
            funds_primary["edgartools_series_id"].isin(
                dropped_classes["edgartools_series_id"]
            )
        ].copy()
        primary_from_series["AUM"] = primary_from_series[
            "Fund Total Assets under Management"
        ]
        primary_columns = [
            "edgartools_cik",
            "edgar_company_name",
            "edgartools_series_id",
            "edgar_series_name",
            "edgartools_class_id",
            "edgar_class_name",
            "fund_wrapper",
            "Name",
            "ISIN",
            "AUM",
            "primary_rule",
        ]
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{primary_result['started']}** funds entered from the current selection \n"
                    f"- **{len(dropped_classes)}** share classes were removed from **{primary_result['collapsed']}** series (leave permanently) \n"
                    f"- **{len(funds_primary)}** funds remain in `funds_primary`, one class per series × wrapper \n"
                    f"- Prepared `edgar.primary_share_class` / `edgar.primary_rule` on `Funds` "
                    f"and sheet `Dropped share classes` ({len(dropped_classes)} rows) in memory "
                    f"(written to `{primary_result['export']}` at step 8) \n"
                ),
                review_table(
                    primary_from_series, primary_columns, "Primary share class (kept)"
                ),
                (
                    review_table(
                        dropped_classes,
                        [
                            "edgartools_cik",
                            "edgartools_series_id",
                            "edgartools_class_id",
                            "edgar_class_name",
                            "fund_wrapper",
                            "Name",
                            "ISIN",
                            "Fund Total Assets under Management",
                            "kept_isin",
                        ],
                        f"Dropped share classes ({len(dropped_classes)})",
                    )
                    if len(dropped_classes)
                    else None
                ),
            ),
            decision=stack(
                mo.md(
                    f"""
                    Keep one primary share class per EDGAR series and fund
                    wrapper. ETF and mutual-fund classes of the same series both
                    remain when each is the primary of its wrapper group.
                    **{len(dropped_classes)}** secondary classes leave the
                    working selection permanently. Later steps (style,
                    timeseries, final export) read only `funds_primary`
                    ({len(funds_primary):,} funds) — dropped classes are not
                    reopened.
                    """
                ),
                selection_stats(len(funds_primary), when="end"),
            ),
        )
    _step_view
    return funds_primary, primary_sheets


@app.cell(hide_code=True)
def _(get_primary, mo, run_step_button, step_header):
    style_ready = get_primary() is not None
    run_step_6 = run_step_button(
        ready=style_ready,
        tooltip=None if style_ready else "Run step 5b first",
    )
    step_header("## 6. Verify fund type (active vs passive)", run_step_6)
    return (run_step_6,)


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    add_prefixed_columns,
    capture_prints,
    get_primary,
    run_step_6,
    set_style,
):
    if run_step_6.value:
        _primary_state = get_primary()
        if _primary_state is not None:
            import importlib
            import helpers.funds_functions.classify_fund_management_style as _style_mod
            import helpers.funds_functions.fund_management_style_rules as _style_rules

            # Marimo keeps imported helpers in memory; reload so N-CEN scan / rule
            # version changes apply without restarting the kernel.
            importlib.reload(_style_rules)
            importlib.reload(_style_mod)
            classify_fund_management_style = _style_mod.classify_fund_management_style

            _funds_primary = _primary_state["funds"]
            _primary_sheets = _primary_state["sheets"]
            _log_buffer, _redirect = capture_prints()
            with _redirect:
                print(f"style rule version: {_style_mod.RULE_VERSION}")
                _funds = classify_fund_management_style(_funds_primary)

            def _type_label(series):
                values = series.astype("string").str.strip()
                blank = values.isna() | values.eq("") | values.str.lower().eq("<na>")
                return values.mask(blank)

            _funds = _funds.copy()
            _sheet_type = _type_label(_funds["fund_type"])
            _edgar_type = _type_label(_funds["fund_management_style"])
            _sheet_cf = _sheet_type.fillna("").str.casefold()
            _edgar_cf = _edgar_type.fillna("").str.casefold()

            # Decision on the working fund_type (EDGAR style stays in
            # fund_management_style for audit).
            _funds["fund_type_sheet"] = _sheet_type
            _decision = []
            _final_type = []
            for _idx in _funds.index:
                _e = _edgar_cf.at[_idx]
                _s = _sheet_cf.at[_idx]
                _sheet_val = _sheet_type.at[_idx]
                if _e == "other":
                    _decision.append("drop_other")
                    _final_type.append(_sheet_val)
                elif _e == "unknown":
                    _decision.append("keep_original_unknown")
                    _final_type.append(_sheet_val)
                elif _s != "" and _s == _e:
                    _decision.append("confirmed")
                    _final_type.append(_sheet_val)
                elif _s == "passive" and _e == "active":
                    _decision.append("override_to_active")
                    _final_type.append("Active")
                elif _s == "active" and _e == "passive":
                    _decision.append("override_to_passive")
                    _final_type.append("Passive")
                else:
                    _decision.append("keep_original")
                    _final_type.append(_sheet_val)
            _funds["fund_type_decision"] = _decision
            _funds["fund_type"] = _final_type
            _fund_type_mismatch = _funds.loc[_sheet_cf.ne(_edgar_cf)].copy()

            _drop_other = _funds["fund_type_decision"].eq("drop_other")
            _dropped_other = _funds.loc[_drop_other].copy()
            _kept = _funds.loc[~_drop_other].copy()

            # New columns go at the end of Funds. Rows removed in 5b stay blank.
            _style_normalized = add_prefixed_columns(
                _primary_sheets["Funds"],
                _funds,
                "fund_type_dq.",
                source_columns=_funds_primary.columns,
                source_prefix="fund_management_",
            )
            if "ds.fund_type" in _style_normalized.columns:
                _style_normalized.loc[_kept.index, "ds.fund_type"] = _kept["fund_type"]
            _style_sheets = {
                **_primary_sheets,
                "Funds": _style_normalized,
                "Fund type mismatch": _style_normalized.loc[_fund_type_mismatch.index],
                "Dropped fund type other": _style_normalized.loc[_dropped_other.index],
            }
            set_style(
                {
                    "funds": _kept,
                    "classified": _funds,
                    "normalized": _style_normalized,
                    "sheets": _style_sheets,
                    "export": NORMALIZED_XLSX_LABEL,
                    "mismatch": _fund_type_mismatch,
                    "dropped_other": _dropped_other,
                    "started": len(_funds),
                    "log": _log_buffer.getvalue(),
                }
            )
    return


@app.cell
def _(
    get_primary,
    get_style,
    md,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    primary_state = get_primary()
    mo.stop(
        primary_state is None,
        mo.md("Run step 5b first. This step reads the primary share class."),
    )
    _n_start = len(primary_state["funds"])
    _documentation = stack(
        selection_stats(_n_start),
        md("""
        ### What and why

        The working Excel sheet already carries an Active / Passive (and related)
        `fund_type` label, but that label was assigned from limited commercial
        metadata. This step **challenges that initial classification** with
        richer SEC evidence: the registrant’s own N-CEN series answers and, when
        those do not decide, the fund’s prospectus language. Verifying style with
        that filing-level detail increases the reliability of the Active vs
        Passive taxonomy used later. The ETF vs mutual-fund wrapper is a separate
        question; style here is about how the portfolio is managed.

        ### How

        Operates only on `funds_primary` (secondary share classes already removed
        in step 5b are not present). Classification is at the EDGAR series
        (CIK + series id); all remaining selected classes of that series inherit
        the same label. Labels: **Passive**, **Active**, **Other**, **Unknown**.
        First source that decides wins.

        After classification, a **decision** updates the working selection (see
        Decision): Active ↔ Passive overrides adopt the EDGAR label; **Other**
        funds are dropped permanently; **Unknown** keeps the original sheet
        `fund_type`. Later steps read only the kept `funds_classified` frame.

        #### 1. Source — N-CEN for the series (questionnaire XML)

        Form N-CEN is the SEC’s annual census of registered investment companies.
        A large registrant may file several N-CEN reports; the **newest CIK-level
        filing does not always list every series**. This step therefore scans
        recent N-CEN filings for the CIK (newest first) until it finds the
        series’s management-investment question node
        (`managementInvestmentQuestion` whose `mgmtInvSeriesId` matches the EDGAR
        series id), and falls back to series-scoped N-CEN filings if needed, then
        reads that node’s fund-type answers.

        **What `fundTypes` / `fundType` are.** On Form N-CEN Item C.3 (“Type of
        fund”), the registrant checks **all that apply** for the series. In the
        filing XML those answers appear under `fundTypes` as one or more
        `fundType` values (a series can carry several labels at once — e.g.
        Exchange-Traded Fund **and** Index Fund). When the series is an index
        fund, the schema uses an `indexFundInfo` block (with tracking metrics)
        whose type attribute is **Index Fund**; the parser treats that the same
        as a fund-type label. Older filings may use a single legacy `fundType`
        element, including the literal **N/A**.

        **Allowed values** (SEC enumeration; check-all-that-apply):

        | Value | Meaning (Form N-CEN) |
        |---|---|
        | Exchange-Traded Fund | Shares trade on an exchange (ETF wrapper). |
        | Exchange-Traded Managed Fund | Exchange-traded managed-fund wrapper. |
        | Index Fund | Seeks to track a specified index (via `indexFundInfo` when present). |
        | Inverse of a benchmark | Seeks a multiple / inverse / leveraged-inverse of an index or benchmark. |
        | Interval Fund | Closed-end fund with periodic repurchases (rule 23c-3). |
        | Fund of Funds | Invests in other funds beyond ordinary 12(d)(1) limits. |
        | Master-Feeder Fund | Master or feeder in a two-tier structure. |
        | Money Market Fund | Money-market fund. |
        | Target Date Fund | Glide-path mix that changes with a target retirement date / age. |
        | Underlying fund | Underlying fund to a variable annuity or variable life contract. |
        | N/A | No special type checked. |

        **How those values drive classification.** The parser collects every
        non-N/A label for the series into a list, then `label_from_ncen` applies
        the first matching rule below (order matters; a series can have multiple
        labels):

        1. Any **Index Fund** label / `indexFundInfo` → **Passive**.
        2. Else any of **Target Date Fund**, **Fund of Funds**, **Interval Fund**
           → **Other**.
        3. Else any remaining non-empty label set (e.g. **Exchange-Traded Fund**,
           **Money Market Fund**, **Master-Feeder Fund**, **Underlying fund**,
           **Inverse of a benchmark**, **Exchange-Traded Managed Fund**) →
           **Active** for this taxonomy — including ETF wrappers that are *not*
           also Index Fund.
        4. Else only **N/A** / empty, or the series missing from the filing →
           no N-CEN decision (fall through to Jev).

        Rule detail and rationale:

        | Label | Match rule | Why |
        |---|---|---|
        | Passive | Series lists fund type **Index Fund**, or `indexFundInfo` is present (which contributes that Index Fund label). | The registrant must disclose index-fund status and tracking metrics in N-CEN; that self-report is stronger evidence of a passive mandate than a commercial sheet flag or the word “Index” in a marketing name. |
        | Other | Fund-type labels include **Target Date Fund**, **Fund of Funds**, or **Interval Fund**, and the series is **not** an index fund (Index Fund / `indexFundInfo` would already have won as Passive). | Plain English: these are special product structures, not a simple “manager picks securities” fund and not a simple “tracks an index” fund. **Target date** funds follow a retirement glide path; **funds of funds** mainly hold other funds; **interval** funds use a different liquidity model. Active vs Passive here asks how a single portfolio is managed — those types do not fit that binary cleanly, so putting them in either bin would mix in products that are not really either for the thesis. |
        | Active | Series has one or more other non-N/A fund-type labels (including an **ETF** wrapper type) and **no** `indexFundInfo` / Index Fund label. | Plain English: N-CEN gave a real fund-type answer, but it did **not** say the series is an index fund — so for this taxonomy we treat it as actively managed. **ETF** on N-CEN means how the shares are offered (exchange-traded wrapper), not “passive.” A passive ETF still gets `indexFundInfo` / Index Fund from the SEC; without that block, an ETF or mutual-fund series with other typed labels counts as Active. |
        | No decision (fall through) | Series absent from the scanned N-CEN filings, or fund type is only **N/A** / empty. | The census then gives no usable style signal, so prospectus text is needed. |

        #### 2. Source — Jev (`jev-latest`) on prospectus text

        Used only when N-CEN does not decide.

        **What Jev is.** **Jev** is an AI decision model from [TypeSafe AI](https://typesafe.ai)
        (this pipeline uses `jev-latest`). It classifies data and returns
        **structured choices for software**, instead of chatting or generating
        prose. You give Jev some context (here: a prospectus excerpt and series
        name) and a set of **constrained questions**. It returns structured
        answers — categories, scores, or yes/no-style probabilities — together
        with **confidence** scores that code can use immediately. Documentation:
        [docs.typesafe.ai](https://docs.typesafe.ai/).

        How it differs from chatbots (typical LLMs):

        - **No text generation.** Jev does not write paragraphs, answer
          open-ended questions, or hold a conversation.
        - **Faster and cheaper for classification.** It is built for quick,
          high-volume labeling at lower cost and latency than asking a large
          language model to “return JSON.”
        - **Built for software.** Outputs arrive in predictable formats; the
          notebook does not need to parse free-form text into Active / Passive /
          Other.

        **Why it is used here.** When N-CEN does not state the management
        style, the remaining evidence is prospectus wording. Reading that
        wording by hand for every series is slow and hard to reproduce. Jev is
        therefore used as a **fixed-label classifier** on the excerpt. In
        practice the pipeline: (1) prepares the prospectus text and series name;
        (2) asks one closed Choice question with exactly three allowed answers —
        Passive, Active, or Other — each with a short definition; (3) keeps the
        returned label only when confidence is high enough (see below). Jev does
        **not** invent new categories, write a narrative justification, or
        choose which filing to download — those steps stay in code. Results are
        cached under rule version `ncen-jev-v2` so a re-run reuses the same
        judgments unless the rule version changes.

        **How it is used here.** For each undecided series the code sends state
        `{series_name, prospectus_text}` and the Choice question
        `management_style`. The instructions tell Jev to judge the fund’s
        **own mandate** (does it track an index, or does a manager select
        securities?). An index named only as a performance benchmark or as a
        stock-selection screen must **not** be treated as Passive. The returned
        label is kept only when confidence is high enough (see table below);
        otherwise the series stays **Unknown**.

        **What text is sent.** Prefer the full **497K** summary-prospectus
        investment objective for that series (recent filings scanned until a
        matching series objective is found). If none is usable, take the latest
        **485BPOS** / **485APOS** statutory prospectus text and keep only an
        excerpt: the investment-objective sentence plus the principal
        “fund/portfolio invests…” strategy paragraph, skipping table-of-contents
        lines (dot leaders). Empty excerpt → no Jev call.

        **Decision rules on the Jev answer:**

        | Label | Match rule | Why |
        |---|---|---|
        | Passive | Jev chooses Passive: the fund’s job is to track, match, or approximate a stated index and it is not actively managed. | Prospectus language is the legal mandate when the census left style blank; tracking language is the passive signal. |
        | Active | Jev chooses Active: a manager selects securities for an objective such as growth or income; naming an index only as a comparison or screen does **not** make the fund Passive. | Avoids false Passive labels for active funds that merely cite a benchmark. |
        | Other | Jev chooses Other: target-date, fund of funds, or interval fund rather than a plain active or index fund. | Same exclusion logic as N-CEN Other when the census did not say so. |
        | Unknown | Confidence below 0.60, or a choice outside those three labels. | Low confidence means the excerpt is ambiguous; better to mark Unknown for review than to invent a hard Active / Passive call. |

        #### 3. Fallbacks

        - No CIK/series → Unknown (not sent to EDGAR).
        - No prospectus text → Unknown (not sent to Jev).

        **Explicitly unused:** edgartools’ single `fundType` tag (drops
        `indexFundInfo`), portfolio turnover, and the word “Index” in the name.

        **Outputs.** `fund_management_style`, `_source`, `_detail`,
        `fund_type_sheet`, `fund_type_decision` (prefix `fund_type_dq.*`). Working
        `fund_type` may be overridden. Sheet `Fund type mismatch` lists
        classification disagreements; `Dropped fund type other` lists removals.
        Kept frame: `funds_classified`.
        """),
    )
    style_result = get_style()
    if style_result is None:
        funds_classified = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to classify fund type._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        funds_classified = style_result["funds"]
        classified_all = style_result.get("classified", funds_classified)
        dropped_other = style_result.get("dropped_other")
        if dropped_other is None:
            dropped_other = classified_all.iloc[0:0].copy()
        style = classified_all["fund_management_style"].astype("string")
        source = classified_all["fund_management_style_source"].astype("string")
        detail = classified_all["fund_management_style_detail"].astype("string").fillna("")
        style_counts = (
            style.value_counts()
            .rename_axis("fund_management_style")
            .reset_index(name="funds")
        )
        active = int(style.eq("Active").sum())
        passive = int(style.eq("Passive").sum())
        other = int(style.eq("Other").sum())
        unknown = int(style.eq("Unknown").sum())
        from_ncen = int(source.eq("N-CEN").sum())
        from_jev = int(source.eq("Jev").sum())
        no_series = int(detail.eq("no EDGAR series").sum())
        no_prospectus = int(detail.str.contains("no prospectus text", na=False).sum())
        low_confidence = int(detail.str.startswith("Jev chose", na=False).sum())

        sheet_for_compare = (
            classified_all["fund_type_sheet"]
            if "fund_type_sheet" in classified_all.columns
            else classified_all["fund_type"]
        )
        sheet_raw = sheet_for_compare.astype("string").str.strip()
        sheet_blank = (
            sheet_raw.isna()
            | sheet_raw.eq("")
            | sheet_raw.str.lower().eq("<na>")
        )
        sheet_cf = sheet_raw.mask(sheet_blank, "").str.casefold()
        class_cf = style.fillna("").str.strip().str.casefold()
        n_total = len(classified_all)
        n_confirmed = int((sheet_cf.ne("") & sheet_cf.eq(class_cf)).sum())
        n_disagree = int((sheet_cf.ne("") & sheet_cf.ne(class_cf)).sum())
        n_sheet_blank = int(sheet_cf.eq("").sum())

        def _transition(from_label: str, to_label: str) -> int:
            return int(
                (
                    sheet_cf.eq(from_label.casefold())
                    & class_cf.eq(to_label.casefold())
                ).sum()
            )

        n_a_to_p = _transition("Active", "Passive")
        n_p_to_a = _transition("Passive", "Active")
        n_a_to_o = _transition("Active", "Other")
        n_p_to_o = _transition("Passive", "Other")
        n_a_to_u = _transition("Active", "Unknown")
        n_p_to_u = _transition("Passive", "Unknown")
        n_ap_transitions = (
            n_a_to_p + n_p_to_a + n_a_to_o + n_p_to_o + n_a_to_u + n_p_to_u
        )
        n_other_disagree = n_disagree - n_ap_transitions

        if "fund_type_decision" in classified_all.columns:
            decision_col = classified_all["fund_type_decision"].astype("string")
            n_dec_confirmed = int(decision_col.eq("confirmed").sum())
            n_dec_to_active = int(decision_col.eq("override_to_active").sum())
            n_dec_to_passive = int(decision_col.eq("override_to_passive").sum())
            n_dec_unknown = int(decision_col.eq("keep_original_unknown").sum())
            n_dec_keep_other = int(decision_col.eq("keep_original").sum())
            n_dec_drop = int(decision_col.eq("drop_other").sum())
        else:
            n_dec_confirmed = n_confirmed
            n_dec_to_active = n_p_to_a
            n_dec_to_passive = n_a_to_p
            n_dec_unknown = n_a_to_u + n_p_to_u
            n_dec_keep_other = 0
            n_dec_drop = len(dropped_other)

        mismatch_columns = [
            "Name",
            "ISIN",
            "fund_type_sheet",
            "fund_type",
            "fund_management_style",
            "fund_management_style_source",
            "fund_management_style_detail",
            "fund_type_decision",
        ]
        _drop_columns = [
            column
            for column in (
                "Name",
                "ISIN",
                "fund_type_sheet",
                "fund_management_style",
                "fund_management_style_source",
                "fund_management_style_detail",
                "fund_type_decision",
            )
            if column in dropped_other.columns
        ]
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                md(f"""
                ### Classified labels (before the Decision)

                The classifier labeled **{n_total}** funds as **{active}** Active,
                **{passive}** Passive, **{other}** Other, and **{unknown}** Unknown.
                Most labels come from N-CEN (**{from_ncen}** funds); Jev is used
                only when N-CEN does not decide (**{from_jev}** funds).

                A small remainder is Unknown for mechanical reasons:
                **{no_series}** have no CIK or series id (not sent to EDGAR),
                **{no_prospectus}** had no usable prospectus text after N-CEN
                failed to decide, and **{low_confidence}** had a Jev choice below
                the 0.60 confidence threshold.

                ### Agreement with the original sheet `fund_type`

                Comparison is case-insensitive on non-blank sheet labels
                (`fund_type_sheet`).

                **{n_confirmed}** funds are **confirmed**: the classified style
                matches the original sheet label.

                **{n_disagree}** funds **disagree**. Among rows whose sheet label
                was Active or Passive, the transitions are:

                | Sheet → classified | Funds |
                |---|---:|
                | Active → Passive | {n_a_to_p} |
                | Passive → Active | {n_p_to_a} |
                | Active → Other | {n_a_to_o} |
                | Passive → Other | {n_p_to_o} |
                | Active → Unknown | {n_a_to_u} |
                | Passive → Unknown | {n_p_to_u} |

                {
                    "Those six transitions cover every disagreement among Active/Passive sheet labels."
                    if n_other_disagree == 0
                    else f"Another **{n_other_disagree}** disagreement(s) involve a sheet label that was not plain Active/Passive (or another residual case); they still appear in the mismatch table below."
                }
                {
                    f"**{n_sheet_blank}** funds have a blank sheet `fund_type` and are neither counted as confirmed nor as a sheet disagreement."
                    if n_sheet_blank
                    else ""
                }

                Sheet `Fund type mismatch` ({len(style_result["mismatch"])} rows)
                and the `fund_type_dq.*` columns on `Funds` are kept in memory
                for step 8 (`{style_result["export"]}`).
                """),
                review_table(
                    style_counts, ["fund_management_style", "funds"], "Classified fund type"
                ),
                review_table(style_result["mismatch"], mismatch_columns, "Fund type mismatch"),
            ),
            decision=stack(
                md(f"""
                ### Decision

                The working `fund_type` and the selection are updated as follows
                (EDGAR/Jev style remains in `fund_management_style` for audit):

                - **Confirmed match** (**{n_dec_confirmed}** funds) — sheet and
                  EDGAR agree → **no change** to `fund_type`.
                - **Passive → Active** (**{n_dec_to_active}**) — EDGAR says Active
                  while the sheet said Passive → **set `fund_type` to Active**.
                - **Active → Passive** (**{n_dec_to_passive}**) — EDGAR says
                  Passive while the sheet said Active → **set `fund_type` to
                  Passive**.
                - **EDGAR Other** (**{n_dec_drop}**) — **drop** from the working
                  selection permanently (target-date / fund-of-funds / interval
                  structures). They are not inputs to later steps.
                - **EDGAR Unknown** (**{n_dec_unknown}**) — **keep the original**
                  sheet `fund_type` (do not invent Active/Passive from a weak
                  signal).
                {
                    f"- **Other residual rows** (**{n_dec_keep_other}**) — keep the original sheet `fund_type`."
                    if n_dec_keep_other
                    else ""
                }

                ### Outcome

                - Dropped **{n_dec_drop}** funds (`Dropped fund type other`).
                - Working set after this step: `funds_classified`
                  (**{len(funds_classified)}** funds).
                - Later steps read only this kept frame.
                """),
                review_table(
                    dropped_other, _drop_columns, "Dropped (EDGAR fund type Other)"
                ),
                selection_stats(len(funds_classified), when="end"),
            ),
        )
    _step_view
    return (funds_classified,)


@app.cell(hide_code=True)
def _(get_style, mo, run_step_button, step_header):
    timeseries_ready = get_style() is not None
    run_step_7 = run_step_button(
        ready=timeseries_ready,
        tooltip=None if timeseries_ready else "Run step 6 first",
    )
    step_header("## 7. Verify if there is a time series", run_step_7)
    return (run_step_7,)


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    add_prefixed_columns,
    capture_prints,
    get_style,
    pd,
    run_step_7,
    set_timeseries,
    workbook,
):
    if run_step_7.value:
        timeseries_input = get_style()
        if timeseries_input is not None:
            from helpers.funds_functions.match_daily_total_return import (
                match_daily_total_return,
            )

            _log_buffer, _redirect = capture_prints()
            with _redirect:
                daily_timeseries = pd.read_excel(
                    workbook,
                    sheet_name="D-Timeseries",
                    header=None,
                    engine="openpyxl",
                )
                print(
                    f"D-Timeseries: {len(daily_timeseries)} rows, "
                    f"{daily_timeseries.shape[1]} columns"
                )
                _funds = match_daily_total_return(
                    timeseries_input["funds"], daily_timeseries
                )
            name_gap_columns = [
                column
                for column in (
                    "Name",
                    "openfigi_name",
                    "edgar_name",
                    "ISIN",
                    "daily_tr_name",
                    "daily_tr_observations",
                    "daily_tr_name_source",
                )
                if column in _funds.columns
            ]
            name_gap = _funds.loc[
                _funds["has_daily_total_return"] & ~_funds["daily_tr_name_match"],
                name_gap_columns,
            ].copy()
            funds_without_timeseries = _funds.loc[~_funds["has_daily_total_return"]].copy()

            # Yahoo vs Datastream check on name-gap funds (one-off audit): keep when
            # Yahoo adjusted-close returns correlate highly with the ISIN-linked DS
            # total-return series; drop when there is no ticker or correlation is weak.
            _name_gap_drop_isins = {
                "US31617F8178",  # Fidelity Advisor Series Growth & Income — no OpenFIGI ticker
                "US8174181060",  # Sequoia Fund — weak Yahoo↔DS corr (~0.61 / 0.55)
            }
            _name_gap_keep_isins = {
                "US38141W6205",  # Goldman Sachs US Equity Insights;A (GSSQX) corr ~0.99
                "US55273W4006",  # MFS Blended Research Core Equity A (MUEAX) ~1.00
                "US9695576028",  # Jamestown Equity (JAMEX) ~1.00
                "US92914C7662",  # Voya U.S. Stock Index S2 (ISIPX) ~1.00
                "US1152338687",  # Brown Advisory Flexible Equity;Inv (BIAFX) ~1.00
                "US2779192051",  # Eaton Vance Tax-Managed Growth 1.0 (CAPEX) ~1.00
            }
            _isin_cf = _funds["ISIN"].astype("string").str.strip().str.upper()
            _drop_name_gap = _funds.index.isin(name_gap.index) & _isin_cf.isin(
                _name_gap_drop_isins
            )
            _dropped_name_gap = _funds.loc[_drop_name_gap].copy()
            _kept = _funds.loc[~_drop_name_gap].copy()
            _name_gap_kept = name_gap.loc[
                name_gap["ISIN"].astype("string").str.strip().str.upper().isin(
                    _name_gap_keep_isins
                )
            ].copy()

            # No Datastream TR → Yahoo Price + TR backfill (same recipe as
            # series-check), else drop.
            from helpers.funds_functions.filter_daily_timeseries import (
                fee_from_fund_row,
            )
            from helpers.funds_functions.map_yahoo_timeseries import (
                append_yahoo_price_and_tr_columns,
                fetch_yahoo_price_levels,
                fetch_yahoo_total_return_levels,
                holiday_mask_from_daily_sheet,
            )

            _missing = _kept.loc[
                ~_kept["has_daily_total_return"].fillna(False).astype(bool)
            ].copy()
            _yahoo_filled: list[object] = []
            _yahoo_dropped: list[object] = []
            _yahoo_fill_rows: list[dict] = []
            _daily = daily_timeseries.copy()
            _holiday_mask = holiday_mask_from_daily_sheet(_daily)
            _yahoo_log, _yahoo_redirect = capture_prints()
            with _yahoo_redirect:
                print(f"{len(_missing)} funds have no Datastream daily total return")
                for _idx, _row in _missing.iterrows():
                    _ticker = None
                    for _col in ("openfigi_market_id", "market_identifier"):
                        if _col in _kept.columns and pd.notna(_row.get(_col)):
                            _text = str(_row.get(_col)).strip()
                            if _text and _text.lower() not in {"none", "nan", "<na>"}:
                                _ticker = _text
                                break
                    _isin = str(_row.get("ISIN") or "").strip().upper()
                    _name = str(_row.get("Name") or _ticker or _isin)
                    if not _ticker:
                        _yahoo_dropped.append(_idx)
                        _yahoo_fill_rows.append(
                            {
                                "Name": _name,
                                "ISIN": _isin,
                                "ticker": None,
                                "verdict": "Drop — no OpenFIGI / Yahoo ticker",
                                "yahoo_obs": 0,
                            }
                        )
                        print(f"drop {_isin or _name}: no ticker")
                        continue
                    try:
                        _tr_levels = fetch_yahoo_total_return_levels(_ticker)
                    except Exception as _exc:
                        _tr_levels = None
                        print(f"Yahoo TR fetch failed for {_ticker}: {_exc}")
                    try:
                        _price_levels = fetch_yahoo_price_levels(_ticker)
                    except Exception as _exc:
                        _price_levels = None
                        print(f"Yahoo Price fetch failed for {_ticker}: {_exc}")
                    if _tr_levels is None or _tr_levels.empty:
                        _yahoo_dropped.append(_idx)
                        _yahoo_fill_rows.append(
                            {
                                "Name": _name,
                                "ISIN": _isin,
                                "ticker": _ticker,
                                "verdict": "Drop — no Yahoo total-return history",
                                "yahoo_obs": 0,
                            }
                        )
                        print(f"drop {_ticker}: no Yahoo TR history")
                        continue
                    if _price_levels is None or _price_levels.empty:
                        _yahoo_dropped.append(_idx)
                        _yahoo_fill_rows.append(
                            {
                                "Name": _name,
                                "ISIN": _isin,
                                "ticker": _ticker,
                                "verdict": "Drop — no Yahoo price history",
                                "yahoo_obs": 0,
                            }
                        )
                        print(f"drop {_ticker}: no Yahoo Price history")
                        continue
                    _category = "Yahoo TR"
                    if "fund_management_style" in _row.index and pd.notna(
                        _row.get("fund_management_style")
                    ):
                        _style = str(_row.get("fund_management_style")).strip()
                        if _style in {"Active", "Passive"}:
                            _category = f"{_style} MF"
                    _daily, _obs = append_yahoo_price_and_tr_columns(
                        _daily,
                        isin=_isin or _ticker,
                        ticker=_ticker,
                        fund_name=_name,
                        tr_levels=_tr_levels,
                        price_levels=_price_levels,
                        category=_category,
                        fee=fee_from_fund_row(_row),
                        holiday_mask=_holiday_mask,
                    )
                    if _obs <= 0:
                        _yahoo_dropped.append(_idx)
                        _yahoo_fill_rows.append(
                            {
                                "Name": _name,
                                "ISIN": _isin,
                                "ticker": _ticker,
                                "verdict": (
                                    "Drop — Yahoo Price/TR did not align to "
                                    "sheet dates"
                                ),
                                "yahoo_obs": 0,
                            }
                        )
                        print(f"drop {_ticker}: no overlap with D-Timeseries dates")
                        continue
                    _kept.at[_idx, "has_daily_total_return"] = True
                    _kept.at[_idx, "daily_tr_observations"] = int(_obs)
                    _kept.at[_idx, "daily_tr_name"] = f"{_name} - TOT RETURN IND"
                    _kept.at[_idx, "daily_tr_name_match"] = True
                    _kept.at[_idx, "daily_tr_name_source"] = "yahoo"
                    _yahoo_filled.append(_idx)
                    _yahoo_fill_rows.append(
                        {
                            "Name": _name,
                            "ISIN": _isin,
                            "ticker": _ticker,
                            "verdict": "Keep — Yahoo Price + TR series appended",
                            "yahoo_obs": int(_obs),
                        }
                    )
                    print(f"keep {_ticker}: appended Yahoo Price+TR ({_obs} obs)")

            _has_series = _kept["has_daily_total_return"].fillna(False).astype(bool)
            _dropped_no_tr = _kept.loc[~_has_series].copy()
            _kept = _kept.loc[_has_series].copy()
            _step_log = _log_buffer.getvalue() + _yahoo_log.getvalue()

            # New columns go at the end of Funds. Rows outside this step stay blank.
            timeseries_normalized = add_prefixed_columns(
                timeseries_input["normalized"],
                _funds,
                "timeseries.",
                source_columns=timeseries_input["funds"].columns,
            )
            for _src, _dst in (
                ("has_daily_total_return", "timeseries.has_daily_total_return"),
                ("daily_tr_observations", "timeseries.daily_tr_observations"),
                ("daily_tr_name", "timeseries.daily_tr_name"),
                ("daily_tr_name_match", "timeseries.daily_tr_name_match"),
                ("daily_tr_name_source", "timeseries.daily_tr_name_source"),
            ):
                if _src in _kept.columns and _dst in timeseries_normalized.columns:
                    timeseries_normalized.loc[_kept.index, _dst] = _kept[_src]
            _decision = pd.Series(
                pd.NA, index=timeseries_normalized.index, dtype="object"
            )
            _decision.loc[_kept.index] = "Keep"
            _decision.loc[_dropped_name_gap.index] = "Drop"
            _decision.loc[_dropped_no_tr.index] = "Drop"
            timeseries_normalized["timeseries.keep_or_drop"] = _decision
            timeseries_sheets = {
                **timeseries_input["sheets"],
                "Funds": timeseries_normalized,
                "No matching D-TIMESERIES NAME": timeseries_normalized.loc[
                    name_gap.index
                ],
                "Dropped D-TIMESERIES name gap": timeseries_normalized.loc[
                    _dropped_name_gap.index
                ],
                "No daily total return": timeseries_normalized.loc[
                    funds_without_timeseries.index
                ],
                "Dropped no daily total return": timeseries_normalized.loc[
                    _dropped_no_tr.index
                ],
            }
            set_timeseries(
                {
                    "funds": _kept,
                    "classified": _funds,
                    "name_gap": name_gap,
                    "name_gap_kept": _name_gap_kept,
                    "dropped_name_gap": _dropped_name_gap,
                    "missing": funds_without_timeseries,
                    "dropped_no_tr": _dropped_no_tr,
                    "yahoo_fill": pd.DataFrame(_yahoo_fill_rows),
                    "yahoo_filled_n": len(_yahoo_filled),
                    "yahoo_dropped_n": len(_yahoo_dropped),
                    "daily": _daily,
                    "normalized": timeseries_normalized,
                    "sheets": timeseries_sheets,
                    "name_gap_export": NORMALIZED_XLSX_LABEL,
                    "missing_export": NORMALIZED_XLSX_LABEL,
                    "started": len(_funds),
                    "rows": len(_daily),
                    "columns": _daily.shape[1],
                    "log": _step_log,
                }
            )
    return


@app.cell
def _(
    get_style,
    get_timeseries,
    md,
    mo,
    pd,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    style_state = get_style()
    mo.stop(
        style_state is None,
        mo.md("Run step 6 first. This step reads `funds_classified`."),
    )
    _n_start = len(style_state["funds"])
    _documentation = stack(
        selection_stats(_n_start),
        md("""
        ### What and why

        The empirical chapters need a daily total-return path for each fund in the
        cross-section. This step attaches the Datastream / Lipper daily TR column
        to each primary share class and verifies that the series name is
        consistent with the fund identity, so that later regressions are not run
        on a mismatched or missing series.

        ### How

        Operates only on `funds_classified`. Name-gap funds and funds with no
        Datastream series are both resolved here (see Decision): confirmed /
        Yahoo-backed series stay; the rest are dropped permanently.

        1. **Source.** Sheet **D-Timeseries** of the same input workbook. The
           first rows are labels (not a column header). A daily TR series is a
           column whose note is `Total return index, daily` and that has at least
           one numeric value.
        2. **Match algorithm.** Join on ISIN among the current selection. Then
           confirm the Datastream column name against the fund, in order:
           - sheet `Name`, then `openfigi_name`, then `edgar_name`;
           - shortened Datastream tokens still count as the same fund;
           - a different economic word (e.g. Value vs Equity) does **not**.
        3. **Fields added** (prefix `timeseries.` on `Funds`):
           - `has_daily_total_return` — series exists;
           - `daily_tr_observations` — number of daily points;
           - `daily_tr_name` — Datastream (or Yahoo) name;
           - `daily_tr_name_match` / `daily_tr_name_source` — whether (and which)
             of the three names confirmed the series (`yahoo` when backfilled).
        4. **Name-gap Yahoo check.** For ISIN hits whose Datastream **name** does
           not match, compare Yahoo adjusted-close daily returns to the DS
           total-return series on the overlapping window. High correlation → keep
           the fund and its DS series; no ticker or weak correlation → drop.
        5. **No Datastream TR.** Same Yahoo recipe as series-check: fetch
           split-adjusted Close (`auto_adjust=False`) into primary `{ISIN} Price` /
           `Price %`, and distribution-adjusted Close (`auto_adjust=True`) into
           `{ISIN} TR` / `TR %`. Align to sheet dates; on S&P-flat holidays set level and % to
           NA and recompute the next session’s return; other missing prints stay
           blank.
           Keep when both series align; otherwise drop.
        6. **Audit sheets.** `No daily total return`; `No matching D-TIMESERIES
           NAME`; `Dropped D-TIMESERIES name gap`; `Dropped no daily total
           return`. Frame: `funds_with_timeseries` (funds that still have a
           usable daily TR).
        """),
    )
    timeseries_result = get_timeseries()
    if timeseries_result is None:
        funds_with_timeseries = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md("_Click **Run step** to match daily total return._"),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        funds_with_timeseries = timeseries_result["funds"]
        _pre = timeseries_result.get("classified", funds_with_timeseries)
        timeseries_found = int(_pre["has_daily_total_return"].sum())
        matched_names = int(
            (
                _pre["has_daily_total_return"] & _pre["daily_tr_name_match"]
            ).sum()
        )
        dropped_name_gap = timeseries_result.get("dropped_name_gap")
        if dropped_name_gap is None:
            dropped_name_gap = _pre.iloc[0:0].copy()
        name_gap_kept = timeseries_result.get("name_gap_kept")
        if name_gap_kept is None:
            name_gap_kept = timeseries_result["name_gap"]
        dropped_no_tr = timeseries_result.get("dropped_no_tr")
        if dropped_no_tr is None:
            dropped_no_tr = _pre.iloc[0:0].copy()
        yahoo_fill = timeseries_result.get("yahoo_fill")
        if yahoo_fill is None:
            yahoo_fill = pd.DataFrame()
        _n_yahoo = int(timeseries_result.get("yahoo_filled_n") or 0)
        _n_yahoo_drop = int(timeseries_result.get("yahoo_dropped_n") or 0)
        timeseries_columns = [
            "Name",
            "openfigi_name",
            "edgar_name",
            "ISIN",
            "daily_tr_name",
            "daily_tr_observations",
            "daily_tr_name_source",
        ]
        missing_series_columns = [
            "Name",
            "ISIN",
            "CUSIP",
            "fund_type",
            "openfigi_name",
            "edgar_name",
        ]
        _drop_columns = [
            column
            for column in timeseries_columns
            if column in dropped_name_gap.columns
        ]
        _drop_no_tr_columns = [
            column
            for column in (
                "Name",
                "ISIN",
                "fund_type",
                "fund_management_style",
                "CUSIP",
            )
            if column in dropped_no_tr.columns
        ]
        _result_parts = [
            md(
                f"""
                ### Match summary

                **D-Timeseries:** {timeseries_result['rows']:,} rows,
                {timeseries_result['columns']} columns. Of the
                **{timeseries_result.get('started', len(_pre))}** funds entering
                this step, **{timeseries_found}** have a daily total-return series
                by ISIN, and **{matched_names}** of those also pass the Datastream
                name check against Name / OpenFIGI / EDGAR.

                Sheets prepared in memory (written at step 8 to
                `{timeseries_result['name_gap_export']}`): `No matching
                D-TIMESERIES NAME` ({len(timeseries_result['name_gap'])} rows),
                `Dropped D-TIMESERIES name gap` ({len(dropped_name_gap)} rows),
                `No daily total return` ({len(timeseries_result['missing'])} rows),
                `Dropped no daily total return` ({len(dropped_no_tr)} rows),
                plus `timeseries.*` on `Funds`.

                Some funds have an ISIN-linked daily total-return series, but the
                Datastream series name does not match the fund name (or OpenFIGI /
                EDGAR). Those **{len(timeseries_result['name_gap'])}** cases are
                listed below.
                """
            )
        ]
        if timeseries_result["log"].strip():
            _result_parts.append(mo.plain_text(timeseries_result["log"].strip()))
        _result_parts.extend(
            [
                review_table(
                    timeseries_result["name_gap"],
                    timeseries_columns,
                    "Series name does not match (before Yahoo decision)",
                ),
                md(
                    f"""
                    In addition, **{len(timeseries_result['missing'])}** funds have
                    no daily total-return timeseries on D-Timeseries at all
                    (**{_n_yahoo}** later filled from Yahoo Price+TR; **{_n_yahoo_drop}**
                    dropped).
                    """
                ),
                review_table(
                    timeseries_result["missing"],
                    missing_series_columns,
                    "No daily total return",
                ),
            ]
        )
        if len(yahoo_fill):
            _result_parts.append(
                review_table(
                    yahoo_fill,
                    ["Name", "ISIN", "ticker", "yahoo_obs", "verdict"],
                    "Yahoo check — funds with no Datastream TR",
                )
            )
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(*_result_parts),
            decision=stack(
                md(f"""
                ### Yahoo check on Datastream name mismatches

                For the **{len(timeseries_result['name_gap'])}** funds with an
                ISIN-linked daily TR series whose Datastream **name** failed the
                string check, Yahoo Finance adjusted close (max history) was
                compared to the Datastream total-return index on the overlapping
                window (~Nov 2015–Oct 2026): daily and monthly return correlation.

                | Fund | Ticker | DS label | Overlap | Corr daily | Corr monthly | Verdict |
                |---|---|---|---:|---:|---:|---|
                | Fidelity Advisor Series Growth & Income | — | MEGA CAP FD. | — | — | — | **Drop** — no OpenFIGI / Yahoo ticker |
                | Goldman Sachs US Equity Insights;A | GSSQX | GLDS.STRUCD.US.EQ.FD. | 2763 | 0.990 | 0.999 | **Keep** — same series |
                | MFS Blended Research Core Equity A | MUEAX | MFS UN. STD.EQ.FD. | 2763 | 0.999 | 1.000 | **Keep** — same series |
                | Sequoia Fund | SEQUX | SEQUOIA ETF | 2753 | 0.609 | 0.552 | **Drop** — weak match (ETF conversion) |
                | Jamestown Equity | JAMEX | JAMESTOWN EQ.FD. WILLIAMSBURG | 2763 | 0.998 | 1.000 | **Keep** — same series |
                | Voya U.S. Stock Index S2 | ISIPX | VOYA … SERVICE 2 | 2763 | 0.998 | 1.000 | **Keep** — same series |
                | Brown Advisory Flexible Equity;Inv | BIAFX | BROWN … FLEX.VAL. | 2763 | 0.999 | 1.000 | **Keep** — same series |
                | Eaton Vance Tax-Managed Growth 1.0 | CAPEX | EATON VANCE … CAP. EX. | 2763 | 0.996 | 0.999 | **Keep** — same series |

                **Rule.** Where Yahoo confirms the Datastream series (high
                correlation) → **keep** the fund and its timeseries. Where Yahoo
                cannot confirm (no ticker) or correlation is weak → **drop** the
                fund permanently.

                ### Yahoo check — funds with no Datastream daily total return

                For the **{len(timeseries_result['missing'])}** funds with no
                Datastream TR series at all, Yahoo Finance was queried with the
                OpenFIGI market ticker using the **same Price + TR recipe as
                series-check**: split-adjusted Close → `{{ISIN}} Price` / `Price %`;
                distribution-adjusted Close → `{{ISIN}} TR` / `TR %`; align to sheet dates;
                S&P-flat holidays NA (next-session % recomputed); blanks when Yahoo
                has no print. When both histories exist and align, they are
                appended to the working D-Timeseries panel.

                | Fund | Ticker | Yahoo Price+TR? | Span (live check) | Verdict |
                |---|---|---|---|---|
                | Johnson Disciplined Large-Cap | — | No | — | **Drop** — no OpenFIGI ticker |
                | Aberdeen US Equity II;A | — | No | — | **Drop** — no OpenFIGI ticker |
                | Franklin Rising Dividends;A | FRDPX | Yes | 1987-01-14 → 2026-11-20 | **Keep** — append Yahoo Price+TR |
                | DWS Equity 500 Index;Inst | BTIIX | Yes | 1996-06-20 → 2026-11-20 | **Keep** — append Yahoo Price+TR |
                | DWS S&P 500 Index;S | SCPIX | Yes | 1997-08-29 → 2026-11-20 | **Keep** — append Yahoo Price+TR |
                | Victory S&P 500 Index;A | MUXAX | Yes | 1992-12-07 → 2026-11-20 | **Keep** — append Yahoo Price+TR |
                | Victory MultiCap;Y | MNNYX | Yes | 1996-08-19 → 2026-11-20 | **Keep** — append Yahoo Price+TR |

                **Rule.** Yahoo Price and TR history present → fetch, append, keep.
                No ticker or missing Price/TR → drop permanently.

                ### Outcome

                - **Kept** **{len(name_gap_kept)}** name-gap funds with Yahoo confirmation
                  (Datastream abbreviations were false alarms).
                - **Dropped** **{len(dropped_name_gap)}** name-gap funds
                  (`Dropped D-TIMESERIES name gap`).
                - Yahoo-filled and kept (no Datastream TR): **{_n_yahoo}**
                - Dropped (still no series): **{len(dropped_no_tr)}**
                  (`Dropped no daily total return`).
                - Working set after this step: `funds_with_timeseries`
                  (**{len(funds_with_timeseries)}** funds).
                """),
                review_table(
                    dropped_name_gap,
                    _drop_columns,
                    "Dropped (name gap — Yahoo missing or weak match)",
                ),
                (
                    review_table(
                        dropped_no_tr,
                        _drop_no_tr_columns,
                        f"Dropped (no daily total return — {len(dropped_no_tr)})",
                    )
                    if len(dropped_no_tr)
                    else None
                ),
                selection_stats(len(funds_with_timeseries), when="end"),
            ),
        )
    _step_view
    return (funds_with_timeseries,)


@app.cell(hide_code=True)
def _(get_timeseries, mo, run_step_button, step_header):
    spxtr_ready = get_timeseries() is not None
    run_step_7b = run_step_button(
        ready=spxtr_ready,
        tooltip=None if spxtr_ready else "Run step 7 first",
    )
    step_header(
        "## 7b. Restrict Active ETFs to S&P 500 TR mandates",
        run_step_7b,
    )
    return (run_step_7b,)


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    add_prefixed_columns,
    get_timeseries,
    pd,
    run_step_7b,
    set_spxtr_screen,
):
    if run_step_7b.value:
        _ts_input = get_timeseries()
        if _ts_input is not None:
            from helpers.funds_functions.filter_active_etf_spxtr import (
                filter_active_etf_spxtr,
                load_trackinsight_objectives,
            )

            _objectives = load_trackinsight_objectives()
            _pre_funds = _ts_input["funds"]
            _kept, _dropped, _review = filter_active_etf_spxtr(
                _pre_funds,
                objectives=_objectives,
            )
            _in_scope = _review.loc[_review["spxtr_screen_in_scope"]].copy()
            _normalized = add_prefixed_columns(
                _ts_input["normalized"],
                _review,
                "spxtr.",
                source_columns=_pre_funds.columns,
                source_prefix="spxtr_",
            )
            # Keep/drop only for Active ETFs this step evaluates; others stay blank.
            _decision = pd.Series(pd.NA, index=_normalized.index, dtype="object")
            _decision.loc[_kept.index.intersection(_in_scope.index)] = "Keep"
            _decision.loc[_dropped.index] = "Drop"
            _normalized["spxtr.keep_or_drop"] = _decision
            _sheets = {
                **_ts_input["sheets"],
                "Funds": _normalized,
                "Active ETF SPXTR review": _normalized.loc[_in_scope.index],
                "Dropped Active ETF non-SPXTR": _normalized.loc[_dropped.index],
            }
            set_spxtr_screen(
                {
                    "funds": _kept.drop(
                        columns=["spxtr_screen_in_scope"],
                        errors="ignore",
                    ),
                    "dropped": _dropped,
                    "review": _in_scope,
                    "started": len(_pre_funds),
                    "in_scope": len(_in_scope),
                    "kept_active": int(_in_scope["spxtr_screen_keep"].sum()),
                    "dropped_n": len(_dropped),
                    "daily": _ts_input.get("daily"),
                    "normalized": _normalized,
                    "sheets": _sheets,
                    "export": NORMALIZED_XLSX_LABEL,
                    "objectives_n": len(_objectives),
                }
            )
    return


@app.cell
def _(
    get_spxtr_screen,
    get_timeseries,
    mo,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    timeseries_for_screen = get_timeseries()
    mo.stop(
        timeseries_for_screen is None,
        mo.md("Run step 7 first. This step reads `funds_with_timeseries`."),
    )
    _n_start_screen = len(timeseries_for_screen["funds"])
    _documentation_screen = stack(
        selection_stats(_n_start_screen),
        mo.md(r"""
        ### What and why

        The empirical chapters regress fund total returns on the S&P 500 total
        return. Active ETFs that entered the extract through a loose “mentions
        S&P 500” screen include many structured-outcome, options-income, hedged,
        and multi-asset products whose official Lipper benchmark is blank or not
        `.SPXTR`. Leaving them in the cross-section would confound Active versus
        Passive performance with product design. This step therefore restricts
        **Active ETFs** to mandates that are consistent with an S&P 500 total-return
        (or active-equity-versus-S&P-500) comparison. Passive funds and Active
        mutual funds are out of scope and are retained unchanged.

        ### Excluded Active ETF product types

        The products removed here are not ordinary active stock-selection
        vehicles that happen to cite the S&P 500. Their payoffs are reshaped by
        options, path-dependent rules, alternate weights, hedges, or other asset
        classes. Daily gaps versus S&P 500 total return are then largely a
        feature of the payoff, not evidence of Active versus Passive skill.

        **Table 7b.1 — Product types excluded from the Active ETF sample**

        | Product type | Economic design | Why it fails an S&P 500 TR comparison | Typical Lipper signal |
        |---|---|---|---|
        | Buffer / defined-outcome | Over a fixed outcome period, upside of an index (often S&P 500 **price**) is tracked up to a **cap**, while a first band of losses is absorbed (the **buffer**). Terms reset at period end. | Path and calendar of the buffer dominate returns; the reference is often price, not total return. | Frequently `.INX`; Lipper `Fund Type` often Alternatives |
        | Barrier | Payoff depends on whether the index stays above a stated **barrier**; often combined with a premium or income overlay. | Path dependence and income overlay break a one-to-one TR comparison. | Often `.INX` or blank; Alternatives |
        | Accelerator | Options seek **levered participation** in upside after thresholds (sometimes uncapped above a point). | Embedded leverage and option Greeks, not 1× equity beta to S&P 500 TR. | Alternatives; may still show `.SPXTR` |
        | Autocall | Coupon-like payoffs that may “call” (end or reset) when the index clears a trigger, with downside conditions. | Structured-note economics rather than equity total return. | Blank or non-equity; Alternatives |
        | Shield / protection | Marketing for downside cushions (puts, collars, or buffers) around S&P-linked exposure. | Hedge payoff dominates drawdowns and recovery paths. | Blank or `.SPXTR` with protection language |
        | Options / premium income | Equity (or equity beta) plus **sold options** (covered calls, puts) to harvest premium and pay distributions. | Upside truncated; income and volatility sale drive performance versus SPXTR. | Blank or `.SPXTR`; often Alternatives |
        | Hedged / VEQTOR-style | Explicit downside hedges or equity–volatility–cash mixes (e.g. Dynamic VEQTOR). | Official benchmark is not S&P 500 TR (e.g. `.SPVQDTR`); large gaps are by design. | `.SPVQDTR` or Mixed Assets / Alternatives |
        | Equal-weight income | Exposure tied to **S&P 500 Equal Weight**, often with an income overlay. | Cap-weighted `.SPXTR` is the wrong yardstick; equal weight changes sector and factor exposures. | `.SPXEW` |
        | Multi-asset / bond / tactical futures | Portfolios of Treasuries, gold, bond indices, or equity-index **futures** with tactical overlays; or sector rotation off a non-SPXTR index (e.g. Shiller CAPE sectors). | The investable “market” is not (only) S&P 500 equities. | Bond tickers (e.g. `.BCUSA`), Mixed Assets, Alternatives; sometimes `.SPXTR` with a non-SPXTR strategy |

        Mutual funds in this extract do not exhibit the same concentration of
        buffer, options-income, or VEQTOR products: retained mutual funds are
        almost entirely Lipper Equity with `Benchmark Ticker = .SPXTR`. A small
        number of mutual-fund edge cases (for example dynamic asset-allocation
        or leveraged “bull” index funds) may still warrant manual review, but
        they are not the object of this Active ETF screen.

        ### How

        Operates only on `funds_with_timeseries`. For each Active ETF the screen
        uses Lipper `fund_type`, `fund_wrapper`, `Fund Type`, `Benchmark Ticker`,
        the fund `Name`, and, when available, the Trackinsight investment
        objective from the static cache.

        1. **Scope.** Rows that are not Active ETFs receive
           `spxtr_screen_reason = out of scope` and stay in the selection.
        2. **Asset class.** Active ETFs whose Lipper `Fund Type` is not **Equity**
           are dropped (Alternatives, Mixed Assets, Bond, and similar wrappers are
           treated as non-TR equity mandates; see Table 7b.1).
        3. **Lipper benchmark.** A non-empty `Benchmark Ticker` other than
           `.SPXTR` is dropped (including `.INX`, `.SPVQDTR`, `.SPXEW`, and other
           non-TR tickers in Table 7b.1).
        4. **Product exclusions.** The concatenated name and Trackinsight
           objective are screened for the product language in Table 7b.1
           (structured-outcome / buffer / barrier / accelerator; options or
           premium-income overlays; hedged or VEQTOR-style designs; equal-weight;
           Shiller CAPE and similar non-TR strategies). A match implies a drop
           even when Lipper reports `.SPXTR`.
        5. **Inclusion.** Remaining Equity Active ETFs are kept if
           `Benchmark Ticker = .SPXTR`, or if the ticker is blank and the
           name/objective states an S&P 500 outperform, total-return, full-index
           reweight, historical-weight, or S&P 500 sector-allocation mandate.
        6. **Audit.** Every in-scope Active ETF is written to
           `Active ETF SPXTR review`; permanent drops go to
           `Dropped Active ETF non-SPXTR`. Decision columns use the prefix
           `spxtr.` on `Funds` (`spxtr.screen_keep`, `spxtr.screen_reason`,
           `spxtr.keep_or_drop`).

        ### Outputs

        Kept rows → `funds_spxtr_screen` (input to step 8). Dropped Active ETFs
        leave the working selection permanently.
        """),
    )
    spxtr_result = get_spxtr_screen()
    if spxtr_result is None:
        funds_spxtr_screen = None
        _step_view_screen = step_sections(
            documentation=_documentation_screen,
            result=mo.md(
                "_Click **Run step** to screen Active ETFs for S&P 500 TR mandates._"
            ),
            decision=stack(
                mo.md("_Decision pending until this step has run._"),
                selection_stats(_n_start_screen, when="end"),
            ),
        )
    else:
        funds_spxtr_screen = spxtr_result["funds"]
        _dropped_screen = spxtr_result["dropped"]
        _review_screen = spxtr_result["review"]
        _reason_counts = (
            _review_screen["spxtr_screen_reason"]
            .value_counts(dropna=False)
            .rename_axis("reason")
            .reset_index(name="funds")
        )
        _step_view_screen = step_sections(
            documentation=_documentation_screen,
            result=stack(
                mo.md(
                    f"- **{spxtr_result['started']}** funds entered from `funds_with_timeseries`\n"
                    f"- **{spxtr_result['in_scope']}** Active ETFs were in scope "
                    f"({spxtr_result['kept_active']} kept, "
                    f"{spxtr_result['dropped_n']} dropped)\n"
                    f"- Trackinsight objectives loaded for "
                    f"**{spxtr_result['objectives_n']}** ISINs\n"
                    f"- **{len(funds_spxtr_screen)}** funds remain for export\n"
                    f"- Sheets `Active ETF SPXTR review` and "
                    f"`Dropped Active ETF non-SPXTR` prepared in memory "
                    f"(written to `{spxtr_result['export']}` at step 8)"
                ),
                review_table(
                    _reason_counts,
                    ["reason", "funds"],
                    "Active ETF screen — reasons",
                ),
                review_table(
                    _review_screen.loc[_review_screen["spxtr_screen_keep"]],
                    [
                        "Name",
                        "ISIN",
                        "Fund Type",
                        "Benchmark Ticker",
                        "spxtr_screen_reason",
                    ],
                    f"Active ETFs kept ({spxtr_result['kept_active']})",
                ),
                (
                    review_table(
                        _dropped_screen,
                        [
                            "Name",
                            "ISIN",
                            "Fund Type",
                            "Benchmark Ticker",
                            "spxtr_screen_reason",
                        ],
                        f"Active ETFs dropped ({spxtr_result['dropped_n']})",
                    )
                    if spxtr_result["dropped_n"]
                    else None
                ),
            ),
            decision=stack(
                mo.md(
                    f"""
                    ### Decision

                    **Principle.** Only Active ETFs whose Lipper fields and
                    product description are consistent with an S&P 500
                    total-return comparison remain in the thesis sample.
                    The product types in Table 7b.1 (buffers and defined
                    outcomes, barriers, accelerators, autocalls, shield
                    designs, options or premium income, hedged or VEQTOR-style
                    overlays, equal-weight income, and multi-asset or tactical
                    non-equity strategies) are removed as **sample selection**,
                    not as data repairs: their gaps versus S&P 500 TR are
                    expected by construction.

                    **Outcome.** **{spxtr_result['dropped_n']}** Active ETFs leave
                    permanently; **{spxtr_result['kept_active']}** Active ETFs and
                    all out-of-scope rows remain. Step 8 exports
                    `funds_spxtr_screen` (**{len(funds_spxtr_screen):,}** funds).
                    """
                ),
                selection_stats(len(funds_spxtr_screen), when="end"),
            ),
        )
    _step_view_screen
    return (funds_spxtr_screen,)


@app.cell(hide_code=True)
def _(get_spxtr_screen, mo, run_step_button, step_header):
    final_ready = get_spxtr_screen() is not None
    run_step_8 = run_step_button(
        ready=final_ready,
        tooltip=None if final_ready else "Run step 7b first",
    )
    step_header("## 8. Export the final fund set and timeseries", run_step_8)
    return (run_step_8,)


@app.cell
def _(
    NORMALIZED_XLSX,
    NORMALIZED_XLSX_LABEL,
    get_spxtr_screen,
    pd,
    run_step_8,
    selected_funds,
    set_daily_series,
    set_final,
    workbook,
    write_sheets,
):
    def _arrange_final_funds(frame, original_columns):
        placed: set[str] = set()
        ordered: list[str] = []
        groups: list[str] = []

        def take(names: list[str], group: str) -> None:
            for name in names:
                if name in placed or name not in frame.columns:
                    continue
                if str(name).startswith("Unnamed"):
                    text = frame[name].astype("string").str.strip()
                    blank = text.isna() | text.eq("") | text.str.lower().eq("<na>")
                    if bool(blank.all()):
                        continue
                placed.add(name)
                ordered.append(name)
                groups.append(group)

        original = [column for column in original_columns if column in frame.columns]
        held = {
            "is_index_or_idx",
            "is_low_tracking_error",
            "is_S&P500",
            "has_timeseries",
            "has_timeseries_issue",
            "alix_fund_type",
            "fund_type",
            "fund_wrapper",
            "is_selected",
            "comment",
        }
        take(["Name", "ISIN", "CUSIP", "RIC"], "Identifiers")
        take(
            [
                "openfigi_market_id",
                "openfigi_name",
                "isin_found",
                "name_matches",
                "cusip_matches",
                "openfigi_identity_quality",
            ],
            "OpenFIGI",
        )
        take([column for column in original if column not in held], "Sheet")
        take(
            ["is_index_or_idx", "is_low_tracking_error", "is_S&P500"],
            "Sheet",
        )
        take(["has_timeseries", "has_timeseries_issue"], "Time series")
        take(
            [
                "has_daily_total_return",
                "daily_tr_name",
                "daily_tr_observations",
                "daily_tr_name_match",
                "daily_tr_name_source",
            ],
            "Time series",
        )
        take(
            [
                "alix_fund_type",
                "fund_type",
                "fund_management_style",
                "fund_management_style_source",
                "fund_management_style_detail",
                "fund_wrapper",
                "is_selected",
            ],
            "Fund type",
        )
        take(
            [
                "edgar_name",
                "edgar_name_match",
                "edgar_isin_found",
                "edgartools_cik",
                "edgar_company_name",
                "edgartools_series_id",
                "edgar_series_name",
                "edgartools_class_id",
                "edgar_class_name",
                "edgar_match_status",
                "edgar_match_note",
                "primary_rule",
            ],
            "EDGAR",
        )
        take(["comment"], "Sheet")
        take(list(frame.columns), "Other")
        arranged = frame.loc[:, ordered].reset_index(drop=True)
        return arranged, groups

    if run_step_8.value:
        final_input = get_spxtr_screen()
        if final_input is not None:
            from helpers.funds_functions.filter_daily_timeseries import (
                backfill_fees_from_funds,
                filter_daily_timeseries,
            )

            _funds_export = final_input["funds"].drop(
                columns=[
                    "spxtr_screen_keep",
                    "spxtr_screen_reason",
                    "spxtr_screen_in_scope",
                ],
                errors="ignore",
            )
            _funds_final, column_groups = _arrange_final_funds(
                _funds_export,
                list(selected_funds.columns),
            )
            _daily = final_input.get("daily")
            if _daily is None:
                _daily = pd.read_excel(
                    workbook,
                    sheet_name="D-Timeseries",
                    header=None,
                    engine="openpyxl",
                )
            _daily_timeseries_final, _roles = filter_daily_timeseries(
                _daily,
                _funds_final["ISIN"],
                (
                    _funds_final["daily_tr_name"]
                    if "daily_tr_name" in _funds_final.columns
                    else None
                ),
            )
            # Yahoo-appended series (and any Datastream blanks) inherit TER
            # from Funds final so D-Timeseries final fees are complete.
            _daily_timeseries_final, _ = backfill_fees_from_funds(
                _daily_timeseries_final,
                _funds_final,
            )
            _all_sheets = {
                **final_input["sheets"],
                "Funds final": _funds_final,
                "D-Timeseries final": _daily_timeseries_final,
            }
            series_export = write_sheets(
                _all_sheets,
                NORMALIZED_XLSX,
                no_header=("D-Timeseries final",),
            )
            set_final(
                {
                    "funds": _funds_final,
                    "groups": column_groups,
                    "sheets": _all_sheets,
                    "daily": _daily,
                    "export": NORMALIZED_XLSX_LABEL,
                }
            )
            set_daily_series(
                {
                    "frame": _daily_timeseries_final,
                    "roles": _roles,
                    "sheets": _all_sheets,
                    "export": series_export,
                    "started_columns": _daily.shape[1],
                    "started_rows": len(_daily),
                }
            )
    return


@app.cell
def _(
    get_daily_series,
    get_final,
    get_spxtr_screen,
    mo,
    pd,
    review_table,
    selection_stats,
    stack,
    step_sections,
):
    spxtr_state = get_spxtr_screen()
    mo.stop(
        spxtr_state is None,
        mo.md("Run step 7b first. This step reads `funds_spxtr_screen`."),
    )
    _n_start = len(spxtr_state["funds"])
    _documentation = stack(
        selection_stats(_n_start),
        mo.md("""
        ### What and why

        Downstream series QA and Lipper-aligned regressions need one readable
        cross-section and a timeseries panel limited to funds that survived the
        filters, including the Active-ETF S&P 500 TR screen. This step freezes
        that sample and writes the normalized workbook once.

        ### How

        Operates only on `funds_spxtr_screen`. No funds are added back from
        earlier drops; the fund count is unchanged.

        1. **Arrange** remaining funds into `Funds final` (identifiers, OpenFIGI,
           sheet fields, daily TR flags, style, EDGAR).
        2. **Filter** the working D-Timeseries panel (including Yahoo Price+TR columns
           appended in step 7) to those funds, plus index and risk-free columns.
        3. **Write** every accumulated sheet once to
           `output-data/v2-funds-normalized.xlsx` (`D-Timeseries final` with
           `no_header`). Frames: `funds_final`, `daily_timeseries_final`.
        """),
    )
    final_result = get_final()
    series_result = get_daily_series()
    if final_result is None or series_result is None:
        funds_final = None
        daily_timeseries_final = None
        _step_view = step_sections(
            documentation=_documentation,
            result=mo.md(
                "_Click **Run step** to arrange the final tables and write the Excel workbook._"
            ),
            decision=stack(
                mo.md(
                    "_No funds are removed; this step reorders columns, filters "
                    "timeseries, and writes the workbook once._"
                ),
                selection_stats(_n_start, when="end"),
            ),
        )
    else:
        funds_final = final_result["funds"]
        daily_timeseries_final = series_result["frame"]
        column_layout = pd.DataFrame(
            {"column": list(funds_final.columns), "group": final_result["groups"]}
        )
        roles = pd.Series(series_result["roles"])
        market_rows = []
        for position in roles.index[roles.isin(["index", "risk-free rate"])]:
            market_rows.append(
                {
                    "role": (
                        "Index"
                        if roles.iloc[position] == "index"
                        else "Risk-free rate"
                    ),
                    "id": daily_timeseries_final.iat[0, position],
                    "name": daily_timeseries_final.iat[1, position],
                    "note": daily_timeseries_final.iat[4, position],
                }
            )
        market_catalog = pd.DataFrame(market_rows)
        fund_columns = int(roles.eq("fund").sum())
        kept_fund_ids = daily_timeseries_final.iloc[
            0, roles.eq("fund").tolist()
        ].astype("string").str.strip().str.upper()
        kept_fund_ids = kept_fund_ids.loc[
            kept_fund_ids.notna()
            & kept_fund_ids.ne("")
            & kept_fund_ids.ne("<NA>")
        ]
        removed_columns = (
            series_result["started_columns"] - daily_timeseries_final.shape[1]
        )
        sheet_names = list(series_result.get("sheets", {}).keys())
        _step_view = step_sections(
            documentation=_documentation,
            result=stack(
                mo.md(
                    f"- **{len(funds_final)}** funds remain \n"
                    f"- **{len(funds_final.columns)}** columns in `Funds final` \n"
                    f"- **D-Timeseries:** {series_result['started_rows']:,} rows → "
                    f"**{kept_fund_ids.nunique()}** funds / **{fund_columns}** series "
                    f"columns; **{removed_columns:,}** columns removed \n"
                    f"- **{int(roles.eq('index').sum())}** index and "
                    f"**{int(roles.eq('risk-free rate').sum())}** risk-free column(s) kept \n"
                    f"- **Wrote** `{series_result['export']}` "
                    f"({len(sheet_names)} sheets: "
                    f"{', '.join(f'`{name}`' for name in sheet_names)}) \n"
                ),
                review_table(column_layout, ["group", "column"], "Column order"),
                review_table(
                    market_catalog,
                    ["role", "id", "name", "note"],
                    "Index and risk-free rate",
                ),
                review_table(
                    funds_final, list(funds_final.columns), "Final fund set"
                ),
            ),
            decision=stack(
                mo.md("""
                Keep the full daily-TR selection as `funds_final`. Filter the
                timeseries panel to those funds (plus index and risk-free rate).
                The fund count does not change. This step is the sole Excel write
                for the pipeline.
                """),
                selection_stats(len(funds_final), when="end"),
            ),
        )
    _step_view
    return daily_timeseries_final, funds_final


@app.cell(hide_code=True)
def _(mo):
    mo.md("## Conclusion")
    return


@app.cell
def _(
    NORMALIZED_XLSX_LABEL,
    funds,
    get_cusip_fill,
    get_daily_series,
    get_final,
    get_openfigi,
    get_primary,
    get_spxtr_screen,
    get_style,
    get_timeseries,
    md,
    mo,
    pd,
    review_table,
    selected_funds,
    stack,
):
    from datetime import datetime

    from helpers.funds_functions.export_funds_pipeline_pdf import (
        build_funds_v2_report,
        write_pipeline_pdf,
    )

    mo.stop(
        get_daily_series() is None or get_final() is None,
        mo.md("_Run step 8 first to write the Excel workbook and unlock the conclusion._"),
    )
    _final = get_final()["funds"]
    _series = get_daily_series()
    _openfigi = get_openfigi()
    _primary = get_primary()
    _style = get_style()
    _ts = get_timeseries()
    _spxtr = get_spxtr_screen()
    _cusip = get_cusip_fill()

    _n_loaded = len(funds)
    _n_selected = len(selected_funds)
    _n_after_openfigi = len(_openfigi["funds"]) if _openfigi else _n_selected
    _n_after_primary = len(_primary["funds"]) if _primary else _n_after_openfigi
    _n_after_style = len(_style["funds"]) if _style else _n_after_primary
    _n_after_ts = len(_ts["funds"]) if _ts else _n_after_style
    _n_final = len(_final)

    def _n_drop(state, key, default=0):
        if state is None:
            return default
        value = state.get(key)
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return int(value)
        return len(value)

    def _rows(frame) -> int | None:
        if frame is None:
            return None
        try:
            return int(len(frame))
        except TypeError:
            return None

    _drop_openfigi = _n_selected - _n_after_openfigi
    _drop_primary = _n_after_openfigi - _n_after_primary
    _drop_other = _n_after_primary - _n_after_style
    _drop_name_gap = _n_drop(_ts, "dropped_name_gap")
    _drop_no_tr = _n_drop(_ts, "dropped_no_tr")
    _drop_spxtr = int((_spxtr or {}).get("dropped_n") or (_n_after_ts - _n_final))
    _n_yahoo_fill = int((_ts or {}).get("yahoo_filled_n") or 0)

    _reclass = 0
    _confirmed = 0
    if _style is not None and "classified" in _style:
        _dec = _style["classified"]["fund_type_decision"].astype("string")
        _reclass = int(_dec.isin(["override_to_active", "override_to_passive"]).sum())
        _confirmed = int(_dec.eq("confirmed").sum())

    _cusip_filled = 0
    if _cusip is not None and _cusip.get("targets") is not None:
        _targets = _cusip["targets"]
        if "filled" in _targets.columns:
            _cusip_filled = int(_targets["filled"].fillna(False).astype(bool).sum())

    _wrapper = (
        _final["fund_wrapper"].astype("string").str.strip().str.casefold()
        if "fund_wrapper" in _final.columns
        else pd.Series("", index=_final.index, dtype="string")
    )
    _ftype = (
        _final["fund_type"].astype("string").str.strip().str.casefold()
        if "fund_type" in _final.columns
        else pd.Series("", index=_final.index, dtype="string")
    )
    _is_etf = _wrapper.eq("etf")
    _is_mf = _wrapper.isin(["mutual fund", "mutualfund", "mf"]) | (
        ~_is_etf & _wrapper.notna() & _wrapper.ne("") & _wrapper.ne("<na>")
    )
    _is_active = _ftype.eq("active")
    _is_passive = _ftype.eq("passive")
    _counts_matrix = {
        ("Active", "Mutual fund"): int((_is_active & _is_mf).sum()),
        ("Passive", "Mutual fund"): int((_is_passive & _is_mf).sum()),
        ("Active", "ETF"): int((_is_active & _is_etf).sum()),
        ("Passive", "ETF"): int((_is_passive & _is_etf).sum()),
    }
    _matrix_total = sum(_counts_matrix.values())
    _other_split = _n_final - _matrix_total

    from helpers.funds_functions.funds_pipeline_conclusion import (
        academic_closing_paragraphs,
        attrition_figure_html,
        attrition_table,
        composition_figure_html,
        contingency_table,
        reclassification_figure_html,
        verification_table,
    )

    _excel_path = str(_series.get("export") or NORMALIZED_XLSX_LABEL)
    _matrix_payload = {
        "active_mf": _counts_matrix[("Active", "Mutual fund")],
        "passive_mf": _counts_matrix[("Passive", "Mutual fund")],
        "active_etf": _counts_matrix[("Active", "ETF")],
        "passive_etf": _counts_matrix[("Passive", "ETF")],
    }
    _counts_payload = {
        "loaded": _n_loaded,
        "selected": _n_selected,
        "after_openfigi": _n_after_openfigi,
        "after_primary": _n_after_primary,
        "after_style": _n_after_style,
        "final": _n_final,
        "drop_openfigi": _drop_openfigi,
        "drop_primary": _drop_primary,
        "drop_other": _drop_other,
        "drop_name_gap": _drop_name_gap,
        "drop_no_tr": _drop_no_tr,
        "drop_spxtr": _drop_spxtr,
        "yahoo_filled": _n_yahoo_fill,
        "cusip_filled": _cusip_filled,
        "confirmed": _confirmed,
        "reclassified": _reclass,
        "after_timeseries": _n_after_ts,
    }
    _stages = [
        ("Loaded extract", _n_loaded),
        ("Selected (non-empty fund_type)", _n_selected),
        ("After OpenFIGI drop", _n_after_openfigi),
        ("After primary share class", _n_after_primary),
        ("After style Other drop", _n_after_style),
        ("After daily TR (step 7)", _n_after_ts),
        ("Final (Active ETF SPXTR screen)", _n_final),
    ]
    _attrition_tbl = attrition_table(_stages)
    _verification_tbl = verification_table(_counts_payload)
    _contingency_tbl = contingency_table(_matrix_payload, total=_n_final)
    _fig_attrition = attrition_figure_html(_stages)
    _fig_composition = composition_figure_html(_matrix_payload, total=_n_final)
    _fig_reclass = reclassification_figure_html(_counts_payload)
    _academic = academic_closing_paragraphs(
        {
            "counts": _counts_payload,
            "matrix": _matrix_payload,
            "excel_export": _excel_path,
        }
    )
    _other_note = (
        f"\n\nNote: {_other_split} fund(s) fall outside the Active/Passive × "
        "mutual-fund/ETF partition (blank or residual labels) and are excluded "
        "from Table 3 and Figure 2."
        if _other_split
        else ""
    )

    _pdf_report = build_funds_v2_report(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        excel_export=_excel_path,
        funnel=[
            ["Loaded from workbook", f"{_n_loaded:,}", "—"],
            [
                "Selected (non-empty fund_type)",
                f"{_n_selected:,}",
                f"−{_n_loaded - _n_selected:,} out of scope",
            ],
            [
                "After OpenFIGI unmatched drop (step 3)",
                f"{_n_after_openfigi:,}",
                f"−{_drop_openfigi:,} closed/merged unmatched",
            ],
            [
                "After primary share-class keep (step 5b)",
                f"{_n_after_primary:,}",
                f"−{_drop_primary:,} secondary classes",
            ],
            [
                "After fund-type Other drop (step 6)",
                f"{_n_after_style:,}",
                f"−{_drop_other:,} EDGAR Other",
            ],
            [
                "After timeseries decisions (step 7)",
                f"{_n_after_ts:,}",
                f"−{_drop_name_gap:,} name-gap; −{_drop_no_tr:,} no TR",
            ],
            [
                "After Active ETF SPXTR screen (step 7b)",
                f"{_n_final:,}",
                f"−{_drop_spxtr:,} Active ETFs without S&P 500 TR mandate",
            ],
            ["Final selection", f"{_n_final:,}", "written in step 8"],
        ],
        counts=_counts_payload,
        matrix=_matrix_payload,
        enrichments_funds=[
            f"Missing US CUSIPs filled from ISIN ({_cusip_filled} filled in step 2)",
            "OpenFIGI: market ticker, FIGI name, ISIN/CUSIP/name match flags",
            "EDGAR: CIK, series id/name, class id/name, match status",
            "One primary share class per series × wrapper (primary_rule)",
            "Management style fields (fund_management_style*) and updated working fund_type",
            "Daily TR match fields (has_daily_total_return, daily_tr_name*, observations)",
            "Active ETF S&P 500 TR screen (spxtr.screen_*)",
        ],
        enrichments_series=[
            "Datastream daily total-return columns matched by ISIN (and name-checked)",
            f"Yahoo Price+TR appended for {_n_yahoo_fill} funds",
            (
                f"Final panel filtered to remaining funds + index + risk-free "
                f"({_excel_path}: {_series['frame'].shape[1]} columns × "
                f"{_series['started_rows']:,} rows)"
            ),
        ],
        academic_conclusion=_academic,
        step_extras={
            "fund_type_groups": int(selected_funds["fund_type"].nunique())
            if "fund_type" in selected_funds.columns
            else None,
            "openfigi_unmatched_rows": _rows((_openfigi or {}).get("unmatched")),
            "dropped_class_rows": _rows((_primary or {}).get("dropped")),
            "primary_kept_rows": _n_after_primary,
            "mismatch_rows": _rows((_style or {}).get("mismatch")),
            "dropped_other_rows": _rows((_style or {}).get("dropped_other")),
            "name_gap_rows": _rows((_ts or {}).get("name_gap")),
            "missing_tr_rows": _rows((_ts or {}).get("missing")),
            "yahoo_fill_rows": _rows((_ts or {}).get("yahoo_fill")),
            "dropped_name_gap_rows": _rows((_ts or {}).get("dropped_name_gap")),
            "dropped_no_tr_rows": _rows((_ts or {}).get("dropped_no_tr")),
            "dropped_spxtr_rows": _rows((_spxtr or {}).get("dropped")),
            "column_order_rows": len(_final.columns),
            "market_rows": None,
            "step7_decision_tables": [
                {
                    "title": "Name-gap Yahoo verdicts (summary)",
                    "headers": ["Fund", "Ticker", "Verdict"],
                    "rows": [
                        ["Fidelity Advisor Series Growth & Income", "—", "Drop"],
                        ["Goldman Sachs US Equity Insights;A", "GSSQX", "Keep"],
                        ["MFS Blended Research Core Equity A", "MUEAX", "Keep"],
                        ["Sequoia Fund", "SEQUX", "Drop"],
                        ["Jamestown Equity", "JAMEX", "Keep"],
                        ["Voya U.S. Stock Index S2", "ISIPX", "Keep"],
                        ["Brown Advisory Flexible Equity;Inv", "BIAFX", "Keep"],
                        ["Eaton Vance Tax-Managed Growth 1.0", "CAPEX", "Keep"],
                    ],
                },
                {
                    "title": "No Datastream TR — Yahoo verdicts (summary)",
                    "headers": ["Fund", "Ticker", "Verdict"],
                    "rows": [
                        ["Johnson Disciplined Large-Cap", "—", "Drop"],
                        ["Aberdeen US Equity II;A", "—", "Drop"],
                        ["Franklin Rising Dividends;A", "FRDPX", "Keep"],
                        ["DWS Equity 500 Index;Inst", "BTIIX", "Keep"],
                        ["DWS S&P 500 Index;S", "SCPIX", "Keep"],
                        ["Victory S&P 500 Index;A", "MUXAX", "Keep"],
                        ["Victory MultiCap;Y", "MNNYX", "Keep"],
                    ],
                },
            ],
        },
    )
    _pdf_path = write_pipeline_pdf(
        _pdf_report,
        "output-data/v2-funds-pipeline-report.pdf",
    )

    stack(
        md(_academic),
        mo.Html(_fig_attrition),
        md("**Table 1.** Sample attrition from the Lipper/Datastream extract to the final cross-section."),
        review_table(
            _attrition_tbl,
            list(_attrition_tbl.columns),
            "Table 1 — Sample attrition",
        ),
        mo.Html(_fig_reclass),
        md("**Table 2.** Outcomes of identifier repair, Active/Passive verification, and total-return backfill."),
        review_table(
            _verification_tbl,
            list(_verification_tbl.columns),
            "Table 2 — Verification and enrichment outcomes",
        ),
        mo.Html(_fig_composition),
        md(
            f"""
            **Table 3.** Contingency of management style and distribution wrapper
            in the final sample (*n* = {_n_final:,}). Cell entries are counts with
            shares of the final sample in parentheses.
            {_other_note}
            """
        ),
        review_table(
            _contingency_tbl,
            list(_contingency_tbl.columns),
            "Table 3 — Style × wrapper",
        ),
        md(
            f"""
            ### Export artefacts

            The normalised workbook was written to `{_excel_path}`. A static PDF
            report of the full pipeline (Documentation, Result, and Decision for
            each step; interactive tables replaced by placeholders; run buttons
            omitted) was saved to `{_pdf_path}`.
            """
        ),
    )
    return


if __name__ == "__main__":
    app.run()
