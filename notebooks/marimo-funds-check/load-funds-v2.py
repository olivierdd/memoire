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
    get_style, set_style = mo.state(None)
    get_timeseries, set_timeseries = mo.state(None)
    get_daily_return, set_daily_return = mo.state(None)
    get_final, set_final = mo.state(None)
    get_daily_series, set_daily_series = mo.state(None)
    return (
        get_cusip_fill,
        get_daily_return,
        get_daily_series,
        get_edgar,
        get_final,
        get_openfigi,
        get_nport_check,
        get_style,
        get_timeseries,
        set_cusip_fill,
        set_daily_return,
        set_daily_series,
        set_edgar,
        set_final,
        set_openfigi,
        set_nport_check,
        set_style,
        set_timeseries,
    )


@app.cell
def _(mo):
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

    return (review_table,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    # Load and analyze funds (V2)

    The workbook loads immediately. Each later step that calls OpenFIGI, EDGAR, or Jev, or that writes an Excel file, waits for its button. `selected_funds` stays the sheet selection. Enrichment starts from a copy, `selected_funds_modified`. Further steps use additional copies: `funds_openfigi`, `funds_edgar`, `funds_classified`, `funds_with_timeseries`, `funds_with_daily_total_return`, `funds_final`, and `daily_timeseries_final`.
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
        "1. Load all funds",
        "2. Keep only selected funds",
        "3. Verify there are no double counts or missing data",
        "4. Match with OpenFIGI and enrich with name and market identifier",
        "5. Match with EDGAR and enrich with CIK and series",
        "6. Keep one primary share class per series",
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
    mo.md("""
    ## 1. Load the data

    Load the **Funds** sheet of `CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx` (from `input-data/`).
    Then place the selected funds in a new dataframe called `selected_funds`.
    """)
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

    from helpers.funds_functions.load_workbook import find_workbook, load_workbook
    from helpers.funds_functions.write_excel import write_excel

    def write_frame(frame, filename: str, *, header: bool = True) -> Path:
        start = Path.cwd().resolve()
        for directory in [start, *start.parents]:
            if (directory / "helpers").is_dir():
                destination = directory / "output-data"
                destination.mkdir(parents=True, exist_ok=True)
                return write_excel(frame, destination / filename, header=header)
        raise FileNotFoundError(f"Could not find helpers/, starting from {start}")

    FILENAME = "CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx"
    workbook = find_workbook(Path("input-data") / FILENAME)
    funds = load_workbook(workbook)
    selected_funds = funds.loc[
        funds["fund_type"].notna()
        & funds["fund_type"].astype("string").str.strip().ne("")
    ].copy()
    return (
        capture_prints,
        funds,
        pd,
        selected_funds,
        workbook,
        write_frame,
    )


@app.cell
def _(funds, mo, review_table, selected_funds, workbook):
    fund_type_counts = (
        selected_funds["fund_type"]
        .value_counts()
        .rename_axis("fund_type")
        .reset_index(name="funds")
    )
    mo.vstack(
        [
            mo.md(
                f"- Loaded `{workbook}` \n"
                f"- **Total number of funds:** {len(funds):,} rows, {len(funds.columns)} columns \n"
                f"- **Number of Selected funds:** {len(selected_funds):,} rows"
            ),
            review_table(
                fund_type_counts,
                ["fund_type", "funds"],
                "selected_funds by fund_type",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 2. Verify if ISIN and CUSIP are unique
    """)
    return


@app.cell
def _(mo, review_table, selected_funds):
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

    isin = _filled_identifier(selected_funds["ISIN"])
    cusip = _filled_identifier(selected_funds["CUSIP"])
    lines = []
    for column, values in (("ISIN", isin), ("CUSIP", cusip)):
        filled = values.dropna()
        repeated = filled[filled.duplicated(keep=False)]
        status = "unique" if repeated.empty else f"{repeated.nunique()} repeated values"
        lines.append(
            f"- **{column}:** {filled.nunique()} unique values among {len(filled)} "
            f"non-empty ({values.isna().sum()} missing) — {status} \n"
        )

    isin_shared = isin.notna() & isin.duplicated(keep=False)
    cusip_shared = cusip.notna() & cusip.duplicated(keep=False)
    shared_funds = selected_funds.loc[
        isin_shared | cusip_shared, ["Name", "ISIN", "CUSIP", "fund_type"]
    ].copy()
    blocks = [mo.md("\n\n".join(lines))]
    if shared_funds.empty:
        blocks.append(mo.md("- No funds share an ISIN or a CUSIP. \n"))
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
        blocks.append(mo.md(f"- **{shared_count} {shared_verb} an ISIN or a CUSIP** \n"))
        blocks.append(
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
        blocks.append(mo.md("- No funds are missing an ISIN or a CUSIP. \n"))
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
        blocks.append(
            mo.md(f"- **{missing_count} {missing_verb} missing an ISIN or a CUSIP** \n")
        )
        blocks.append(
            review_table(
                missing_funds,
                ["missing_identifier", "Name", "ISIN", "CUSIP", "fund_type"],
                "Missing ISIN or CUSIP",
            )
        )
    mo.vstack(blocks)
    return


@app.cell(hide_code=True)
def _(mo):
    fill_cusips_button = mo.ui.run_button(label="Fill missing CUSIPs from OpenFIGI")
    mo.vstack(
        [
            mo.md("""
            A US ISIN is `US`, then the 9-character CUSIP, then one check digit. For each selected fund with an empty CUSIP and a US ISIN, that middle value is sent to OpenFIGI (`ID_CUSIP`) to verify if a record is found and if the ISIN is the same.<br>
            We copy `selected_funds` into `selected_funds_modified` and enrich that copy's `CUSIP` column only when OpenFIGI confirms the match. Any other result stays blank. `selected_funds` is left unchanged. Later enrichment steps read from copies in this pipeline, not from the original selection.
            """),
            fill_cusips_button,
        ]
    ).callout(kind="warn", title="Dataset enrichment")
    return (fill_cusips_button,)


@app.cell
def _(capture_prints, fill_cusips_button, selected_funds, set_cusip_fill):
    if fill_cusips_button.value:
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
        set_cusip_fill(
            {
                "funds": _funds,
                "targets": targets,
                "message": message,
                "log": _log_buffer.getvalue(),
            }
        )
    return


@app.cell
def _(get_cusip_fill, mo, review_table):
    cusip_fill = get_cusip_fill()
    mo.stop(cusip_fill is None)
    selected_funds_modified = cusip_fill["funds"]
    cusip_targets = cusip_fill["targets"]
    cusip_blocks = [mo.md(f"**{cusip_fill['message']}**")]
    if cusip_fill["log"].strip():
        cusip_blocks.append(mo.plain_text(cusip_fill["log"].strip()))
    if not cusip_targets.empty:
        cusip_blocks.append(
            review_table(
                cusip_targets,
                ["Name", "ISIN", "CUSIP", "openfigi_ticker", "openfigi_name", "filled"],
                "CUSIP candidates",
            )
        )
    mo.vstack(cusip_blocks)
    return (selected_funds_modified,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 4. Verify selected funds and enrich dataset with OpenFIGI

    Each ISIN is sent to the OpenFIGI mapping API (`ID_ISIN`).

    - `isin_found` is true when OpenFIGI returns a record.
    - `name_matches` compares the sheet name with that record's name. OpenFIGI short forms (`LRG`, `INST`, `AMER FND`) count as the same name. A different word, such as Core versus Growth, does not.
    - Each file CUSIP is also sent to OpenFIGI (`ID_CUSIP`). `cusip_matches` is true when that lookup returns the same listing as the ISIN. The same FIGI means the same listing. A missing CUSIP, a miss, or a different listing is false.
    - The ISIN record's ticker and name are written to `openfigi_market_id` and `openfigi_name`. A different value already in either column is replaced, and the log shows an alert.

    ISIN records are cached in `cache/cache-isin-openfigi-record.json`. CUSIP listings are cached in `cache/cache-cusip-openfigi.json`.

    Funds that are not in OpenFIGI are saved as `output-data/v2-no-matching-OPENFIGI.xlsx`.
    """)
    return


@app.cell(hide_code=True)
def _(get_cusip_fill, mo):
    cusips_ready = get_cusip_fill() is not None
    verify_openfigi_button = mo.ui.run_button(
        label="Verify ISINs with OpenFIGI",
        disabled=not cusips_ready,
        tooltip=None if cusips_ready else "Fill missing CUSIPs first",
    )
    mo.vstack(
        [
            mo.md("""
            Some records have **no OpenFIGI match** and will have no market ticker and therefore no possibility to match with EDGAR.<br>
            Funds with no match are saved in `output-data/v2-no-matching-OPENFIGI.xlsx`.
            """),
            verify_openfigi_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (verify_openfigi_button,)


@app.cell
def _(
    capture_prints,
    get_cusip_fill,
    set_openfigi,
    verify_openfigi_button,
    write_frame,
):
    if verify_openfigi_button.value:
        openfigi_input = get_cusip_fill()
        if openfigi_input is not None:
            from helpers.funds_functions.check_openfigi_isin import check_openfigi_isins

            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _funds = check_openfigi_isins(openfigi_input["funds"])
            unmatched_openfigi = _funds.loc[~_funds["isin_found"]].copy()
            openfigi_export = write_frame(
                unmatched_openfigi, "v2-no-matching-OPENFIGI.xlsx"
            )
            set_openfigi(
                {
                    "funds": _funds,
                    "unmatched": unmatched_openfigi,
                    "export": openfigi_export,
                    "log": _log_buffer.getvalue(),
                }
            )
    return


@app.cell
def _(get_cusip_fill, get_openfigi, mo, review_table):
    openfigi_result = get_openfigi()
    mo.stop(
        openfigi_result is None,
        None
        if get_cusip_fill() is not None
        else mo.md(
            "Fill missing CUSIPs first. This step reads `selected_funds_modified`."
        ),
    )
    funds_openfigi = openfigi_result["funds"]
    openfigi_columns = [
        "Name",
        "openfigi_name",
        "ISIN",
        "isin_found",
        "name_matches",
        "CUSIP",
        "cusip_matches",
    ]
    openfigi_found = int(funds_openfigi["isin_found"].sum())
    openfigi_name_matches = int(funds_openfigi["name_matches"].sum())
    openfigi_cusip_matches = int(funds_openfigi["cusip_matches"].sum())
    openfigi_blocks = [
        mo.md(
            f"- **{openfigi_found}** of {len(funds_openfigi)} ISINs found in OpenFIGI \n"
            f"- **{openfigi_name_matches}** of {len(funds_openfigi)} names match the OpenFIGI record \n"
            f"- **{openfigi_cusip_matches}** of {len(funds_openfigi)} CUSIPs return the same OpenFIGI record as the ISIN \n"
            f"- For non matching rows : wrote {len(openfigi_result['unmatched'])} rows to `{openfigi_result['export']}`\n"
            f"- The selected funds dataset has been enriched with OpenFIGI data in the output dataset `funds_openfigi`.\n"
        )
    ]
    openfigi_blocks.append(
        review_table(funds_openfigi, openfigi_columns, "OpenFIGI check")
    )
    openfigi_blocks.append(
        review_table(
            openfigi_result["unmatched"],
            openfigi_columns,
            "No OpenFIGI match",
        )
    )
    mo.vstack(openfigi_blocks)
    return (funds_openfigi,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 5. Verify and enrich ISINs with EDGAR

    The SEC fund reference is keyed by ticker. Each ISIN is resolved with its OpenFIGI ticker, then looked up in that reference. The CUSIP resolves to the same ticker, so it is not looked up separately.

    - `edgar_isin_found` is true when the ISIN's ticker has an EDGAR record.
    - `edgar_name` is that row's series name and share class. It is empty when the ISIN does not match.
    - `edgar_name_match` compares the sheet name with `edgar_name`. Short forms count as the same name, and a different word such as Core versus Growth does not. It is false when `edgar_name` is empty.
    - `edgartools_cik` is the registrant. One CIK is the investment company.
    - `edgar_company_name` is that registrant's name.
    - `edgartools_series_id` is the series inside the registrant.
    - `edgar_series_name` is that series name.
    - `edgartools_class_id` is the share class inside the series.
    - `edgar_class_name` is that share class name.

    The CIK, series, and share class fields come from the ISIN's EDGAR row. They are empty when the ISIN does not match.
    """)
    return


@app.cell(hide_code=True)
def _(get_openfigi, mo):
    openfigi_ready = get_openfigi() is not None
    match_edgar_button = mo.ui.run_button(
        label="Match EDGAR identifiers",
        disabled=not openfigi_ready,
        tooltip=None if openfigi_ready else "Verify ISINs with OpenFIGI first",
    )
    mo.vstack(
        [
            mo.md("""
            Some records have **no EDGAR match** and will not be enriched.<br>
            Funds with no match are saved in `output-data/v2-no-matching-EDGAR.xlsx`.
            """),
            match_edgar_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (match_edgar_button,)


@app.cell
def _(
    capture_prints,
    get_openfigi,
    match_edgar_button,
    set_edgar,
    write_frame,
):
    if match_edgar_button.value:
        edgar_input = get_openfigi()
        if edgar_input is not None:
            from helpers.funds_functions.match_edgar_identifiers import (
                match_edgar_identifiers,
            )

            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _funds = match_edgar_identifiers(edgar_input["funds"])
            unmatched_edgar = _funds.loc[~_funds["edgar_isin_found"]].copy()
            edgar_export = write_frame(unmatched_edgar, "v2-no-matching-EDGAR.xlsx")
            set_edgar(
                {
                    "funds": _funds,
                    "unmatched": unmatched_edgar,
                    "export": edgar_export,
                    "log": _log_buffer.getvalue(),
                }
            )
    return


@app.cell
def _(get_edgar, get_openfigi, mo, review_table):
    edgar_result = get_edgar()
    mo.stop(
        edgar_result is None,
        None
        if get_openfigi() is not None
        else mo.md(
            "Verify ISINs with OpenFIGI first. This step reads `funds_openfigi`."
        ),
    )
    funds_edgar = edgar_result["funds"]
    edgar_columns = [
        "Name",
        "edgar_name",
        "openfigi_name",
        "edgar_name_match",
        "ISIN",
        "edgar_isin_found",
        "edgar_match_status",
        "edgar_match_note",
        "CUSIP",
    ]
    edgar_matches = int(funds_edgar["edgar_isin_found"].sum())
    edgar_name_matches = int(
        funds_edgar.loc[funds_edgar["edgar_isin_found"], "edgar_name_match"].sum()
    )
    edgar_blocks = [
        mo.md(
            f"- **{edgar_matches}** of {len(funds_edgar)} ISINs match an EDGAR record \n"
            f"- **{edgar_name_matches}** of {edgar_matches} EDGAR names match the sheet \n"
            f"- For non matching rows : wrote {len(edgar_result['unmatched'])} rows to `{edgar_result['export']}` \n"
            f"- The selected funds dataset has been enriched with EDGAR data in the output dataset `funds_edgar`. \n"
        )
    ]
    edgar_blocks.append(review_table(funds_edgar, edgar_columns, "EDGAR check"))
    edgar_blocks.append(
        review_table(edgar_result["unmatched"], edgar_columns, "No EDGAR match")
    )
    mo.vstack(edgar_blocks)
    return (funds_edgar,)


@app.cell
def _(funds_edgar, mo, review_table):
    from helpers.funds_functions.edgar_unmatched_corrections import (
        STATUS_CLOSED,
        STATUS_NAME,
        STATUS_UNMATCHABLE,
        correction_review,
    )

    edgar_correction_review = correction_review(funds_edgar)
    name_review = edgar_correction_review.loc[
        edgar_correction_review["category"].eq(STATUS_NAME)
    ]
    closed_review = edgar_correction_review.loc[
        edgar_correction_review["category"].eq(STATUS_CLOSED)
    ]
    unmatchable_review = edgar_correction_review.loc[
        edgar_correction_review["category"].eq(STATUS_UNMATCHABLE)
    ]
    correction_columns = ["applied", "Name", "ISIN", "openfigi_market_id", "detail"]
    match_status = (
        funds_edgar["edgar_match_status"] if "edgar_match_status" in funds_edgar.columns else None
    )
    if match_status is not None and match_status.eq(STATUS_NAME).any():
        applied_note = (
            f"Corrections are in `funds_edgar`: **{int(match_status.eq(STATUS_NAME).sum())}** matched by name, "
            f"**{int(match_status.eq(STATUS_CLOSED).sum())}** closed, "
            f"**{int(match_status.eq(STATUS_UNMATCHABLE).sum())}** without a series row."
        )
    else:
        applied_note = "The corrections are not in `funds_edgar` yet."
    corrections_applied = match_status is not None and bool(match_status.eq(STATUS_NAME).any())
    apply_edgar_corrections_button = mo.ui.run_button(
        label="Enrich the dataset with these corrections",
        disabled=corrections_applied,
        tooltip="Already applied" if corrections_applied else None,
    )
    mo.vstack(
        [
            mo.md(
                f"""
                The 43 funds are US funds. The ticker join missed them for three different reasons. All 43 stay in the selected set.

                {applied_note}
                """
            ),
            mo.md(
                f"""
                **Case 1: Match by name, and keep ({len(name_review)})**

                - These funds are already in the SEC file. The row has the series and the share class, and its ticker cell is blank.
                - Section 5 looks up the OpenFIGI ticker in that cell. A blank cell is reported as no match.
                - The correction matches the fund name on the sheet to the SEC series and share class. It does not use the ticker. The class id from that name match is what gets stored.
                - Two funds are not taken from the OpenFIGI name. Invesco Main Street All Cap Fund;Y is class Y on the sheet and in the SEC file; OpenFIGI calls it class A. HAWG is the HCM Hedged Equity ETF; the SEC ticker list currently gives HAWG to Tradr 2X Long HAWK, so the HCM series is the one stored.

                Some of the 43 share classes belong to the same fund series.

                - iShares S&P 500 Index Fund, S000004272: Service, G, Investor A
                - Invesco Main Street All Cap Fund, S000064631: Y, R, A
                - Invesco Main Street Fund, S000064632: Y, A, R, R6, C
                - Invesco Rising Dividends Fund, S000064633: A, C, R
                """
            ),
            review_table(name_review, correction_columns, "Match by name"),
            mo.md(
                f"""
                **Case 2: Closed, and keep ({len(closed_review)})**

                These series left the current SEC file after a merger or liquidation. They stay in the performance sample so the funds that disappeared remain in the history. Their EDGAR identifiers stay empty. The survivor's series is not copied onto the dead fund.
                """
            ),
            review_table(closed_review, correction_columns, "Closed"),
            mo.md(
                f"""
                **Case 3: Cannot match ({len(unmatchable_review)})**

                These stay in the selected set. The series-and-class file has no row to attach, so the identifiers stay empty and the N-CEN classification does not run.

                SPY and the Voya Corporate Leaders Trust are unit investment trusts. A unit investment trust holds a fixed portfolio, with no manager buying and selling over time. It files on EDGAR as its own trust, without the series and share class row used for open-end funds.
                """
            ),
            review_table(unmatchable_review, correction_columns, "Cannot match"),
            mo.vstack(
                [
                    mo.md("""
                    These corrections are written into `funds_edgar`. Closed funds and funds with no series row stay in the selected set.
                    """),
                    apply_edgar_corrections_button,
                ]
            ).callout(kind="warn", title="Dataset enrichment"),
        ]
    )
    return (apply_edgar_corrections_button,)


@app.cell
def _(
    apply_edgar_corrections_button,
    capture_prints,
    get_edgar,
    set_edgar,
    write_frame,
):
    if apply_edgar_corrections_button.value:
        current_edgar = get_edgar()
        if current_edgar is not None and not current_edgar.get("corrections_applied"):
            from helpers.funds_functions.edgar_unmatched_corrections import (
                apply_edgar_unmatched_corrections,
            )
            from helpers.funds_functions.map_edgar_tickers import (
                load_all_fund_reference_data,
            )

            correction_log, correction_redirect = capture_prints()
            with correction_redirect:
                enriched_edgar = apply_edgar_unmatched_corrections(
                    current_edgar["funds"],
                    load_all_fund_reference_data(),
                )
            still_unmatched = ~enriched_edgar["edgar_isin_found"].astype(bool)
            remaining_unmatched = enriched_edgar.loc[still_unmatched].copy()
            correction_export = write_frame(remaining_unmatched, "v2-no-matching-EDGAR.xlsx")
            previous_log = current_edgar.get("log") or ""
            set_edgar(
                {
                    "funds": enriched_edgar,
                    "unmatched": remaining_unmatched,
                    "export": correction_export,
                    "log": previous_log + correction_log.getvalue(),
                    "corrections_applied": True,
                }
            )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 6. Verify if some funds belong to the same series

    Funds are filed in EDGAR as a registrant (CIK), then a series, then a share class. One CIK is the investment company. It can offer several series, and each series can offer several share classes of the same portfolio.

    The selected funds are all supposed to be primary share classes: the main share class among many. Therefore we don't expect to see rows in our table that belong to the same CIK and series.

    The series and class identifiers come from the SEC fund-reference table. The latest N-PORT for that series is a separate filing and the check that the grouping is the one the registrant reported. `genInfo/seriesId` must equal `edgartools_series_id`. `edgartools_class_id` must appear on a `monthlyTotReturn` of that filing. The filing has one `invstOrSec` holdings list for the series. `nport_same_series` is `confirmed` with the report date when both hold. A class missing from that month is checked on the previous N-PORT.

    `AUM` is the sheet column Fund Total Assets under Management. It is the Lipper figure for that row, so two classes of one series can differ. A blank cell means Lipper did not report a figure for that share class.
    """)
    return


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


@app.cell(hide_code=True)
def _(get_edgar, mo):
    nport_ready = get_edgar() is not None
    confirm_nport_button = mo.ui.run_button(
        label="Confirm classes on N-PORT",
        disabled=not nport_ready,
        tooltip=None if nport_ready else "Match EDGAR identifiers first",
    )
    mo.vstack(
        [
            mo.md("""
            **Some records share classes belonging to the same fund series.**<br>
            The table writes them to `output-data/v2-common-fund-series.xlsx`. **Confirm classes on N-PORT** fills `nport_same_series` and writes the file again.
            """),
            confirm_nport_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (confirm_nport_button,)


@app.cell
def _(
    capture_prints,
    confirm_nport_button,
    get_edgar,
    series_groups,
    set_nport_check,
):
    if confirm_nport_button.value:
        nport_input = get_edgar()
        if nport_input is not None:
            from helpers.funds_functions.confirm_nport_series_classes import (
                add_nport_same_series,
            )

            _missing_class_id, _same_cik_series = series_groups(nport_input["funds"])
            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _checked = add_nport_same_series(_same_cik_series)
            set_nport_check({"funds": _checked, "log": _log_buffer.getvalue()})
    return


@app.cell
def _(get_edgar, get_nport_check, mo, review_table, series_groups, write_frame):
    series_input = get_edgar()
    mo.stop(
        series_input is None,
        mo.md("Match EDGAR identifiers first. This step reads `funds_edgar`."),
    )
    missing_class_id, same_cik_series = series_groups(series_input["funds"])
    nport_check = get_nport_check()
    same_cik_series = same_cik_series.copy()
    if nport_check is None:
        same_cik_series["nport_same_series"] = "not checked"
    else:
        same_cik_series["nport_same_series"] = (
            nport_check["funds"]["nport_same_series"]
            .reindex(same_cik_series.index)
            .fillna("not checked")
        )
    same_cik_series["AUM"] = same_cik_series["Fund Total Assets under Management"]
    class_count = len(missing_class_id)
    class_verb = "fund has" if class_count == 1 else "funds have"
    series_count = len(same_cik_series)
    series_verb = "fund shares" if series_count == 1 else "funds share"
    confirmed_count = int(
        same_cik_series["nport_same_series"].astype("string").str.startswith("confirmed").sum()
    )
    nport_note = (
        "Click **Confirm classes on N-PORT** to fill `nport_same_series`."
        if confirmed_count == 0
        and same_cik_series["nport_same_series"].eq("not checked").all()
        else f"**{confirmed_count}** of {series_count} classes are confirmed on the series N-PORT."
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
    share_class_export = write_frame(
        missing_class_id, "v2-no-matching-EDGAR_SHARE_CLASS.xlsx"
    )
    common_series_export = write_frame(
        same_cik_series.loc[:, series_columns], "v2-common-fund-series.xlsx"
    )
    series_blocks = [
        mo.md(
            f"- **{class_count} {class_verb} no EDGAR share class id** \n"
            f"- Wrote {class_count} rows to `{share_class_export}` \n"
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
            f"- Wrote {series_count} rows to `{common_series_export}` \n"
            f"- {nport_note} \n"
        ),
        review_table(same_cik_series, series_columns, "Same CIK and series"),
    ]
    mo.vstack(series_blocks)
    return missing_class_id, same_cik_series


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 6b. Keep the primary share class

    One series is one portfolio. Where the selected funds include more than one class of that series, one class stays and the others are removed. A fund that is the only selected class of its series stays. A fund with no series id stays, because it is not a second class of a known series.

    The class that stays is the primary class:

    1. The class with the largest `AUM`, when at least one class in the series has a figure. A blank AUM is ignored, not treated as zero.
    2. When no class has an AUM, or the largest AUM is shared, the EDGAR class name decides. The first match wins: the class name is the series name and does not say Advisor; then Investor or Ordinary; then Gabelli Class AAA; then Class A, other than a 529 class; then Admiral; then Institutional or Class I; then Class Y; then any other class.
    3. If the name still ties, the smallest `edgartools_class_id` stays.

    `primary_rule` records which of those three steps decided. Later steps read this filtered set.
    """)
    return


@app.cell
def _(get_edgar, mo, review_table, write_frame):
    primary_input = get_edgar()
    mo.stop(
        primary_input is None,
        mo.md("Match EDGAR identifiers first. This step reads `funds_edgar`."),
    )
    from helpers.funds_functions.select_primary_share_class import (
        select_primary_share_class,
    )

    funds_primary, dropped_classes = select_primary_share_class(primary_input["funds"])
    collapsed = dropped_classes["edgartools_series_id"].nunique() if len(dropped_classes) else 0
    primary_from_series = funds_primary.loc[
        funds_primary["edgartools_series_id"].isin(dropped_classes["edgartools_series_id"])
    ].copy()
    primary_from_series["AUM"] = primary_from_series["Fund Total Assets under Management"]
    primary_columns = [
        "edgartools_cik",
        "edgar_company_name",
        "edgartools_series_id",
        "edgar_series_name",
        "edgartools_class_id",
        "edgar_class_name",
        "Name",
        "ISIN",
        "AUM",
        "primary_rule",
    ]
    primary_export = write_frame(
        primary_from_series.loc[:, primary_columns],
        "v2-primary-share-class.xlsx",
    )
    dropped_export = write_frame(dropped_classes, "v2-dropped-share-classes.xlsx")
    mo.vstack(
        [
            mo.md(
                f"- **{len(primary_input['funds'])}** funds went in \n"
                f"- **{len(dropped_classes)}** share classes were removed from **{collapsed}** series \n"
                f"- **{len(funds_primary)}** funds remain, one class per series \n"
                f"- Wrote {len(primary_from_series)} primary classes to `{primary_export}` \n"
                f"- Wrote {len(dropped_classes)} removed classes to `{dropped_export}` \n"
            ),
            review_table(primary_from_series, primary_columns, "Primary share class"),
        ]
    )
    return (funds_primary,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 7. Verify fund type (active vs passive)

    Each fund is classified at the EDGAR series: one registrant (CIK) and one series id. Share classes of that series receive the same label. The label is Passive, Active, Other, or Unknown. The first source that decides wins.

    1. The latest N-CEN filing for the CIK. The questionnaire for `edgartools_series_id` is read from the filing XML.
       - `indexFundInfo` with fund type Index Fund means Passive. That block is the SEC census flag that the series tracks an index.
       - A fund type of Target Date Fund, Fund of Funds, or Interval Fund, with no `indexFundInfo`, means Other.
       - Another fund type, including Exchange-Traded Fund, with no `indexFundInfo`, means Active. An ETF is a wrapper. The SEC adds `indexFundInfo` when that series is an index fund.
       - A fund type of N/A, or a series id absent from that filing, moves to the next source.
    2. When N-CEN does not decide, Jev (`jev-latest`) reads the prospectus and chooses Passive, Active, or Other.
       - The text is the whole 497K investment objective for that series.
       - When the 497K has no objective, the text is the investment-objective section and the principal-strategy section of the latest 485BPOS or 485APOS. The table of contents is left out.
       - Passive means the fund's job is to track, match, or approximate an index.
       - Active means a manager selects securities. An index named only as a comparison, or as a list of stocks the manager may buy, does not make the fund passive.
       - Other means a target-date fund, a fund of funds, or an interval fund.
       - A choice with confidence below 0.60 stays Unknown.
    3. A row with no CIK or no series id is Unknown and is not sent to EDGAR. A series with no prospectus text is Unknown and is not sent to Jev.

    The parsed N-CEN field `fund_type` is left unused: edgartools copies a single `fundType` tag and drops `indexFundInfo`. Portfolio turnover and the word Index in the fund name are left unused.
    """)
    return


@app.cell(hide_code=True)
def _(get_edgar, mo):
    style_ready = get_edgar() is not None
    classify_style_button = mo.ui.run_button(
        label="Classify fund type",
        disabled=not style_ready,
        tooltip=None if style_ready else "Match EDGAR identifiers first",
    )
    mo.vstack(
        [
            mo.md("""
            **Some funds have an invalidated fund type.**<br>
            Funds whose sheet fund type does not match the classified fund type are saved in `output-data/v2-fund-type-mismatch.xlsx`.
            """),
            classify_style_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (classify_style_button,)


@app.cell
def _(
    capture_prints,
    classify_style_button,
    funds_primary,
    set_style,
    write_frame,
):
    if classify_style_button.value:
        if funds_primary is not None:
            from helpers.funds_functions.classify_fund_management_style import (
                classify_fund_management_style,
            )

            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _funds = classify_fund_management_style(funds_primary)

            def _type_label(series):
                values = series.astype("string").str.strip()
                blank = values.isna() | values.eq("") | values.str.lower().eq("<na>")
                return values.mask(blank)

            sheet_type = _type_label(_funds["fund_type"])
            edgar_type = _type_label(_funds["fund_management_style"])
            fund_type_mismatch = _funds.loc[
                sheet_type.fillna("").str.casefold().ne(
                    edgar_type.fillna("").str.casefold()
                )
            ].copy()
            fund_type_export = write_frame(
                fund_type_mismatch, "v2-fund-type-mismatch.xlsx"
            )
            set_style(
                {
                    "funds": _funds,
                    "mismatch": fund_type_mismatch,
                    "export": fund_type_export,
                    "log": _log_buffer.getvalue(),
                }
            )
    return


@app.cell
def _(get_edgar, get_style, mo, review_table):
    style_result = get_style()
    mo.stop(
        style_result is None,
        None
        if get_edgar() is not None
        else mo.md(
            "Match EDGAR identifiers first. This step reads the primary share class."
        ),
    )
    funds_classified = style_result["funds"]
    style = funds_classified["fund_management_style"].astype("string")
    source = funds_classified["fund_management_style_source"].astype("string")
    detail = funds_classified["fund_management_style_detail"].astype("string").fillna("")
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
    mismatch_columns = [
        "Name",
        "ISIN",
        "fund_type",
        "fund_management_style",
        "fund_management_style_source",
        "fund_management_style_detail",
    ]
    style_blocks = [
        mo.md(
            f"- **{active}** Active, **{passive}** Passive, **{other}** Other, **{unknown}** Unknown \n"
            f"- **{from_ncen}** took the label from the latest N-CEN filing \n"
            f"- **{from_jev}** took the label from Jev, because N-CEN did not decide \n"
            f"- **{no_series}** have no CIK or series id. They stay Unknown and are not sent to EDGAR \n"
            f"- **{no_prospectus}** stayed Unknown because N-CEN did not decide and the prospectus had no usable text \n"
            f"- **{low_confidence}** stayed Unknown because Jev's choice was below 0.60 confidence \n"
            f"- **{len(style_result['mismatch'])}** funds have a sheet fund type that does not match the classified type \n"
            f"- Wrote {len(style_result['mismatch'])} rows to `{style_result['export']}` \n"
        ),
    ]
    style_blocks.append(
        review_table(style_counts, ["fund_management_style", "funds"], "Classified fund type")
    )
    style_blocks.append(
        review_table(style_result["mismatch"], mismatch_columns, "Fund type mismatch")
    )
    mo.vstack(style_blocks)
    return (funds_classified,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 8. Verify if there is a time series

    Load the **D-Timeseries** sheet of the same workbook. The first rows are labels, not a column header. A daily total return series is a column whose note is `Total return index, daily` and that has at least one value.

    Each selected fund is matched on ISIN. The Datastream name on that column is then checked against the fund. The sheet name is used first. When that name does not confirm the series, the OpenFIGI name is used, then the EDGAR name. A shortened Datastream name still counts as the same fund. A different word, such as Value versus Equity, does not.

    `has_daily_total_return` is true when the series exists. `daily_tr_observations` is the number of daily points. `daily_tr_name` is the Datastream name. `daily_tr_name_match` is true when one of the three names confirms it, and `daily_tr_name_source` is the name that did.
    """)
    return


@app.cell(hide_code=True)
def _(get_style, mo):
    timeseries_ready = get_style() is not None
    match_timeseries_button = mo.ui.run_button(
        label="Match daily total return",
        disabled=not timeseries_ready,
        tooltip=None if timeseries_ready else "Classify fund type first",
    )
    mo.vstack(
        [
            mo.md("""
            Some funds have **no daily total return**, or the series name does not match.<br>
            Funds with no series are saved in `output-data/v2-no-daily-total-return.xlsx`. Funds whose series name does not match are saved in `output-data/v2-no-matching-D-TIMESERIES-NAME.xlsx`.
            """),
            match_timeseries_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (match_timeseries_button,)


@app.cell
def _(
    capture_prints,
    get_style,
    match_timeseries_button,
    pd,
    set_timeseries,
    workbook,
    write_frame,
):
    if match_timeseries_button.value:
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
            ]
            funds_without_timeseries = _funds.loc[~_funds["has_daily_total_return"]].copy()
            name_gap_export = write_frame(
                name_gap, "v2-no-matching-D-TIMESERIES-NAME.xlsx"
            )
            missing_timeseries_export = write_frame(
                funds_without_timeseries, "v2-no-daily-total-return.xlsx"
            )
            set_timeseries(
                {
                    "funds": _funds,
                    "name_gap": name_gap,
                    "missing": funds_without_timeseries,
                    "name_gap_export": name_gap_export,
                    "missing_export": missing_timeseries_export,
                    "rows": len(daily_timeseries),
                    "columns": daily_timeseries.shape[1],
                    "log": _log_buffer.getvalue(),
                }
            )
    return


@app.cell
def _(get_style, get_timeseries, mo, review_table):
    timeseries_result = get_timeseries()
    mo.stop(
        timeseries_result is None,
        None
        if get_style() is not None
        else mo.md(
            "Classify fund type first. This step reads `funds_classified`."
        ),
    )
    funds_with_timeseries = timeseries_result["funds"]
    timeseries_found = int(funds_with_timeseries["has_daily_total_return"].sum())
    matched_names = int(
        (
            funds_with_timeseries["has_daily_total_return"]
            & funds_with_timeseries["daily_tr_name_match"]
        ).sum()
    )
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
    timeseries_blocks = [
        mo.md(
            f"- **D-Timeseries:** {timeseries_result['rows']:,} rows, {timeseries_result['columns']} columns \n"
            f"- **{timeseries_found}** of {len(funds_with_timeseries)} funds have a daily total return series \n"
            f"- **{matched_names}** of {timeseries_found} series names match Name, OpenFIGI, or EDGAR \n"
            f"- Wrote {len(timeseries_result['name_gap'])} rows to `{timeseries_result['name_gap_export']}` \n"
            f"- Wrote {len(timeseries_result['missing'])} rows to `{timeseries_result['missing_export']}` \n"
        )
    ]
    if timeseries_result["log"].strip():
        timeseries_blocks.append(mo.plain_text(timeseries_result["log"].strip()))
    timeseries_blocks.append(
        review_table(
            timeseries_result["name_gap"],
            timeseries_columns,
            "Series name does not match",
        )
    )
    timeseries_blocks.append(
        review_table(
            timeseries_result["missing"],
            missing_series_columns,
            "No daily total return",
        )
    )
    mo.vstack(timeseries_blocks)
    return (funds_with_timeseries,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 9. Keep funds with a daily total return

    Funds with no daily total return series are removed. A fund whose series name does not match stays, because the series itself is present. The kept funds are `funds_with_daily_total_return`.
    """)
    return


@app.cell(hide_code=True)
def _(get_timeseries, mo):
    daily_return_ready = get_timeseries() is not None
    drop_missing_timeseries_button = mo.ui.run_button(
        label="Drop funds with no daily total return",
        disabled=not daily_return_ready,
        tooltip=None if daily_return_ready else "Match daily total return first",
    )
    mo.vstack(
        [
            mo.md("""
            Funds with **no daily total return** are removed from the set.

            The kept funds are saved in `output-data/v2-funds-with-daily-total-return.xlsx`.
            """),
            drop_missing_timeseries_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (drop_missing_timeseries_button,)


@app.cell
def _(
    drop_missing_timeseries_button,
    get_timeseries,
    set_daily_return,
    write_frame,
):
    if drop_missing_timeseries_button.value:
        daily_return_input = get_timeseries()
        if daily_return_input is not None:
            _funds = daily_return_input["funds"]
            has_series = _funds["has_daily_total_return"].fillna(False).astype(bool)
            kept = _funds.loc[has_series].copy()
            kept_export = write_frame(kept, "v2-funds-with-daily-total-return.xlsx")
            set_daily_return(
                {
                    "funds": kept,
                    "started": len(_funds),
                    "dropped": int((~has_series).sum()),
                    "export": kept_export,
                }
            )
    return


@app.cell
def _(get_daily_return, get_timeseries, mo, review_table):
    daily_return = get_daily_return()
    mo.stop(
        daily_return is None,
        None
        if get_timeseries() is not None
        else mo.md(
            "Match daily total return first. This step reads `funds_with_timeseries`."
        ),
    )
    funds_with_daily_total_return = daily_return["funds"]
    kept_columns = [
        "Name",
        "ISIN",
        "fund_type",
        "fund_management_style",
        "daily_tr_name",
        "daily_tr_observations",
        "daily_tr_name_source",
    ]
    mo.vstack(
        [
            mo.md(
                f"- **{daily_return['started']}** funds went in \n"
                f"- **{daily_return['dropped']}** funds with no daily total return were removed \n"
                f"- **{len(funds_with_daily_total_return)}** funds remain \n"
                f"- Wrote {len(funds_with_daily_total_return)} rows to `{daily_return['export']}` \n"
            ),
            review_table(
                funds_with_daily_total_return,
                kept_columns,
                "Funds with a daily total return",
            ),
        ]
    )
    return (funds_with_daily_total_return,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 10. Save the final fund set

    `funds_final` is the remaining funds, with the columns put in reading order.

    - The name and the identifiers come first, with the OpenFIGI ticker and name beside them.
    - The sheet's description and performance columns follow, in their original order. Empty columns that Excel imported without a name are left out.
    - The sheet's time-series flags are followed by the daily total return columns.
    - `fund_type` is followed by the classified fund type.
    - The EDGAR registrant, series, and share class come last, with `primary_rule`.
    """)
    return


@app.cell(hide_code=True)
def _(get_daily_return, mo):
    final_ready = get_daily_return() is not None
    write_final_button = mo.ui.run_button(
        label="Write the final fund file",
        disabled=not final_ready,
        tooltip=None if final_ready else "Drop funds with no daily total return first",
    )
    mo.vstack(
        [
            mo.md("""
            This writes the cleaned fund set to `output-data/v2-funds-final.xlsx`.
            """),
            write_final_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (write_final_button,)


@app.cell
def _(
    get_daily_return,
    selected_funds,
    set_final,
    write_final_button,
    write_frame,
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

    if write_final_button.value:
        final_input = get_daily_return()
        if final_input is not None:
            _funds_final, column_groups = _arrange_final_funds(
                final_input["funds"],
                list(selected_funds.columns),
            )
            final_export = write_frame(_funds_final, "v2-funds-final.xlsx")
            set_final(
                {
                    "funds": _funds_final,
                    "groups": column_groups,
                    "export": final_export,
                }
            )
    return


@app.cell
def _(get_daily_return, get_final, mo, pd, review_table):
    final_result = get_final()
    mo.stop(
        final_result is None,
        None
        if get_daily_return() is not None
        else mo.md(
            "Drop funds with no daily total return first. This step reads `funds_with_daily_total_return`."
        ),
    )
    funds_final = final_result["funds"]
    column_layout = pd.DataFrame(
        {"column": list(funds_final.columns), "group": final_result["groups"]}
    )
    mo.vstack(
        [
            mo.md(
                f"- **{len(funds_final)}** funds remain \n"
                f"- **{len(funds_final.columns)}** columns, sheet columns first and the added columns beside the field they describe \n"
                f"- Wrote {len(funds_final)} rows to `{final_result['export']}` \n"
            ),
            review_table(column_layout, ["group", "column"], "Column order"),
            review_table(funds_final, list(funds_final.columns), "Final fund set"),
        ]
    )
    return (funds_final,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## 11. Keep the time series of the remaining funds

    The **D-Timeseries** sheet has one column for each series. A fund has its total return, price, and net assets. The S&P 500 columns are the index. The 3-month US T-bill is the risk-free rate.

    Columns for a fund that is not in `funds_final` are removed. The index, the risk-free rate, and the series of the remaining funds stay. Empty columns are left out. The sheet keeps its label rows, so another notebook can read it the same way.
    """)
    return


@app.cell(hide_code=True)
def _(get_final, mo):
    series_ready = get_final() is not None
    filter_timeseries_button = mo.ui.run_button(
        label="Keep the remaining funds' time series",
        disabled=not series_ready,
        tooltip=None if series_ready else "Write the final fund file first",
    )
    mo.vstack(
        [
            mo.md("""
            Fund columns that are not in the final set are removed. The index and the risk-free rate stay.

            The sheet is saved in `output-data/v2-d-timeseries-final.xlsx`.
            """),
            filter_timeseries_button,
        ]
    ).callout(kind="warn", title="Warning")
    return (filter_timeseries_button,)


@app.cell
def _(
    filter_timeseries_button,
    get_final,
    pd,
    set_daily_series,
    workbook,
    write_frame,
):
    if filter_timeseries_button.value:
        _final_funds = get_final()
        if _final_funds is not None:
            from helpers.funds_functions.filter_daily_timeseries import (
                filter_daily_timeseries,
            )

            _daily = pd.read_excel(
                workbook,
                sheet_name="D-Timeseries",
                header=None,
                engine="openpyxl",
            )
            _kept = _final_funds["funds"]
            _daily_timeseries_final, _roles = filter_daily_timeseries(
                _daily,
                _kept["ISIN"],
                _kept["daily_tr_name"] if "daily_tr_name" in _kept.columns else None,
            )
            series_export = write_frame(
                _daily_timeseries_final,
                "v2-d-timeseries-final.xlsx",
                header=False,
            )
            set_daily_series(
                {
                    "frame": _daily_timeseries_final,
                    "roles": _roles,
                    "export": series_export,
                    "started_columns": _daily.shape[1],
                    "started_rows": len(_daily),
                }
            )
    return


@app.cell
def _(get_daily_series, get_final, mo, pd, review_table):
    series_result = get_daily_series()
    mo.stop(
        series_result is None,
        None
        if get_final() is not None
        else mo.md(
            "Write the final fund file first. This step reads `funds_final`."
        ),
    )
    daily_timeseries_final = series_result["frame"]
    roles = pd.Series(series_result["roles"])
    market_rows = []
    for position in roles.index[roles.isin(["index", "risk-free rate"])]:
        market_rows.append(
            {
                "role": "Index" if roles.iloc[position] == "index" else "Risk-free rate",
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
        kept_fund_ids.notna() & kept_fund_ids.ne("") & kept_fund_ids.ne("<NA>")
    ]
    removed_columns = series_result["started_columns"] - daily_timeseries_final.shape[1]
    mo.vstack(
        [
            mo.md(
                f"- **D-Timeseries:** {series_result['started_rows']:,} rows, {series_result['started_columns']:,} columns \n"
                f"- **{kept_fund_ids.nunique()}** funds remain, with **{fund_columns}** series columns \n"
                f"- **{int(roles.eq('index').sum())}** index columns and **{int(roles.eq('risk-free rate').sum())}** risk-free rate column kept \n"
                f"- **{removed_columns:,}** columns removed \n"
                f"- Wrote {series_result['started_rows']:,} rows to `{series_result['export']}` \n"
            ),
            review_table(
                market_catalog,
                ["role", "id", "name", "note"],
                "Index and risk-free rate",
            ),
        ]
    )
    return (daily_timeseries_final,)


if __name__ == "__main__":
    app.run()
