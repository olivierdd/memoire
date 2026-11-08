"""Parse formatted regression comparison deltas for export tolerances."""

from __future__ import annotations

from typing import Any

import pandas as pd

# Metrics whose CSV deltas use Python percent formatting ({:.2%}, {:.4%}):
# stored values are decimals; displayed values are percentage points after stripping "%".
_PERCENT_DELTA_METRICS = frozenset(
    {
        "Alpha (monthly)",
        "Alpha (annualized, ×12)",
        "Annualized tracking error",
        "Annualized excess return",
        "Tracking error (annualized)",
        "Net alpha (annualized)",
        "Gross alpha (annualized)",
        "Excess return (annualized)",
    }
)

# Plain numeric deltas (no percent sign in normal exports).
_PLAIN_DELTA_METRICS = frozenset(
    {
        "Beta",
        "R²",
        "Information ratio",
        "Correlation",
        "Months",
    }
)


def parse_regression_delta(metric: str, raw: Any) -> float | None:
    """Return a float delta in export-comparison units for ``metric``.

    - Beta, R², information ratio: absolute delta (unitless).
    - Alpha (monthly): percentage points per month (pp/mo), e.g. ``-0.2022%`` → ``-0.2022``.
    - Annualized percent metrics (tracking error, net alpha, …): annualized
      percentage points (pp), e.g. ``2.05%`` → ``2.05``.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = text.replace(",", "")
    metric = metric.strip()
    has_percent = "%" in text
    text = text.replace("%", "")
    try:
        value = float(text)
    except ValueError:
        return None
    if metric in _PLAIN_DELTA_METRICS and not has_percent:
        return value
    if metric in _PERCENT_DELTA_METRICS or has_percent:
        return value
    if metric in _PLAIN_DELTA_METRICS:
        return value
    # Unknown metric: if formatted with %, treat as percentage points.
    if has_percent:
        return value
    return value
