"""Chart the monthly returns and mark the months the consistency check flags."""

import altair as alt
import pandas as pd

from helpers.timeseries_functions.check_timeseries_consistency import SeriesCheck
from helpers.timeseries_functions.compute_fund_to_index_regression import (
    FUND_COLOR,
    INDEX_COLOR,
)

ISSUE_GAP = "Gap"
ISSUE_SPIKE = "Abnormal spike"
ISSUE_LEVEL = "Level jump"
ISSUE_SCALE = "Scale shift"
ISSUE_INDEX = "Far from S&P 500 TR"

ISSUE_ORDER = [ISSUE_GAP, ISSUE_SPIKE, ISSUE_LEVEL, ISSUE_SCALE, ISSUE_INDEX]
ISSUE_COLORS = ["#A16207", "#C2410C", "#BE123C", "#0F766E", "#6D28D9"]
POINT_SHAPES = {
    ISSUE_SPIKE: "circle",
    ISSUE_LEVEL: "square",
    ISSUE_INDEX: "diamond",
}
RULE_ISSUES = (ISSUE_GAP, ISSUE_SCALE)


def issue_markers(check: SeriesCheck) -> pd.DataFrame:
    """One mark per flagged month. Rules have no return; points sit on the fund return.

    A month that is both a spike (or a level jump) and far from the index keeps the
    more specific label. The detail text still names every flag on that month.
    """
    months = check.months
    days = months["Date"].diff().dt.days
    records: list[dict] = []

    for i, row in months.iterrows():
        if row["gap"]:
            reasons = []
            if row["missing"]:
                reasons.append("missing return")
            if row["skipped"]:
                reasons.append("skipped month")
            if row["long_gap"]:
                reasons.append(f"{int(days.iloc[i])} days since the previous date")
            records.append(_mark(row, ISSUE_GAP, ", ".join(reasons), y=None))

        notes = []
        if row["spike"]:
            note = (
                "reverses the next month, the index does not"
                if row["reversal"]
                else "the index does not follow"
            )
            notes.append(
                f"{row['return']:+.2%}  S&P 500 TR {row['index_return']:+.2%}  {note}"
            )
        if row["level_jump"]:
            notes.append(
                f"{row['return']:+.2%}  level does not come back over the next months"
            )
        if row["wide"]:
            gap_bp = (row["return"] - row["index_return"]) * 1e4
            text = (
                f"{gap_bp:+.1f} bp  fund {row['return']:+.2%}  "
                f"index {row['index_return']:+.2%}"
            )
            if row["on_new_scale"]:
                text += "  because the scale has changed"
            notes.append(text)
        if notes:
            if row["spike"]:
                issue = ISSUE_SPIKE
            elif row["level_jump"]:
                issue = ISSUE_LEVEL
            else:
                issue = ISSUE_INDEX
            records.append(_mark(row, issue, " · ".join(notes), y=float(row["return"])))

    if check.scale_at is not None:
        i = check.scale_at
        absolute = months["return"].abs()
        before = absolute.iloc[:i].median()
        after = absolute.iloc[i:].median()
        records.append(
            _mark(
                months.loc[i],
                ISSUE_SCALE,
                f"median |return| goes from {before:.2%} to {after:.2%} and stays there",
                y=None,
            )
        )

    return pd.DataFrame.from_records(
        records,
        columns=["Date", "Period", "Return", "Issue", "Detail"],
    )


def plot_timeseries_issues(
    checks: list[SeriesCheck],
    index_column: str,
) -> alt.VConcatChart | alt.LayerChart:
    """Two panels (master, then comparison), with the flagged months marked."""
    panels = [_panel(check, index_column) for check in checks]
    if len(panels) == 1:
        return panels[0]
    chart = panels[0]
    for panel in panels[1:]:
        chart = chart & panel
    return chart.resolve_scale(y="shared")


def _mark(row: pd.Series, issue: str, detail: str, y: float | None) -> dict:
    return {
        "Date": row["Date"],
        "Period": row["Period"],
        "Return": y,
        "Issue": issue,
        "Detail": detail,
    }


def _subtitle(check: SeriesCheck) -> str:
    months = check.months
    counts = (
        (int(months["gap"].sum()), "gap", "gaps"),
        (int(months["spike"].sum()), "abnormal spike", "abnormal spikes"),
        (int(months["level_jump"].sum()), "level jump", "level jumps"),
        (0 if check.scale_at is None else 1, "scale shift", "scale shifts"),
        (
            int(months["wide"].sum()),
            f"month more than {check.index_gap:.0%} from the S&P 500 TR",
            f"months more than {check.index_gap:.0%} from the S&P 500 TR",
        ),
    )
    parts = [
        f"{count} {singular if count == 1 else plural}"
        for count, singular, plural in counts
        if count
    ]
    if not parts:
        return "No gaps, spikes, scale shifts, or months far from the S&P 500 TR"
    return " · ".join(parts)


def _panel(check: SeriesCheck, index_column: str) -> alt.LayerChart:
    months = check.months
    index_line = months.loc[
        months["index_return"].notna(), ["Date", "Period", "index_return"]
    ].rename(columns={"index_return": "Return"})
    index_line["Series"] = index_column
    fund_line = months.loc[months["return"].notna(), ["Date", "Period", "return"]].rename(
        columns={"return": "Return"}
    )
    fund_line["Series"] = check.label
    history = pd.concat([index_line, fund_line], ignore_index=True)

    marks = issue_markers(check)
    rules = marks[marks["Issue"].isin(RULE_ISSUES)] if not marks.empty else marks
    points = marks[marks["Issue"].isin(POINT_SHAPES)] if not marks.empty else marks
    present = [name for name in ISSUE_ORDER if name in set(marks["Issue"])]
    point_issues = [name for name in present if name in POINT_SHAPES]

    zero = (
        alt.Chart(pd.DataFrame({"Return": [0.0]}))
        .mark_rule(color="#E4E4E4", strokeWidth=1)
        .encode(y="Return:Q")
    )
    lines = (
        alt.Chart(history)
        .mark_line(strokeWidth=1.6)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y(
                "Return:Q",
                title="Monthly total return",
                axis=alt.Axis(format="%"),
            ),
            color=alt.Color(
                "Series:N",
                title=None,
                scale=alt.Scale(
                    domain=[index_column, check.label],
                    range=[INDEX_COLOR, FUND_COLOR],
                ),
            ),
            strokeDash=alt.StrokeDash(
                "Series:N",
                title=None,
                scale=alt.Scale(
                    domain=[index_column, check.label],
                    range=[[5, 3], [1, 0]],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Period:N", title="Month"),
                alt.Tooltip("Series:N"),
                alt.Tooltip("Return:Q", title="Return", format=".2%"),
            ],
        )
    )

    layers: list[alt.Chart] = [zero, lines]
    if not rules.empty:
        layers.append(
            alt.Chart(rules)
            .mark_rule(strokeWidth=1.5)
            .encode(
                x="Date:T",
                color=_issue_color(present, legend=points.empty),
                strokeDash=alt.StrokeDash(
                    "Issue:N",
                    scale=alt.Scale(
                        domain=present,
                        range=[[4, 3] if name == ISSUE_GAP else [1, 0] for name in present],
                    ),
                    legend=None,
                ),
                tooltip=_issue_tooltip(with_return=False),
            )
        )
    if not points.empty:
        layers.append(
            alt.Chart(points)
            .mark_point(filled=True, size=90, stroke="white", strokeWidth=1)
            .encode(
                x="Date:T",
                y="Return:Q",
                color=_issue_color(present, legend=True),
                shape=alt.Shape(
                    "Issue:N",
                    title="Issue",
                    scale=alt.Scale(
                        domain=point_issues,
                        range=[POINT_SHAPES[name] for name in point_issues],
                    ),
                    legend=None,
                ),
                tooltip=_issue_tooltip(with_return=True),
            )
        )

    chart = alt.layer(*layers)
    if len(layers) > 2:
        chart = chart.resolve_scale(color="independent").resolve_legend(color="independent")
    return chart.properties(
        width=720,
        height=280,
        title=alt.Title(check.label, subtitle=_subtitle(check)),
    )


def _issue_color(present: list[str], *, legend: bool) -> alt.Color:
    return alt.Color(
        "Issue:N",
        title="Issue",
        scale=alt.Scale(
            domain=present,
            range=[ISSUE_COLORS[ISSUE_ORDER.index(name)] for name in present],
        ),
        legend=alt.Legend(title="Issue") if legend else None,
    )


def _issue_tooltip(*, with_return: bool) -> list[alt.Tooltip]:
    fields = [
        alt.Tooltip("Period:N", title="Month"),
        alt.Tooltip("Issue:N"),
    ]
    if with_return:
        fields.append(alt.Tooltip("Return:Q", title="Return", format=".2%"))
    fields.append(alt.Tooltip("Detail:N"))
    return fields
