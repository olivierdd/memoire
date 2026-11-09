"""Keep one share class per EDGAR series.

The kept class is the primary class. A reported AUM wins. When no class in the
series has an AUM, or the largest AUM is shared, the EDGAR class name decides.
The smallest class id breaks a remaining tie. A row with no series id stays.
"""

from __future__ import annotations

import html
import re

import pandas as pd

AUM_COLUMN = "Fund Total Assets under Management"
RULE_LARGEST_AUM = "largest aum"
RULE_CLASS_RANK = "class rank"
RULE_SMALLEST_CLASS_ID = "smallest class id"
RULE_ONLY_CLASS = "only class"
RULE_NO_SERIES = "no series"

_UNSUFFIXED = 0
_INVESTOR = 1
_AAA = 2
_CLASS_A = 3
_ADMIRAL = 4
_INSTITUTIONAL = 5
_CLASS_Y = 6
_OTHER = 7


def _text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "<na>"}:
        return None
    return text


def _norm(value: object) -> str:
    text = html.unescape(_text(value) or "").lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _tokens(value: object) -> tuple[str, ...]:
    text = _norm(value)
    return tuple(text.split()) if text else ()


def _class_number(value: object) -> int:
    digits = "".join(character for character in (_text(value) or "") if character.isdigit())
    return int(digits) if digits else 10**12


def class_priority(row: pd.Series) -> int:
    """Lower is the preferred retail class when AUM does not decide."""
    class_name = _norm(row.get("edgar_class_name"))
    series_name = _norm(row.get("edgar_series_name"))
    tokens = _tokens(row.get("edgar_class_name"))
    company = _norm(row.get("edgar_company_name"))
    if class_name and class_name == series_name and "advisor" not in tokens:
        return _UNSUFFIXED
    if "investor" in tokens or "ordinary" in tokens or tokens == ("inv",):
        return _INVESTOR
    if "aaa" in tokens and "gabelli" in f"{company} {series_name} {class_name}":
        return _AAA
    if "529" not in tokens and (
        tokens in {("a",), ("class", "a"), ("a", "class"), ("a", "shares")}
        or tokens[-2:] == ("class", "a")
    ):
        return _CLASS_A
    if "admiral" in tokens:
        return _ADMIRAL
    if "institutional" in tokens or tokens[-2:] in {("class", "i"), ("i", "class"), ("i", "shares")}:
        return _INSTITUTIONAL
    if tokens in {("y",), ("class", "y"), ("y", "class"), ("y", "shares")} or tokens[-2:] == ("class", "y"):
        return _CLASS_Y
    return _OTHER


def _winner_rule(group: pd.DataFrame) -> tuple[object, str]:
    aum = pd.to_numeric(group.get(AUM_COLUMN), errors="coerce")
    if not isinstance(aum, pd.Series):
        aum = pd.Series(pd.NA, index=group.index, dtype="Float64")
    reported = aum.notna()
    candidates = group.loc[reported] if reported.any() else group
    rule = RULE_LARGEST_AUM if reported.any() else RULE_CLASS_RANK
    if reported.any():
        candidates = candidates.loc[aum.loc[candidates.index].eq(aum.max())]
        if len(candidates) == 1:
            return candidates.index[0], RULE_LARGEST_AUM
        rule = RULE_CLASS_RANK
    priority = candidates.apply(class_priority, axis=1)
    candidates = candidates.loc[priority.eq(priority.min())]
    if len(candidates) == 1:
        return candidates.index[0], rule
    order = candidates["edgartools_class_id"].map(_class_number).sort_values()
    return order.index[0], RULE_SMALLEST_CLASS_ID


def select_primary_share_class(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the kept funds and the share classes removed as duplicates.

    The kept frame includes ``primary_rule``. The dropped frame includes
    ``kept_isin`` for the class that was kept in that series.
    """
    required = ["edgartools_series_id", "edgartools_class_id"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    kept_index: list[object] = []
    rules: dict[object, str] = {}
    dropped_kept_isin: dict[object, str | None] = {}
    grouped: dict[str, list[object]] = {}
    alone: list[object] = []
    for index, series_id in zip(frame.index, frame["edgartools_series_id"].tolist(), strict=True):
        series_key = _text(series_id)
        if series_key is None:
            alone.append(index)
            continue
        grouped.setdefault(series_key, []).append(index)

    for index in alone:
        kept_index.append(index)
        rules[index] = RULE_NO_SERIES

    for indexes in grouped.values():
        group = frame.loc[indexes]
        if len(group) == 1:
            kept_index.append(group.index[0])
            rules[group.index[0]] = RULE_ONLY_CLASS
            continue
        winner, rule = _winner_rule(group)
        kept_index.append(winner)
        rules[winner] = rule
        kept_isin = _text(frame.at[winner, "ISIN"]) if "ISIN" in frame.columns else None
        for index in group.index:
            if index != winner:
                dropped_kept_isin[index] = kept_isin

    kept = frame.loc[kept_index].copy()
    kept["primary_rule"] = [rules[index] for index in kept.index]
    dropped = frame.loc[list(dropped_kept_isin)].copy()
    if not dropped.empty:
        dropped["kept_isin"] = [dropped_kept_isin[index] for index in dropped.index]
    elif "ISIN" in frame.columns:
        dropped["kept_isin"] = pd.Series(dtype="object")
    return kept, dropped
