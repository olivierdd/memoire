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
    get_series_export, set_series_export = mo.state(None)
    get_style, set_style = mo.state(None)
    get_timeseries, set_timeseries = mo.state(None)
    return (
        get_cusip_fill,
        get_edgar,
        get_openfigi,
        get_series_export,
        get_style,
        get_timeseries,
        set_cusip_fill,
        set_edgar,
        set_openfigi,
        set_series_export,
        set_style,
        set_timeseries,
    )


@app.cell
def _(mo):
    def review_table(frame, columns, label):
        present = [column for column in columns if column in frame.columns]
        view = frame.loc[:, present].copy() if present else frame.copy()
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

    The workbook loads immediately. Each later step that calls OpenFIGI, EDGAR, or Jev, or that writes an Excel file, waits for its button. `selected_funds` stays the sheet selection. Later tables are copies: `funds_with_cusip`, `funds_openfigi`, `funds_edgar`, `funds_classified`, and `funds_with_timeseries`.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### 1. Load the data

    Load the **Funds** sheet of `CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx` from `input-data-alix/clean/`.
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

    def write_frame(frame, filename: str) -> Path:
        start = Path.cwd().resolve()
        for directory in [start, *start.parents]:
            if (directory / "helpers").is_dir():
                destination = directory / "output-data"
                destination.mkdir(parents=True, exist_ok=True)
                path = destination / filename
                frame.to_excel(path, index=False)
                return path
        raise FileNotFoundError(f"Could not find helpers/, starting from {start}")

    FILENAME = "CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx"
    workbook = find_workbook(Path("input-data-alix") / "clean" / FILENAME)
    funds = load_workbook(workbook)
    selected_funds = funds.loc[
        funds["fund_type"].notna()
        & funds["fund_type"].astype("string").str.strip().ne("")
    ].copy()
    return (
        FILENAME,
        Path,
        capture_prints,
        find_workbook,
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
                f"Loaded `{workbook}`\n\n"
                f"**Funds:** {len(funds):,} rows, {len(funds.columns)} columns\n\n"
                f"**selected_funds:** {len(selected_funds):,} rows"
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
    ### 2. Verify if ISIN and CUSIP are unique
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
            f"**{column}:** {filled.nunique()} unique values among {len(filled)} "
            f"non-empty ({values.isna().sum()} missing) — {status}"
        )

    isin_shared = isin.notna() & isin.duplicated(keep=False)
    cusip_shared = cusip.notna() & cusip.duplicated(keep=False)
    shared_funds = selected_funds.loc[
        isin_shared | cusip_shared, ["Name", "ISIN", "CUSIP", "fund_type"]
    ].copy()
    blocks = [mo.md("\n\n".join(lines))]
    if shared_funds.empty:
        blocks.append(mo.md("No funds share an ISIN or a CUSIP."))
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
        blocks.append(mo.md(f"**{shared_count} {shared_verb} an ISIN or a CUSIP**"))
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
        blocks.append(mo.md("No funds are missing an ISIN or a CUSIP."))
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
            mo.md(f"**{missing_count} {missing_verb} missing an ISIN or a CUSIP**")
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
    mo.md("""
    **Dataset enrichment**

    A US ISIN is `US`, then the 9-character CUSIP, then one check digit. For each selected fund with an empty CUSIP and a US ISIN, that middle value is sent to OpenFIGI (`ID_CUSIP`).

    The CUSIP is written into `funds_with_cusip` only when OpenFIGI returns the same listing as the ISIN. The same FIGI means the same listing. Any other result is left blank. `selected_funds` is left unchanged.
    """).callout(kind="warn", title="Dataset enrichment")
    return


@app.cell
def _(mo):
    fill_cusips_button = mo.ui.run_button(label="Fill missing CUSIPs from OpenFIGI")
    fill_cusips_button
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
    mo.stop(
        cusip_fill is None,
        mo.md("Click **Fill missing CUSIPs from OpenFIGI** to query OpenFIGI."),
    )
    funds_with_cusip = cusip_fill["funds"]
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
    return (funds_with_cusip,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### 4. Verify ISINs and enrich dataset with OpenFIGI

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
def _(mo):
    mo.md("""
    **Some records have no OpenFIGI match and will have no market ticker and no possibility to match with EDGAR.**

    Funds with no match are saved in `output-data/v2-no-matching-OPENFIGI.xlsx`.
    """).callout(kind="warn")
    return


@app.cell
def _(get_cusip_fill, mo):
    cusips_ready = get_cusip_fill() is not None
    verify_openfigi_button = mo.ui.run_button(
        label="Verify ISINs with OpenFIGI",
        disabled=not cusips_ready,
        tooltip=None if cusips_ready else "Fill missing CUSIPs first",
    )
    verify_openfigi_button
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
        mo.md(
            "Click **Verify ISINs with OpenFIGI**."
            if get_cusip_fill() is not None
            else "Fill missing CUSIPs first. This step reads `funds_with_cusip`."
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
            f"**{openfigi_found}** of {len(funds_openfigi)} ISINs found in OpenFIGI\n\n"
            f"**{openfigi_name_matches}** of {len(funds_openfigi)} names match the OpenFIGI record\n\n"
            f"**{openfigi_cusip_matches}** of {len(funds_openfigi)} CUSIPs return the same OpenFIGI record as the ISIN\n\n"
            f"Wrote {len(openfigi_result['unmatched'])} rows to `{openfigi_result['export']}`"
        )
    ]
    if openfigi_result["log"].strip():
        openfigi_blocks.append(mo.plain_text(openfigi_result["log"].strip()))
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
    ### 5. Verify and enrich ISINs with EDGAR

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
def _(mo):
    mo.md("""
    **Some records have no EDGAR match and will not be enriched.**

    Funds with no match are saved in `output-data/v2-no-matching-EDGAR.xlsx`.
    """).callout(kind="warn")
    return


@app.cell
def _(get_openfigi, mo):
    openfigi_ready = get_openfigi() is not None
    match_edgar_button = mo.ui.run_button(
        label="Match EDGAR identifiers",
        disabled=not openfigi_ready,
        tooltip=None if openfigi_ready else "Verify ISINs with OpenFIGI first",
    )
    match_edgar_button
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
        mo.md(
            "Click **Match EDGAR identifiers**."
            if get_openfigi() is not None
            else "Verify ISINs with OpenFIGI first. This step reads `funds_openfigi`."
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
        "CUSIP",
    ]
    edgar_matches = int(funds_edgar["edgar_isin_found"].sum())
    edgar_name_matches = int(
        funds_edgar.loc[funds_edgar["edgar_isin_found"], "edgar_name_match"].sum()
    )
    edgar_blocks = [
        mo.md(
            f"**{edgar_matches}** of {len(funds_edgar)} ISINs match an EDGAR record\n\n"
            f"**{edgar_name_matches}** of {edgar_matches} EDGAR names match the sheet\n\n"
            f"{len(edgar_result['unmatched'])} funds have no EDGAR record\n\n"
            f"Wrote {len(edgar_result['unmatched'])} rows to `{edgar_result['export']}`"
        )
    ]
    if edgar_result["log"].strip():
        edgar_blocks.append(mo.plain_text(edgar_result["log"].strip()))
    edgar_blocks.append(review_table(funds_edgar, edgar_columns, "EDGAR check"))
    edgar_blocks.append(
        review_table(edgar_result["unmatched"], edgar_columns, "No EDGAR match")
    )
    mo.vstack(edgar_blocks)
    return (funds_edgar,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### 6. Verify if some funds belong to the same series

    Funds are filed in EDGAR as a registrant (CIK), then a series, then a share class. One CIK is the investment company. It can offer several series, and each series can offer several share classes of the same portfolio.

    The selected funds are all supposed to be primary share classes: the main share class among many. Therefore we don't expect to see rows in our table that belong to the same CIK and series.
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


@app.cell
def _(get_edgar, mo, review_table, series_groups):
    series_input = get_edgar()
    mo.stop(
        series_input is None,
        mo.md("Match EDGAR identifiers first. This step reads `funds_edgar`."),
    )
    missing_class_id, same_cik_series = series_groups(series_input["funds"])
    class_count = len(missing_class_id)
    class_verb = "fund has" if class_count == 1 else "funds have"
    series_count = len(same_cik_series)
    series_verb = "fund shares" if series_count == 1 else "funds share"
    series_columns = [
        "edgartools_cik",
        "edgar_company_name",
        "edgartools_series_id",
        "edgar_series_name",
        "edgartools_class_id",
        "edgar_class_name",
        "Name",
        "ISIN",
    ]
    mo.vstack(
        [
            mo.md(f"**{class_count} {class_verb} no EDGAR share class id**"),
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
                f"**{series_count} {series_verb} a CIK and series with another selected fund**"
            ),
            review_table(same_cik_series, series_columns, "Same CIK and series"),
        ]
    )
    return missing_class_id, same_cik_series


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    **Some records have no EDGAR share class id.**

    Those funds are saved in `output-data/v2-no-matching-EDGAR_SHARE_CLASS.xlsx`.
    """).callout(kind="warn")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    **Some records share classes belonging to the same fund series.**

    Those funds are saved in `output-data/v2-common-fund-series.xlsx`.
    """).callout(kind="warn")
    return


@app.cell
def _(get_edgar, mo):
    series_ready = get_edgar() is not None
    save_series_button = mo.ui.run_button(
        label="Save series workbooks",
        disabled=not series_ready,
        tooltip=None if series_ready else "Match EDGAR identifiers first",
    )
    save_series_button
    return (save_series_button,)


@app.cell
def _(
    get_edgar,
    save_series_button,
    series_groups,
    set_series_export,
    write_frame,
):
    if save_series_button.value:
        series_export_input = get_edgar()
        if series_export_input is not None:
            _missing_class_id, _same_cik_series = series_groups(
                series_export_input["funds"]
            )
            share_class_export = write_frame(
                _missing_class_id, "v2-no-matching-EDGAR_SHARE_CLASS.xlsx"
            )
            common_series = _same_cik_series.loc[
                :,
                [
                    "edgartools_cik",
                    "edgar_company_name",
                    "edgartools_series_id",
                    "edgar_series_name",
                    "edgartools_class_id",
                    "edgar_class_name",
                    "Name",
                    "ISIN",
                ],
            ]
            common_series_export = write_frame(
                common_series, "v2-common-fund-series.xlsx"
            )
            set_series_export(
                "\n".join(
                    [
                        f"Wrote {len(_missing_class_id)} rows to {share_class_export}",
                        f"Wrote {len(common_series)} rows to {common_series_export}",
                    ]
                )
            )
    return


@app.cell
def _(get_edgar, get_series_export, mo, save_series_button):
    series_export_note = get_series_export()
    if get_edgar() is None:
        series_hint = "Match EDGAR identifiers first."
    elif save_series_button.value:
        series_hint = "Saving the series workbooks."
    else:
        series_hint = "Click **Save series workbooks** to write the two Excel files."
    mo.stop(series_export_note is None, mo.md(series_hint))
    mo.plain_text(series_export_note)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### 7. Verify fund type (active vs passive)

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
def _(mo):
    mo.md("""
    **Some funds have an invalidated fund type.**

    Funds whose sheet fund type does not match the classified fund type are saved in `output-data/v2-fund-type-mismatch.xlsx`.
    """).callout(kind="warn")
    return


@app.cell
def _(get_edgar, mo):
    edgar_ready = get_edgar() is not None
    classify_style_button = mo.ui.run_button(
        label="Classify fund type",
        disabled=not edgar_ready,
        tooltip=None if edgar_ready else "Match EDGAR identifiers first",
    )
    classify_style_button
    return (classify_style_button,)


@app.cell
def _(
    capture_prints,
    classify_style_button,
    get_edgar,
    set_style,
    write_frame,
):
    if classify_style_button.value:
        style_input = get_edgar()
        if style_input is not None:
            from helpers.funds_functions.classify_fund_management_style import (
                classify_fund_management_style,
            )

            _log_buffer, _redirect = capture_prints()
            with _redirect:
                _funds = classify_fund_management_style(style_input["funds"])

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
        mo.md(
            "Click **Classify fund type**. This step reads N-CEN filings and, where those do not decide, sends prospectus text to Jev."
            if get_edgar() is not None
            else "Match EDGAR identifiers first. This step reads `funds_edgar`."
        ),
    )
    funds_classified = style_result["funds"]
    style_counts = (
        funds_classified["fund_management_style"]
        .value_counts()
        .rename_axis("fund_management_style")
        .reset_index(name="funds")
    )
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
            f"**{len(style_result['mismatch'])}** funds have a sheet fund type that does not match the classified type\n\n"
            f"Wrote {len(style_result['mismatch'])} rows to `{style_result['export']}`"
        ),
        review_table(style_counts, ["fund_management_style", "funds"], "Classified fund type"),
    ]
    if style_result["log"].strip():
        style_blocks.append(mo.plain_text(style_result["log"].strip()))
    style_blocks.append(
        review_table(style_result["mismatch"], mismatch_columns, "Fund type mismatch")
    )
    mo.vstack(style_blocks)
    return (funds_classified,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### 8. Verify if there is a time series

    Load the **D-Timeseries** sheet of the same workbook. The first rows are labels, not a column header. A daily total return series is a column whose note is `Total return index, daily` and that has at least one value.

    Each selected fund is matched on ISIN. The Datastream name on that column is then checked against the fund. The sheet name is used first. When that name does not confirm the series, the OpenFIGI name is used, then the EDGAR name. A shortened Datastream name still counts as the same fund. A different word, such as Value versus Equity, does not.

    `has_daily_total_return` is true when the series exists. `daily_tr_observations` is the number of daily points. `daily_tr_name` is the Datastream name. `daily_tr_name_match` is true when one of the three names confirms it, and `daily_tr_name_source` is the name that did.

    Funds with no series are written to `output-data/v2-no-daily-total-return.xlsx`. Funds whose series name does not match are written to `output-data/v2-no-matching-D-TIMESERIES-NAME.xlsx`.
    """)
    return


@app.cell
def _(get_style, mo):
    style_ready = get_style() is not None
    match_timeseries_button = mo.ui.run_button(
        label="Match daily total return",
        disabled=not style_ready,
        tooltip=None if style_ready else "Classify fund type first",
    )
    match_timeseries_button
    return (match_timeseries_button,)


@app.cell
def _(
    FILENAME,
    Path,
    capture_prints,
    find_workbook,
    get_style,
    match_timeseries_button,
    pd,
    set_timeseries,
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
                    find_workbook(Path("input-data-alix") / "clean" / FILENAME),
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
        mo.md(
            "Click **Match daily total return**. This reads the D-Timeseries sheet and writes the two workbooks."
            if get_style() is not None
            else "Classify fund type first. This step reads `funds_classified`."
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
            f"**D-Timeseries:** {timeseries_result['rows']:,} rows, "
            f"{timeseries_result['columns']} columns\n\n"
            f"**{timeseries_found}** of {len(funds_with_timeseries)} funds have a daily total return series\n\n"
            f"**{matched_names}** of {found} series names match Name, OpenFIGI, or EDGAR\n\n"
            f"Wrote {len(timeseries_result['name_gap'])} rows to `{timeseries_result['name_gap_export']}`\n\n"
            f"Wrote {len(timeseries_result['missing'])} rows to `{timeseries_result['missing_export']}`"
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


if __name__ == "__main__":
    app.run()
