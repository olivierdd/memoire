"""Decision rules for Passive, Active, Other, and Unknown.

The first decisive source wins. None from the N-CEN step means the prospectus
steps still run. A benchmark name on its own does not decide.
"""

from __future__ import annotations

import re
from typing import Any

from helpers.funds_functions.fetch_edgar_filing_facts import parse_ncen_fund_types_for_series

OTHER_FUND_TYPES = {"Target Date Fund", "Fund of Funds", "Interval Fund"}
STYLE_PASSIVE = "Passive"
STYLE_ACTIVE = "Active"
STYLE_OTHER = "Other"
STYLE_UNKNOWN = "Unknown"
JEV_CONFIDENCE_MIN = 0.6

PASSIVE_LANGUAGE = re.compile(
    r"not actively managed|passively managed|index fund|"
    r"seeks to track|seek to track|"
    r"tracks the (?:performance|index)|track the performance|"
    r"replicate[sd]? the|matching the performance of|"
    r"approximat\w* the .{0,80}?index|"
    r"before fees and expenses",
    re.IGNORECASE | re.DOTALL,
)
ACTIVE_LANGUAGE = re.compile(
    r"(?<!not )actively managed|"
    r"growth of capital|capital growth|capital appreciation|"
    r"outperform|security selection|"
    r"(?:fund|portfolio) invests (?:primarily|principally) in "
    r"(?:common stocks|equity securities|companies)",
    re.IGNORECASE,
)
STRATEGY_PARAGRAPH = re.compile(
    r"(?:the |this )?(?:fund|portfolio) invests\b.{0,900}",
    re.IGNORECASE | re.DOTALL,
)
OBJECTIVE_SENTENCE = re.compile(
    r"investment objective\b.{0,350}",
    re.IGNORECASE | re.DOTALL,
)


def style_from_jev_choice(choice: str, confidence: float) -> str | None:
    """Accept a Jev choice only when it is one of the labels and confidence is high enough."""
    if choice not in {STYLE_PASSIVE, STYLE_ACTIVE, STYLE_OTHER}:
        return None
    if confidence < JEV_CONFIDENCE_MIN:
        return None
    return choice


def label_from_ncen(parsed: dict[str, Any] | None) -> tuple[str | None, str]:
    """Apply the N-CEN step. None means the prospectus steps still run."""
    if parsed is None:
        return None, "series absent from the latest N-CEN"
    labels = [str(label) for label in (parsed.get("labels") or [])]
    if parsed.get("is_index_fund") or "Index Fund" in labels:
        return STYLE_PASSIVE, "N-CEN indexFundInfo fund type is Index Fund"
    other = [label for label in labels if label in OTHER_FUND_TYPES]
    if other:
        return STYLE_OTHER, f"N-CEN fund type is {other[0]}"
    if labels:
        shown = ", ".join(labels)
        return STYLE_ACTIVE, f"N-CEN fund type is {shown} and has no indexFundInfo"
    return None, "N-CEN fund type is N/A"


def label_from_objective(text: str | None) -> tuple[str | None, str]:
    """Apply the prospectus phrase step. A benchmark name alone does not decide."""
    if not text or not str(text).strip():
        return None, "no investment objective text"
    body = str(text)
    if PASSIVE_LANGUAGE.search(body):
        return STYLE_PASSIVE, "prospectus says the fund tracks an index"
    if ACTIVE_LANGUAGE.search(body):
        return STYLE_ACTIVE, "prospectus describes security selection or outperformance"
    return None, "prospectus has no decisive phrase"


def prospectus_excerpt(text: str, series_name: str | None) -> str:
    """Objective sentence plus the strategy paragraph, skipping the table of contents."""
    lines = []
    for line in str(text).splitlines():
        stripped = line.strip()
        if not stripped or re.search(r"\.{3,}", stripped):
            continue
        lines.append(stripped)
    prose = "\n".join(lines)
    start = 0
    name = (series_name or "").strip()
    if name:
        at = prose.lower().find(name.lower())
        if at >= 0:
            start = at
    region = prose[start : start + 80_000]
    parts: list[str] = []
    objective = OBJECTIVE_SENTENCE.search(region)
    if objective:
        parts.append(objective.group(0))
    strategy = STRATEGY_PARAGRAPH.search(region)
    if strategy:
        parts.append(strategy.group(0))
    return "\n".join(parts)


def label_from_statutory_text(
    text: str | None, series_name: str | None
) -> tuple[str | None, str]:
    """Read the 485 objective and principal strategy, not the table of contents."""
    if not text or not str(text).strip():
        return None, "no statutory prospectus text"
    excerpt = prospectus_excerpt(text, series_name)
    if not excerpt:
        return None, "statutory prospectus has no strategy paragraph"
    return label_from_objective(excerpt)


def decide_series(
    *,
    ncen_xml: str | None,
    series_id: str,
    objective: str | None,
    statutory_text: str | None,
    series_name: str | None,
) -> dict[str, str]:
    """Run the three sources for one series. Callers supply the already fetched text."""
    parsed = parse_ncen_fund_types_for_series(ncen_xml, series_id) if ncen_xml else None
    label, detail = label_from_ncen(parsed)
    if label:
        return {"style": label, "source": "N-CEN", "detail": detail}

    reasons = [detail]
    label, detail = label_from_objective(objective)
    if label:
        return {"style": label, "source": "497K", "detail": detail}
    reasons.append(detail)

    label, detail = label_from_statutory_text(statutory_text, series_name)
    if label:
        return {"style": label, "source": "485", "detail": detail}
    reasons.append(detail)
    return {"style": STYLE_UNKNOWN, "source": "none", "detail": "; ".join(reasons)}
