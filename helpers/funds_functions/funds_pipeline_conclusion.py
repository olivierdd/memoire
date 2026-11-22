"""Figures and tables for the academic conclusion of load-funds-v2.

Figures are plain HTML/SVG so the marimo sandbox does not need Altair.
"""

from __future__ import annotations

import html
from typing import Any

import pandas as pd


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def attrition_frame(stages: list[tuple[str, int]]) -> pd.DataFrame:
    rows = []
    previous = None
    for index, (label, count) in enumerate(stages, start=1):
        removed = 0 if previous is None else max(previous - count, 0)
        rows.append(
            {
                "order": index,
                "stage": label,
                "funds": int(count),
                "removed": int(removed),
            }
        )
        previous = count
    return pd.DataFrame(rows)


def _horizontal_bars(
    labels: list[str],
    values: list[int],
    *,
    title: str,
    color: str = "#4a5568",
    width: int = 560,
    row_height: int = 28,
) -> str:
    max_value = max(values) if values else 1
    max_value = max(max_value, 1)
    plot_width = width - 220
    rows_html: list[str] = []
    for label, value in zip(labels, values):
        bar_w = int(round(plot_width * (value / max_value)))
        rows_html.append(
            "<tr>"
            f"<td style='text-align:right;padding:4px 10px 4px 0;white-space:nowrap;"
            f"font-size:12px;width:200px'>{_esc(label)}</td>"
            "<td style='padding:4px 0'>"
            f"<div style='background:{color};height:16px;width:{bar_w}px;"
            "display:inline-block;vertical-align:middle'></div>"
            f"<span style='margin-left:8px;font-size:12px'>{value:,}</span>"
            "</td></tr>"
        )
    height = 40 + row_height * max(len(labels), 1)
    return (
        f"<div style='max-width:{width}px;margin:0.75rem 0 1.25rem'>"
        f"<div style='font-weight:600;margin-bottom:0.5rem'>{_esc(title)}</div>"
        f"<table style='border-collapse:collapse;width:100%;height:{height}px'>"
        f"{''.join(rows_html)}</table></div>"
    )


def attrition_figure_html(stages: list[tuple[str, int]]) -> str:
    frame = attrition_frame(stages)
    return _horizontal_bars(
        frame["stage"].tolist(),
        frame["funds"].astype(int).tolist(),
        title="Figure 1. Sample attrition across construction stages",
        color="#4a5568",
    )


def composition_frame(matrix: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "style": "Active",
                "wrapper": "Mutual fund",
                "funds": int(matrix["active_mf"]),
            },
            {
                "style": "Active",
                "wrapper": "ETF",
                "funds": int(matrix["active_etf"]),
            },
            {
                "style": "Passive",
                "wrapper": "Mutual fund",
                "funds": int(matrix["passive_mf"]),
            },
            {
                "style": "Passive",
                "wrapper": "ETF",
                "funds": int(matrix["passive_etf"]),
            },
        ]
    )


def composition_figure_html(matrix: dict[str, int], *, total: int) -> str:
    """Grouped bars for Active/Passive within Mutual fund and ETF."""
    frame = composition_frame(matrix)
    max_value = max(int(v) for v in frame["funds"]) if len(frame) else 1
    max_value = max(max_value, 1)
    colors = {"Active": "#2f4f4f", "Passive": "#8b7355"}
    groups = ["Mutual fund", "ETF"]
    bar_max = 160
    group_blocks: list[str] = []
    for wrapper in groups:
        subset = frame.loc[frame["wrapper"].eq(wrapper)]
        bars = []
        for _, row in subset.iterrows():
            height = int(round(bar_max * (int(row["funds"]) / max_value)))
            bars.append(
                "<div style='display:inline-block;text-align:center;margin:0 10px'>"
                f"<div style='font-size:12px;margin-bottom:4px'>{int(row['funds']):,}</div>"
                "<div style='height:"
                f"{bar_max}px;display:flex;align-items:flex-end;justify-content:center'>"
                f"<div style='width:36px;height:{height}px;background:{colors[row['style']]}'>"
                "</div></div>"
                f"<div style='font-size:11px;margin-top:6px'>{_esc(row['style'])}</div>"
                "</div>"
            )
        share = (
            100.0 * int(subset["funds"].sum()) / total if total else 0.0
        )
        group_blocks.append(
            "<div style='display:inline-block;vertical-align:top;margin:0 1.5rem;"
            "text-align:center'>"
            f"<div style='font-size:13px;font-weight:600;margin-bottom:8px'>"
            f"{_esc(wrapper)} ({share:.1f}%)</div>"
            f"{''.join(bars)}</div>"
        )
    return (
        "<div style='margin:0.75rem 0 1.25rem'>"
        "<div style='font-weight:600;margin-bottom:0.75rem'>"
        "Figure 2. Final sample by wrapper and management style</div>"
        f"{''.join(group_blocks)}</div>"
    )


def reclassification_figure_html(counts: dict[str, int]) -> str:
    labels = [
        "Confirmed (sheet = EDGAR)",
        "Overridden (Active ↔ Passive)",
        "Dropped (EDGAR Other)",
    ]
    values = [
        int(counts["confirmed"]),
        int(counts["reclassified"]),
        int(counts["drop_other"]),
    ]
    return _horizontal_bars(
        labels,
        values,
        title="Figure 3. Outcomes of the Active/Passive verification",
        color="#5c6b73",
        width=520,
    )


def contingency_table(matrix: dict[str, int], *, total: int) -> pd.DataFrame:
    frame = composition_frame(matrix).copy()
    frame["share_pct"] = (
        (100.0 * frame["funds"] / total).round(1) if total else 0.0
    )
    wide = (
        frame.pivot(index="style", columns="wrapper", values="funds")
        .reindex(index=["Active", "Passive"], columns=["Mutual fund", "ETF"])
        .fillna(0)
        .astype(int)
    )
    shares = (
        frame.pivot(index="style", columns="wrapper", values="share_pct")
        .reindex(index=["Active", "Passive"], columns=["Mutual fund", "ETF"])
        .fillna(0.0)
    )
    out = pd.DataFrame(
        {
            "Mutual fund": [
                f"{wide.loc['Active', 'Mutual fund']} ({shares.loc['Active', 'Mutual fund']:.1f}%)",
                f"{wide.loc['Passive', 'Mutual fund']} ({shares.loc['Passive', 'Mutual fund']:.1f}%)",
            ],
            "ETF": [
                f"{wide.loc['Active', 'ETF']} ({shares.loc['Active', 'ETF']:.1f}%)",
                f"{wide.loc['Passive', 'ETF']} ({shares.loc['Passive', 'ETF']:.1f}%)",
            ],
        },
        index=["Active", "Passive"],
    )
    out.index.name = "Management style"
    return out.reset_index()


def attrition_table(stages: list[tuple[str, int]]) -> pd.DataFrame:
    frame = attrition_frame(stages).copy()
    frame["retention_pct"] = (
        100.0 * frame["funds"] / frame["funds"].iloc[0]
        if len(frame) and frame["funds"].iloc[0]
        else 0.0
    )
    frame["retention_pct"] = frame["retention_pct"].round(1)
    return frame.rename(
        columns={
            "stage": "Stage",
            "funds": "Funds",
            "removed": "Removed vs prior",
            "retention_pct": "Retention of initial load (%)",
        }
    )[["Stage", "Funds", "Removed vs prior", "Retention of initial load (%)"]]


def verification_table(counts: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Outcome": "Sheet label confirmed by EDGAR/N-CEN/Jev",
                "Funds": int(counts["confirmed"]),
            },
            {
                "Outcome": "Sheet Active/Passive overridden by EDGAR",
                "Funds": int(counts["reclassified"]),
            },
            {
                "Outcome": "Dropped as EDGAR Other",
                "Funds": int(counts["drop_other"]),
            },
            {
                "Outcome": "CUSIPs filled from US ISIN (step 2)",
                "Funds": int(counts["cusip_filled"]),
            },
            {
                "Outcome": "Yahoo total-return series appended (step 7)",
                "Funds": int(counts["yahoo_filled"]),
            },
        ]
    )


def academic_closing_paragraphs(payload: dict[str, Any]) -> str:
    """Markdown body for the academic conclusion (figures/tables referenced in prose)."""
    c = payload["counts"]
    m = payload["matrix"]
    excel = payload["excel_export"]
    n_final = c["final"]
    n_loaded = c["loaded"]
    retention = (100.0 * n_final / n_loaded) if n_loaded else 0.0
    return f"""
### Purpose and contribution

This notebook constructs a reproducible cross-section of U.S. mutual funds and
exchange-traded funds (ETFs) for subsequent total-return analysis. Starting from
a commercial Lipper/Datastream extract of **{n_loaded:,}** fund rows, the
pipeline applies identifier quality controls, legal-entity enrichment, share-class
consolidation, Active/Passive verification against SEC filings, and daily
total-return screening. The resulting sample contains **{n_final:,}** primary
share classes (**{retention:.1f}%** of the initial extract) and is written once to
`{excel}`.

### Sample construction

Figure 1 and Table 1 summarise attrition. The largest reductions arise from
(i) restricting to rows with a non-empty asset-class `fund_type`,
(ii) retaining a single primary share class per EDGAR series, and
(iii) requiring a usable daily total-return path. Closed or merged funds without
an OpenFIGI match, and series classified as EDGAR “Other”, are removed
permanently and are not reconsidered in later steps.

### Classification and enrichment

Commercial Active/Passive labels are treated as provisional. Step 6 challenges
them with N-CEN disclosures and, where necessary, prospectus language. Table 2
and Figure 3 report the verification outcomes: **{c['confirmed']:,}** labels were
confirmed, **{c['reclassified']:,}** Active↔Passive disagreements were resolved in
favour of the EDGAR classification, and **{c['drop_other']:,}** funds were
excluded as structural “Other” products. Parallel enrichments attach OpenFIGI
market identifiers, EDGAR CIK/series/class fields, and Datastream (or Yahoo
total-return) daily paths; **{c['yahoo_filled']:,}** funds without a Datastream
series were retained after a Yahoo dividend-and-split-adjusted backfill.

### Composition of the final sample

The analytical design distinguishes management style (Active vs Passive) from
distribution wrapper (mutual fund vs ETF). Figure 2 and Table 3 present the
2×2 partition of the **{n_final:,}** retained funds:

- Active mutual funds: **{m['active_mf']:,}**
- Passive mutual funds: **{m['passive_mf']:,}**
- Active ETFs: **{m['active_etf']:,}**
- Passive ETFs: **{m['passive_etf']:,}**

This taxonomy is the unit of analysis for the downstream series-cleaning and
regression notebooks.

### Artefacts

The normalised workbook and this pipeline report document both the selection
rules and the realised sample, so that empirical results can be traced to an
explicit construction protocol rather than to an opaque commercial screen.
""".strip()
