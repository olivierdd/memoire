"""Keep the D-Timeseries columns that belong to the remaining funds.

Index columns and the risk-free rate stay. Fund columns stay only when the
fund is still in the selected set. Empty columns are left out.
"""

from __future__ import annotations

import pandas as pd

INDEX_CATEGORY = "Index"
RISK_FREE_CATEGORY = "Risk-free rate"
LABELS = "labels"
INDEX = "index"
RISK_FREE = "risk-free rate"
FUND = "fund"

_TAILS = (
    " - TOT RETURN IND - daily return",
    " - PRICE - daily return",
    " - TOTAL NET ASSETS",
    " - TOT RETURN IND",
    " - PRICE",
)


def _text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    return text or None


def _isin(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    text = text.upper()
    if len(text) == 12 and text[:2].isalpha() and text[2:].isalnum():
        return text
    return None


def _instrument(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    for tail in _TAILS:
        if text.endswith(tail):
            stem = text[: -len(tail)].strip()
            return stem or None
    return text


def _names(values: pd.Series | set[str] | list[str] | None) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, pd.Series):
        values = values.tolist()
    names: set[str] = set()
    for value in values:
        text = _text(value)
        if text is not None and text.lower() != "<na>":
            names.add(text)
    return names


def filter_daily_timeseries(
    daily: pd.DataFrame,
    kept_isins: pd.Series | set[str] | list[str],
    kept_labels: pd.Series | set[str] | list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Return the sheet columns to keep, and a role for each kept column.

    Column 0 is the label column. A column whose category is Index or
    Risk-free rate stays. A fund column stays when its id is one of
    ``kept_isins``, or when it has no ISIN and its instrument name is one of
    ``kept_labels``.
    """
    if len(daily) < 5 or daily.shape[1] < 1:
        raise ValueError("D-Timeseries has no label rows")
    isins = {_isin(value) for value in _names(kept_isins)}
    isins.discard(None)
    labels = _names(kept_labels)
    keep: list[int] = []
    roles: list[str] = []
    for position in range(daily.shape[1]):
        if position == 0:
            keep.append(position)
            roles.append(LABELS)
            continue
        category = _text(daily.iat[2, position])
        if category == INDEX_CATEGORY:
            keep.append(position)
            roles.append(INDEX)
            continue
        if category == RISK_FREE_CATEGORY:
            keep.append(position)
            roles.append(RISK_FREE)
            continue
        identifier = _isin(daily.iat[0, position])
        if identifier is not None and identifier in isins:
            keep.append(position)
            roles.append(FUND)
            continue
        instrument = _instrument(daily.iat[1, position])
        if identifier is None and instrument is not None and instrument in labels:
            keep.append(position)
            roles.append(FUND)
    filtered = daily.iloc[:, keep].copy()
    filtered.columns = range(filtered.shape[1])
    return filtered, roles
