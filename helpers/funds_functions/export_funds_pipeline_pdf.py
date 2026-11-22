"""Write a PDF summary of the load-funds-v2 pipeline after a completed run.

Interactive notebook tables become placeholders. Run buttons are omitted.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import pymupdf

DEFAULT_PDF_PATH = Path("output-data/v2-funds-pipeline-report.pdf")


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def _p(text: str) -> str:
    return f"<p>{_esc(text)}</p>"


def _li(items: list[str]) -> str:
    if not items:
        return ""
    body = "".join(f"<li>{_esc(item)}</li>" for item in items)
    return f"<ul>{body}</ul>"


def _table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{_esc(cell)}</td>" for cell in row)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        '<table border="1" cellpadding="4" cellspacing="0" '
        'style="border-collapse:collapse;width:100%;margin:0.4em 0 0.8em">'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )


def _placeholder(label: str, rows: int | None = None) -> str:
    detail = f" ({rows:,} rows)" if rows is not None else ""
    return (
        '<div style="border:1px dashed #888;padding:10px;margin:8px 0;'
        'background:#f7f7f7;color:#444">'
        f"[Interactive table omitted from PDF: {_esc(label)}{detail}]"
        "</div>"
    )


def _h2(text: str) -> str:
    return f"<h2>{_esc(text)}</h2>"


def _h3(text: str) -> str:
    return f"<h3>{_esc(text)}</h3>"


def _section(title: str, blocks: list[str]) -> str:
    return _h2(title) + "".join(blocks)


def build_pipeline_report_html(report: dict[str, Any]) -> str:
    """Build HTML for the PDF from a structured pipeline report dict."""
    counts = report["counts"]
    matrix = report["matrix"]
    steps = report["steps"]

    parts: list[str] = [
        "<html><head><meta charset='utf-8'></head><body>",
        "<h1>Load and analyze funds (V2) — pipeline report</h1>",
        _p(
            "Static export of the marimo notebook after a completed run. "
            "Run buttons are omitted. Paginated / scrollable interactive tables "
            "are replaced by placeholders."
        ),
        _p(f"Generated: {report.get('generated_at', '')}"),
        _p(f"Excel workbook: {report.get('excel_export', '')}"),
        _section(
            "Overview",
            [
                _p(
                    "Goal: produce a clean fund cross-section for the thesis, "
                    "enriched with OpenFIGI / EDGAR identifiers, one primary share "
                    "class per series, Active/Passive verification, and a usable "
                    "daily total-return path."
                ),
                _li(
                    [
                        "Selection rule: dropped funds leave permanently",
                        "Excel is written once at the end (step 8)",
                        "Each step has Documentation, Result, and Decision",
                    ]
                ),
            ],
        ),
        _section(
            "Sample path",
            [
                _table(
                    ["Stage", "Funds", "Change"],
                    report["funnel"],
                )
            ],
        ),
    ]

    for step in steps:
        blocks = [
            _h3("1. Documentation — What and why"),
            _p(step["what_why"]),
            _h3("1. Documentation — How"),
            _li(step["how"]),
            _h3("2. Result"),
            _p(step["result"]),
        ]
        for table in step.get("tables", []):
            blocks.append(_placeholder(table["label"], table.get("rows")))
        blocks.extend(
            [
                _h3("3. Decision"),
                _p(step["decision"]),
            ]
        )
        if step.get("decision_tables"):
            for table in step["decision_tables"]:
                blocks.append(_h3(table["title"]))
                blocks.append(_table(table["headers"], table["rows"]))
        if step.get("outcome"):
            blocks.append(_li(step["outcome"]))
        parts.append(_section(step["title"], blocks))

    conclusion_blocks: list[str] = []
    academic = report.get("academic_conclusion")
    if academic:
        for block in str(academic).split("\n\n"):
            text = block.strip()
            if not text:
                continue
            if text.startswith("### "):
                conclusion_blocks.append(_h3(text[4:]))
            else:
                conclusion_blocks.append(_p(text.replace("\n", " ")))
    else:
        conclusion_blocks.extend(
            [
                _h3("Reclassification"),
                _li(
                    [
                        f"Sheet and EDGAR confirmed same Active/Passive: {counts['confirmed']:,}",
                        f"Sheet Active/Passive overridden by EDGAR: {counts['reclassified']:,}",
                        f"EDGAR Other dropped: {counts['drop_other']:,}",
                    ]
                ),
                _h3("Data enrichments"),
                _p("On the fund cross-section:"),
                _li(report["enrichments_funds"]),
                _p("On the timeseries panel:"),
                _li(report["enrichments_series"]),
            ]
        )
    conclusion_blocks.extend(
        [
            _h3("Table. Final sample by wrapper × style"),
            _p(f"Counts for the {counts['final']:,} funds in funds_final:"),
            _table(
                ["", "Mutual fund", "ETF"],
                [
                    ["Active", matrix["active_mf"], matrix["active_etf"]],
                    ["Passive", matrix["passive_mf"], matrix["passive_etf"]],
                ],
            ),
            _h3("Table. Enrichments"),
            _p("On the fund cross-section:"),
            _li(report["enrichments_funds"]),
            _p("On the timeseries panel:"),
            _li(report["enrichments_series"]),
        ]
    )
    if report.get("funnel"):
        conclusion_blocks.extend(
            [
                _h3("Table. Sample attrition"),
                _table(["Stage", "Funds", "Change"], report["funnel"]),
            ]
        )
    parts.append(_section("Conclusion", conclusion_blocks))
    parts.append("</body></html>")
    return "\n".join(parts)


def write_pipeline_pdf(
    report: dict[str, Any],
    path: Path | str | None = None,
) -> Path:
    """Render ``report`` to PDF and return the output path."""
    output = Path(path) if path is not None else DEFAULT_PDF_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    story = pymupdf.Story(html=build_pipeline_report_html(report))
    writer = pymupdf.DocumentWriter(str(output))
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (48, 48, -48, -48)
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()
    return output


def build_funds_v2_report(
    *,
    generated_at: str,
    excel_export: str,
    funnel: list[list[object]],
    counts: dict[str, int],
    matrix: dict[str, int],
    enrichments_funds: list[str],
    enrichments_series: list[str],
    step_extras: dict[str, Any] | None = None,
    academic_conclusion: str | None = None,
) -> dict[str, Any]:
    """Assemble the report payload used by the load-funds-v2 conclusion cell."""
    extras = step_extras or {}
    steps = [
        {
            "title": "1. Load the data",
            "what_why": (
                "Open the Lipper / Datastream extract and define a transparent "
                "working sample for later identifier, EDGAR, and timeseries steps."
            ),
            "how": [
                "Read the Funds sheet of the input workbook",
                "Normalize columns to snake_case with prefix ds.",
                "Keep rows whose asset-class fund_type is non-empty as selected_funds",
            ],
            "result": (
                f"Loaded {counts['loaded']:,} funds; selected {counts['selected']:,} "
                "with a non-empty fund_type."
            ),
            "tables": [
                {
                    "label": "selected_funds by fund_type",
                    "rows": extras.get("fund_type_groups"),
                }
            ],
            "decision": (
                "Keep rows with a non-empty fund_type as the working selection. "
                "Rows without fund_type are out of scope."
            ),
            "outcome": [f"Selection remaining: {counts['selected']:,} funds"],
        },
        {
            "title": "2. Verify if ISIN and CUSIP are unique",
            "what_why": (
                "Audit identifier uniqueness and fill missing US CUSIPs from ISIN "
                "when OpenFIGI confirms the listing."
            ),
            "how": [
                "Report unique / duplicate / missing ISIN and CUSIP counts",
                "For missing CUSIP + US ISIN, derive CUSIP and confirm via OpenFIGI",
                "Write filled values onto selected_funds_modified only",
            ],
            "result": (
                f"Filled {counts['cusip_filled']:,} missing CUSIPs from US ISINs "
                "where OpenFIGI confirmed the match."
            ),
            "tables": [
                {"label": "Duplicate identifiers", "rows": extras.get("dup_rows")},
                {"label": "Missing identifiers", "rows": extras.get("missing_id_rows")},
            ],
            "decision": (
                "No funds are dropped. Correct the dataset by adding confirmed "
                "missing CUSIPs."
            ),
            "outcome": [f"Selection remaining: {counts['selected']:,} funds"],
        },
        {
            "title": "3. Match with OpenFIGI",
            "what_why": (
                "Attach a market ticker and FIGI name so later EDGAR and Yahoo "
                "lookups have a stable market identifier."
            ),
            "how": [
                "Lookup each ISIN in OpenFIGI; check CUSIP consistency",
                "Add openfigi_market_id, openfigi_name, match flags",
                "Drop documented closed/merged unmatched ISINs; keep caveat fund",
            ],
            "result": (
                f"After unmatched review: {counts['after_openfigi']:,} funds remain "
                f"(dropped {counts['drop_openfigi']:,} closed/merged unmatched)."
            ),
            "tables": [
                {
                    "label": "Unmatched OpenFIGI review",
                    "rows": extras.get("openfigi_unmatched_rows"),
                }
            ],
            "decision": (
                "Drop closed/merged unmatched funds permanently; keep the remaining "
                "caveat unmatched fund for later steps."
            ),
            "outcome": [f"Selection remaining: {counts['after_openfigi']:,} funds"],
        },
        {
            "title": "4. Match with EDGAR",
            "what_why": (
                "Attach SEC registrant / series / class identifiers used for share-"
                "class selection and Active/Passive classification."
            ),
            "how": [
                "Match ISINs to the EDGAR fund reference",
                "Apply documented ticker / name / closed-fund corrections",
                "Enrich CIK, series id/name, class id/name, match status",
            ],
            "result": (
                f"EDGAR enrichment applied to {counts['after_openfigi']:,} funds still "
                "in the selection. No permanent drops in this step."
            ),
            "tables": [
                {
                    "label": "No matching EDGAR / corrections",
                    "rows": extras.get("edgar_unmatched_rows"),
                }
            ],
            "decision": "No funds are removed; enrichment only.",
            "outcome": [f"Selection remaining: {counts['after_openfigi']:,} funds"],
        },
        {
            "title": "5 / 5b. Primary share class",
            "what_why": (
                "Collapse multi-class series to one comparable retail share class "
                "for the cross-section."
            ),
            "how": [
                "Flag shared CIK/series groups and missing class ids",
                "Select one primary class per series using the documented priority rules",
                "Drop secondary classes permanently",
            ],
            "result": (
                f"Removed {counts['drop_primary']:,} secondary share classes; "
                f"{counts['after_primary']:,} funds remain."
            ),
            "tables": [
                {
                    "label": "Dropped share classes",
                    "rows": extras.get("dropped_class_rows"),
                },
                {
                    "label": "Primary share class (kept)",
                    "rows": extras.get("primary_kept_rows"),
                },
            ],
            "decision": (
                "Keep one primary share class per series. Dropped classes leave "
                "the working selection permanently."
            ),
            "outcome": [f"Selection remaining: {counts['after_primary']:,} funds"],
        },
        {
            "title": "6. Verify fund type (active vs passive)",
            "what_why": (
                "Challenge the sheet Active/Passive label with SEC N-CEN evidence "
                "and, when needed, prospectus language via Jev."
            ),
            "how": [
                "Classify with N-CEN fundTypes / indexFundInfo",
                "Fall back to Jev on prospectus text when N-CEN does not decide",
                "Active↔Passive overrides adopt EDGAR; Other is dropped; Unknown keeps sheet",
            ],
            "result": (
                f"Confirmed {counts['confirmed']:,}; overridden {counts['reclassified']:,}; "
                f"dropped Other {counts['drop_other']:,}."
            ),
            "tables": [
                {
                    "label": "Fund type mismatch",
                    "rows": extras.get("mismatch_rows"),
                },
                {
                    "label": "Dropped (EDGAR fund type Other)",
                    "rows": extras.get("dropped_other_rows"),
                },
            ],
            "decision": (
                "Match → keep; Active↔Passive → override to EDGAR; Other → drop; "
                "Unknown → keep sheet label."
            ),
            "outcome": [f"Selection remaining: {counts['after_style']:,} funds"],
        },
        {
            "title": "7. Verify daily total-return timeseries",
            "what_why": (
                "Attach a usable daily total-return path. Resolve Datastream name "
                "mismatches and funds with no Datastream series via Yahoo Finance."
            ),
            "how": [
                "Match D-Timeseries total-return columns by ISIN and confirm names",
                "Name-gap Yahoo correlation check → keep high corr / drop weak or missing",
                "No Datastream TR → fetch Yahoo auto_adjust=True TR, append, keep; else drop",
            ],
            "result": (
                f"Name-gap drops {counts['drop_name_gap']:,}; no-TR drops "
                f"{counts['drop_no_tr']:,}; Yahoo TR backfills {counts['yahoo_filled']:,}. "
                f"Final timeseries set: {counts['final']:,}."
            ),
            "tables": [
                {
                    "label": "Series name does not match",
                    "rows": extras.get("name_gap_rows"),
                },
                {
                    "label": "No daily total return",
                    "rows": extras.get("missing_tr_rows"),
                },
                {
                    "label": "Yahoo check — funds with no Datastream TR",
                    "rows": extras.get("yahoo_fill_rows"),
                },
                {
                    "label": "Dropped (name gap)",
                    "rows": extras.get("dropped_name_gap_rows"),
                },
                {
                    "label": "Dropped (no daily total return)",
                    "rows": extras.get("dropped_no_tr_rows"),
                },
            ],
            "decision": (
                "Name-gap: keep when Yahoo confirms the Datastream series; drop otherwise. "
                "No Datastream TR: append Yahoo total return when available; else drop."
            ),
            "decision_tables": extras.get("step7_decision_tables", []),
            "outcome": [f"Selection remaining: {counts['final']:,} funds"],
        },
        {
            "title": "8. Export the final fund set and timeseries",
            "what_why": (
                "Freeze the cleaned cross-section and write one normalized workbook "
                "for the series-cleaning notebook and thesis appendices."
            ),
            "how": [
                "Arrange Funds final column groups",
                "Filter D-Timeseries to remaining funds + index + risk-free",
                "Write all accumulated sheets once to the normalized Excel path",
            ],
            "result": (
                f"Wrote {excel_export} with {counts['final']:,} funds and a filtered "
                "D-Timeseries final panel."
            ),
            "tables": [
                {
                    "label": "Column order",
                    "rows": extras.get("column_order_rows"),
                },
                {
                    "label": "Final fund set",
                    "rows": counts["final"],
                },
                {
                    "label": "Index and risk-free rate",
                    "rows": extras.get("market_rows"),
                },
            ],
            "decision": (
                "No funds are removed. This step is the sole Excel write for the pipeline."
            ),
            "outcome": [f"Selection remaining: {counts['final']:,} funds"],
        },
    ]
    return {
        "generated_at": generated_at,
        "excel_export": excel_export,
        "funnel": funnel,
        "counts": counts,
        "matrix": matrix,
        "enrichments_funds": enrichments_funds,
        "enrichments_series": enrichments_series,
        "academic_conclusion": academic_conclusion,
        "steps": steps,
    }
