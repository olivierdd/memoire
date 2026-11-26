"""Keep the D-Timeseries columns that belong to the remaining funds.

Index columns and the risk-free rate stay. Fund columns stay only when the
fund is still in the selected set. Empty columns are left out.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

INDEX_CATEGORY = "Index"
RISK_FREE_CATEGORY = "Risk-free rate"
LABELS = "labels"
INDEX = "index"
RISK_FREE = "risk-free rate"
FUND = "fund"
FEE_ROW = 3
ID_ROW = 0
TER_COLUMNS = (
    "Total Expense Ratio",
    "ds.total_expense_ratio",
    "total_expense_ratio",
)

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


def coerce_fee_value(value: Any) -> float | None:
    """Parse a TER / fee cell to float; accept European comma decimals."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return None if math.isnan(number) else number
    text = str(value).strip()
    if not text or text.lower() in {"<na>", "nan", "none", "–", "-"}:
        return None
    text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return None if math.isnan(number) else number


def fee_from_fund_row(row: pd.Series | dict[str, Any]) -> float | None:
    """Read TER from a fund row under any known column name."""
    getter = row.get if isinstance(row, dict) else row.get
    for column in TER_COLUMNS:
        if isinstance(row, pd.Series) and column not in row.index:
            continue
        if isinstance(row, dict) and column not in row:
            continue
        fee = coerce_fee_value(getter(column))
        if fee is not None:
            return fee
    return None


def ter_by_isin(funds: pd.DataFrame) -> dict[str, float]:
    """Map ISIN → TER from a Funds / Funds final frame."""
    if "ISIN" not in funds.columns:
        return {}
    mapping: dict[str, float] = {}
    for _, row in funds.iterrows():
        isin = _isin(row.get("ISIN"))
        if isin is None or isin in mapping:
            continue
        fee = fee_from_fund_row(row)
        if fee is not None:
            mapping[isin] = fee
    return mapping


def backfill_fees_from_funds(
    daily: pd.DataFrame,
    funds: pd.DataFrame,
    *,
    fee_row: int = FEE_ROW,
    id_row: int = ID_ROW,
) -> tuple[pd.DataFrame, int]:
    """Fill blank D-Timeseries fee cells from the fund TER by ISIN.

    Returns the (possibly copied) frame and the number of cells written.
    """
    if len(daily) <= fee_row or daily.shape[1] < 1:
        return daily, 0
    ters = ter_by_isin(funds)
    if not ters:
        return daily, 0
    out = daily.copy()
    filled = 0
    for position in range(1, out.shape[1]):
        isin = _isin(out.iat[id_row, position])
        if isin is None or isin not in ters:
            continue
        if coerce_fee_value(out.iat[fee_row, position]) is not None:
            continue
        out.iat[fee_row, position] = ters[isin]
        filled += 1
    return out, filled


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
