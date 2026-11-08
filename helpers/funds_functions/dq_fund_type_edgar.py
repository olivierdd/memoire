"""EDGAR-backed proof for fund management style (Active vs Passive / index fund)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from helpers.funds_functions.fetch_edgar_filing_facts import (
    INDEX_FUND_LABEL,
    MANAGEMENT_STYLE_ACTIVE,
    MANAGEMENT_STYLE_PASSIVE,
    load_filing_facts_cache,
)
from helpers.funds_functions.map_edgar_tickers import resolve_cache_path

DEFAULT_CACHE = Path("cache") / "dq-fund_type-edgar.json"
FUND_TYPE_ACTIVE = "Active"
FUND_TYPE_PASSIVE = "Passive"

__all__ = [
    "FUND_TYPE_ACTIVE",
    "FUND_TYPE_PASSIVE",
    "build_dq_fund_type_edgar_cache",
    "dq_fund_type_edgar",
    "evaluate_fund_row",
    "fund_type_mismatches_dataframe",
    "load_dq_fund_type_cache",
    "normalize_lipper_fund_type",
    "proof_fund_type_from_ncen",
    "save_dq_fund_type_cache",
    "summarize_lipper_edgar_fund_type_comparison",
]


def normalize_lipper_fund_type(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered == "active":
        return FUND_TYPE_ACTIVE
    if lowered == "passive":
        return FUND_TYPE_PASSIVE
    return text


def _empty_proof() -> dict[str, Any]:
    return {
        "classification": None,
        "source": "none",
        "logic": "No evidence available.",
        "evidence": {},
    }


def _ncen_series_entry(filing_facts: dict, series_id: str | None) -> dict[str, Any] | None:
    if not series_id:
        return None
    entry = filing_facts.get(str(series_id))
    if not isinstance(entry, dict):
        return None
    n_cen = entry.get("n_cen")
    return n_cen if isinstance(n_cen, dict) else None


def proof_fund_type_from_ncen(n_cen: dict[str, Any]) -> dict[str, Any]:
    fund_types = n_cen.get("fund_types")
    series = n_cen.get("series") if isinstance(n_cen.get("series"), dict) else {}

    evidence: dict[str, Any] = {
        "series_id": series.get("series_id"),
        "series_name": series.get("name"),
        "n_cen_accession_number": n_cen.get("accession_number"),
        "n_cen_filing_date": n_cen.get("filing_date"),
        "n_cen_report_date": n_cen.get("report_date"),
    }

    if not isinstance(fund_types, dict) or "is_index_fund" not in fund_types:
        evidence["fund_types_enriched"] = False
        return {
            "classification": None,
            "source": "edgar_n_cen",
            "logic": (
                "N-CEN is cached for this series but fundTypes / indexFundInfo were not "
                "parsed yet. Re-run fetch_edgar_filing_facts to backfill fund_types."
            ),
            "evidence": evidence,
        }

    labels = list(fund_types.get("labels") or [])
    is_index_fund = bool(fund_types.get("is_index_fund"))
    management_style = fund_types.get("management_style")
    evidence.update(
        {
            "fund_types_enriched": True,
            "fund_type_labels": labels,
            "is_index_fund": is_index_fund,
            "management_style_ncen": management_style,
            "index_fund_info": fund_types.get("index_fund_info"),
        }
    )

    if is_index_fund:
        logic = (
            f"N-CEN fundTypes include {INDEX_FUND_LABEL!r} "
            "(indexFundInfo on the annual census filing)."
        )
        return {
            "classification": FUND_TYPE_PASSIVE,
            "source": "edgar_n_cen",
            "logic": logic,
            "evidence": evidence,
        }

    if management_style == MANAGEMENT_STYLE_ACTIVE:
        if labels:
            logic = (
                "N-CEN fundTypes are present and do not include Index Fund; "
                f"labels reported: {labels!r}."
            )
        else:
            logic = (
                "N-CEN legacy fundType is N/A or fundTypes omit Index Fund; "
                "treated as not an index fund (actively managed for Lipper comparison)."
            )
        return {
            "classification": FUND_TYPE_ACTIVE,
            "source": "edgar_n_cen",
            "logic": logic,
            "evidence": evidence,
        }

    if management_style == MANAGEMENT_STYLE_PASSIVE:
        return {
            "classification": FUND_TYPE_PASSIVE,
            "source": "edgar_n_cen",
            "logic": "N-CEN management_style is Passive.",
            "evidence": evidence,
        }

    return {
        "classification": None,
        "source": "edgar_n_cen",
        "logic": "N-CEN fundTypes present but active/passive could not be determined.",
        "evidence": evidence,
    }


def evaluate_fund_row(
    *,
    isin: str,
    name: Any,
    lipper_fund_type: Any,
    market_identifier: Any,
    edgartools_series_id: Any,
    filing_facts: dict,
) -> dict[str, Any]:
    series_id = (
        str(edgartools_series_id).strip()
        if isinstance(edgartools_series_id, str) and edgartools_series_id.strip()
        else None
    )
    ticker = (
        str(market_identifier).strip().upper()
        if isinstance(market_identifier, str) and market_identifier.strip()
        else None
    )

    n_cen = _ncen_series_entry(filing_facts, series_id)
    fund_type_proof = (
        proof_fund_type_from_ncen(n_cen)
        if n_cen
        else {
            **_empty_proof(),
            "logic": (
                "No N-CEN slice in cache for this series "
                "(missing EDGAR match or filing facts)."
            ),
        }
    )

    lipper_norm = normalize_lipper_fund_type(lipper_fund_type)
    edgar_norm = fund_type_proof.get("classification")
    match = None
    if lipper_norm in (FUND_TYPE_ACTIVE, FUND_TYPE_PASSIVE) and edgar_norm is not None:
        match = lipper_norm == edgar_norm

    return {
        "isin": isin,
        "name": None if pd.isna(name) else name,
        "market_identifier": ticker,
        "edgartools_series_id": series_id,
        "lipper_fund_type": None if pd.isna(lipper_fund_type) else lipper_fund_type,
        "fund_type": fund_type_proof,
        "comparison": {
            "lipper_fund_type_normalized": lipper_norm,
            "edgar_fund_type_normalized": edgar_norm,
            "lipper_matches_edgar_fund_type": match,
        },
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def load_dq_fund_type_cache(cache_path: Path | None = None) -> dict:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_dq_fund_type_cache(cache: dict, cache_path: Path | None = None) -> Path:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, default=str) + "\n")
    return path


def build_dq_fund_type_edgar_cache(
    funds: pd.DataFrame,
    *,
    cache_path: Path | None = None,
    filing_facts_path: Path | None = None,
) -> dict[str, Any]:
    filing_facts = load_filing_facts_cache(filing_facts_path)

    records: dict[str, Any] = {}
    for _, row in funds.iterrows():
        isin = row.get("ISIN")
        if pd.isna(isin) or not str(isin).strip():
            continue
        isin_key = str(isin).strip()
        records[isin_key] = evaluate_fund_row(
            isin=isin_key,
            name=row.get("Name"),
            lipper_fund_type=row.get("fund_type"),
            market_identifier=row.get("market_identifier"),
            edgartools_series_id=row.get("edgartools_series_id"),
            filing_facts=filing_facts,
        )

    cache = {
        "records": records,
        "meta": {
            "fund_count": len(records),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
    save_dq_fund_type_cache(cache, cache_path)
    return cache


def summarize_lipper_edgar_fund_type_comparison(
    cache: dict | None = None,
    cache_path: Path | None = None,
) -> dict[str, int]:
    if cache is None:
        cache = load_dq_fund_type_cache(cache_path)
    records = cache.get("records") if isinstance(cache, dict) else {}
    if not isinstance(records, dict):
        records = {}

    match = 0
    mismatch = 0
    no_edgar_fund_type = 0
    lipper_not_labeled = 0

    for row in records.values():
        if not isinstance(row, dict):
            continue
        edgar_type = (row.get("fund_type") or {}).get("classification")
        lipper_norm = (row.get("comparison") or {}).get("lipper_fund_type_normalized")
        if lipper_norm not in (FUND_TYPE_ACTIVE, FUND_TYPE_PASSIVE):
            lipper_not_labeled += 1
        if not edgar_type:
            no_edgar_fund_type += 1
            continue
        lipper_match = (row.get("comparison") or {}).get("lipper_matches_edgar_fund_type")
        if lipper_match is True:
            match += 1
        elif lipper_match is False:
            mismatch += 1

    return {
        "total_funds": len(records),
        "lipper_edgar_match": match,
        "lipper_edgar_mismatch": mismatch,
        "no_edgar_fund_type": no_edgar_fund_type,
        "lipper_not_active_or_passive": lipper_not_labeled,
    }


def fund_type_mismatches_dataframe(
    cache: dict | None = None,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    if cache is None:
        cache = load_dq_fund_type_cache(cache_path)
    records = cache.get("records") if isinstance(cache, dict) else {}
    rows: list[dict[str, Any]] = []
    if not isinstance(records, dict):
        return pd.DataFrame(rows)

    for isin, row in records.items():
        if not isinstance(row, dict):
            continue
        if (row.get("comparison") or {}).get("lipper_matches_edgar_fund_type") is False:
            rows.append(
                {
                    "ISIN": isin,
                    "Name": row.get("name"),
                    "market_identifier": row.get("market_identifier"),
                    "lipper_fund_type": row.get("lipper_fund_type"),
                    "edgar_fund_type": (row.get("fund_type") or {}).get("classification"),
                    "fund_type_source": (row.get("fund_type") or {}).get("source"),
                    "fund_type_logic": (row.get("fund_type") or {}).get("logic"),
                }
            )
    return pd.DataFrame(rows)


def dq_fund_type_edgar(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """Build active/passive proof for each fund; write ``dq-fund_type-edgar.json``."""
    cache = build_dq_fund_type_edgar_cache(funds, cache_path=cache_path, **kwargs)
    records = cache.get("records") or {}
    with_proof = sum(
        1
        for row in records.values()
        if isinstance(row, dict) and row.get("fund_type", {}).get("classification")
    )
    passive = sum(
        1
        for row in records.values()
        if isinstance(row, dict)
        and row.get("fund_type", {}).get("classification") == FUND_TYPE_PASSIVE
    )
    active = sum(
        1
        for row in records.values()
        if isinstance(row, dict)
        and row.get("fund_type", {}).get("classification") == FUND_TYPE_ACTIVE
    )
    matches = sum(
        1
        for row in records.values()
        if isinstance(row, dict)
        and row.get("comparison", {}).get("lipper_matches_edgar_fund_type") is True
    )
    mismatches = sum(
        1
        for row in records.values()
        if isinstance(row, dict)
        and row.get("comparison", {}).get("lipper_matches_edgar_fund_type") is False
    )
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    print(
        f"Fund type DQ (EDGAR): {len(records)} funds written to {path} "
        f"({with_proof} with N-CEN active/passive proof: {passive} passive, {active} active; "
        f"{matches} Lipper matches, {mismatches} Lipper mismatches)"
    )
    return funds
