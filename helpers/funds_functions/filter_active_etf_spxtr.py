"""Restrict Active ETFs to S&P 500 total-return mandates.

Passive funds and mutual funds are out of scope and always kept. Active ETFs are
kept only when the Lipper benchmark and the product description are consistent
with an S&P 500 TR (or active-equity-versus-S&P-500) mandate, after excluding
structured-outcome, options-income, hedged, and other overlay products.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

SPXTR_TICKER = ".SPXTR"
WRAPPER_ETF = "etf"
STYLE_ACTIVE = "active"
ASSET_EQUITY = "equity"

REASON_OUT_OF_SCOPE = "out of scope (not an Active ETF)"
REASON_KEEP_SPXTR = "Keep — Lipper .SPXTR and Equity active ETF"
REASON_KEEP_OBJECTIVE = "Keep — Equity active ETF; S&P 500 mandate in objective/name"
REASON_DROP_ASSET = "Drop — Active ETF asset class is not Equity"
REASON_DROP_BENCH = "Drop — Lipper Benchmark Ticker is not .SPXTR"
REASON_DROP_PRODUCT = "Drop — structured, options, hedged, or non-TR S&P product"
REASON_DROP_NO_MANDATE = "Drop — no S&P 500 TR / outperform mandate"

_WRONG_BENCH = frozenset(
    {
        ".INX",
        ".SPVQDTR",
        ".SPXEW",
        ".BCUSA",
        ".NQ96DIVUSX",
    }
)

_STRUCTURED = re.compile(
    r"buffer|defined\s+outcome|structured\s+outcome|barrier|accelerator|"
    r"autocall|shield|protection|power\s+buffer|uncapped\s+accelerat|"
    r"target\s*10,?000|outcome\s+period",
    re.I,
)
_OPTIONS_INCOME = re.compile(
    r"options?\s+income|premium\s+income|covered\s+call|buy[-\s]?write|"
    r"equity\s+premium|no\s+dividend\s+target|enhanced\s+options|"
    r"target\s+income|defensive\s+income",
    re.I,
)
_HEDGED = re.compile(
    r"hedged\s+equity|downside\s+hedged|veqtor|risk[-\s]?managed\s+growth",
    re.I,
)
_NON_TR_STRATEGY = re.compile(
    r"shiller\s+cape|cape\s+us\s+sector|stocks?,?\s+bonds?\s+(?:and|&)\s+gold|"
    r"bond\s+innovation|equal\s*weight",
    re.I,
)
_ACTIVE_SPX_MANDATE = re.compile(
    r"outperform(?:ing)?\s+the\s+s\s*&\s*p\s*500(?:\s*total\s*return)?"
    r"|s\s*&\s*p\s*500\s*total\s*return"
    r"|buys?\s+all\s+500\s+stocks\s+in\s+the\s+s\s*&\s*p"
    r"|historical\s+weight.{0,60}s\s*&\s*p\s*500"
    r"|sectors?\s+of\s+the\s+s\s*&\s*p\s*500"
    r"|each\s+equity\s+sector.{0,80}s\s*&\s*p\s*500"
    r"|reweights?\s+them.{0,40}(?:cheaper|expensive)"
    r"|dynamic\s+stock\s*/\s*sector\s+allocation.{0,100}s\s*&\s*p\s*500",
    re.I,
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
    if not text or text.lower() in {"none", "nan", "<na>"}:
        return None
    return text


def _norm_key(value: object) -> str:
    text = _text(value)
    return text.casefold() if text else ""


def _is_active_etf(row: pd.Series) -> bool:
    return (
        _norm_key(row.get("fund_type")) == STYLE_ACTIVE
        and _norm_key(row.get("fund_wrapper")) == WRAPPER_ETF
    )


def _is_equity_asset(row: pd.Series) -> bool:
    asset = row.get("Fund Type")
    if asset is None or (isinstance(asset, float) and pd.isna(asset)):
        asset = row.get("fund_type_sheet")
    return _norm_key(asset) == ASSET_EQUITY


def _benchmark_ticker(row: pd.Series) -> str | None:
    return _text(row.get("Benchmark Ticker"))


def load_trackinsight_objectives(
    cache_path: Path | None = None,
) -> dict[str, str]:
    """Map ISIN → investment_objective from the Trackinsight static cache."""
    path = cache_path or Path("cache") / "cache-trackinsight-static.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    objectives: dict[str, str] = {}
    for record in payload.values():
        if not isinstance(record, dict):
            continue
        isin = _text(record.get("isin") or record.get("isin_1"))
        objective = _text(record.get("investment_objective"))
        if isin and objective:
            objectives[isin] = objective
    return objectives


def _product_text(row: pd.Series, objectives: dict[str, str]) -> str:
    name = _text(row.get("Name")) or ""
    isin = _text(row.get("ISIN")) or ""
    objective = objectives.get(isin, "")
    return f"{name}\n{objective}"


def _excluded_product(text: str) -> bool:
    return bool(
        _STRUCTURED.search(text)
        or _OPTIONS_INCOME.search(text)
        or _HEDGED.search(text)
        or _NON_TR_STRATEGY.search(text)
    )


def evaluate_active_etf_row(
    row: pd.Series,
    *,
    objectives: dict[str, str] | None = None,
) -> dict[str, object]:
    """Return keep flag and reason for one fund row."""
    objectives = objectives or {}
    if not _is_active_etf(row):
        return {"keep": True, "reason": REASON_OUT_OF_SCOPE, "in_scope": False}

    text = _product_text(row, objectives)
    ticker = _benchmark_ticker(row)

    if not _is_equity_asset(row):
        return {"keep": False, "reason": REASON_DROP_ASSET, "in_scope": True}
    if ticker is not None and ticker != SPXTR_TICKER:
        label = ticker if ticker in _WRONG_BENCH or ticker.startswith(".") else ticker
        return {
            "keep": False,
            "reason": f"{REASON_DROP_BENCH} ({label})",
            "in_scope": True,
        }
    if _excluded_product(text):
        return {"keep": False, "reason": REASON_DROP_PRODUCT, "in_scope": True}

    if ticker == SPXTR_TICKER:
        return {"keep": True, "reason": REASON_KEEP_SPXTR, "in_scope": True}
    if _ACTIVE_SPX_MANDATE.search(text):
        return {"keep": True, "reason": REASON_KEEP_OBJECTIVE, "in_scope": True}
    return {"keep": False, "reason": REASON_DROP_NO_MANDATE, "in_scope": True}


def filter_active_etf_spxtr(
    funds: pd.DataFrame,
    *,
    objectives: dict[str, str] | None = None,
    cache_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Keep funds that pass the Active-ETF S&P 500 TR screen.

    Returns ``(kept, dropped, review)`` where ``review`` is every Active ETF
    (kept or dropped) with ``spxtr_screen_keep`` and ``spxtr_screen_reason``.
    """
    if objectives is None:
        objectives = load_trackinsight_objectives(cache_path)

    decisions = funds.apply(
        lambda row: evaluate_active_etf_row(row, objectives=objectives),
        axis=1,
        result_type="expand",
    )
    review = funds.copy()
    review["spxtr_screen_keep"] = decisions["keep"].astype(bool)
    review["spxtr_screen_reason"] = decisions["reason"].astype("string")
    review["spxtr_screen_in_scope"] = decisions["in_scope"].astype(bool)

    kept = review.loc[review["spxtr_screen_keep"]].drop(
        columns=["spxtr_screen_in_scope"],
        errors="ignore",
    )
    # Working selection carries the decision columns for audit continuity.
    dropped = review.loc[
        review["spxtr_screen_in_scope"] & ~review["spxtr_screen_keep"]
    ].copy()
    return kept, dropped, review
