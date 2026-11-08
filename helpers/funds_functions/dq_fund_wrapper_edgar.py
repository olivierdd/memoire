"""EDGAR-backed proof for fund wrapper (mutual fund vs ETF) and open-end status."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from helpers.funds_functions.fetch_edgar_filing_facts import (
    load_filing_facts_cache,
    is_open_end_registrant,
)
from helpers.funds_functions.map_edgar_tickers import resolve_cache_path
from helpers.funds_functions.map_financedatabase import load_fd_cache
from helpers.funds_functions.map_yahoo_static import load_yahoo_cache

DEFAULT_CACHE = Path("cache") / "dq-fund_wraper-edgar.json"
WRAPPER_MUTUAL_FUND = "mutual fund"
WRAPPER_ETF = "ETF"

__all__ = [
    "WRAPPER_ETF",
    "WRAPPER_MUTUAL_FUND",
    "build_dq_fund_wrapper_edgar_cache",
    "dq_fund_wrapper_edgar",
    "evaluate_fund_row",
    "fund_wrapper_mismatches_dataframe",
    "load_dq_fund_wrapper_cache",
    "normalize_lipper_wrapper",
    "save_dq_fund_wrapper_cache",
    "summarize_lipper_edgar_wrapper_comparison",
]


def normalize_lipper_wrapper(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered == "etf":
        return WRAPPER_ETF
    if "mutual" in lowered:
        return WRAPPER_MUTUAL_FUND
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


def proof_open_end_from_ncen(n_cen: dict[str, Any]) -> dict[str, Any]:
    classification_type = n_cen.get("registrant_classification_type")
    is_open_end = n_cen.get("is_open_end")
    if is_open_end is None:
        is_open_end = is_open_end_registrant(classification_type)

    evidence = {
        "registrant_classification_type": classification_type,
        "registrant_name": n_cen.get("registrant_name"),
        "n_cen_accession_number": n_cen.get("accession_number"),
        "n_cen_filing_date": n_cen.get("filing_date"),
        "n_cen_report_date": n_cen.get("report_date"),
    }

    if is_open_end is True:
        logic = (
            "N-CEN registrant is classified as N-1A (open-end management investment company)."
        )
        return {
            "classification": True,
            "source": "edgar_n_cen",
            "logic": logic,
            "evidence": evidence,
        }
    if is_open_end is False:
        logic = (
            f"N-CEN registrant classification is {classification_type!r}, not N-1A; "
            "treated as not open-end."
        )
        return {
            "classification": False,
            "source": "edgar_n_cen",
            "logic": logic,
            "evidence": evidence,
        }

    return {
        "classification": None,
        "source": "edgar_n_cen",
        "logic": "N-CEN present but registrant classification type is missing or N/A.",
        "evidence": evidence,
    }


def proof_wrapper_from_ncen(
    n_cen: dict[str, Any],
    market_ticker: str | None,
    open_end: bool | None,
) -> dict[str, Any]:
    series = n_cen.get("series") if isinstance(n_cen.get("series"), dict) else {}
    etf = n_cen.get("etf") if isinstance(n_cen.get("etf"), dict) else None
    has_etf = bool(series.get("has_etf"))

    evidence: dict[str, Any] = {
        "market_ticker": market_ticker,
        "series_id": series.get("series_id"),
        "series_name": series.get("name"),
        "has_etf": has_etf,
        "etf_ticker": etf.get("ticker") if etf else None,
        "etf_exchange": etf.get("exchange") if etf else None,
        "n_cen_accession_number": n_cen.get("accession_number"),
    }

    if open_end is False:
        return {
            "classification": None,
            "source": "edgar_n_cen",
            "logic": (
                "Registrant is not open-end (N-1A); mutual fund vs ETF wrapper labels "
                "apply to open-end vehicles only."
            ),
            "evidence": evidence,
        }

    ticker = (market_ticker or "").strip().upper()
    etf_ticker = (etf.get("ticker") or "").strip().upper() if etf else ""

    if has_etf and etf_ticker and ticker and ticker == etf_ticker:
        return {
            "classification": WRAPPER_ETF,
            "source": "edgar_n_cen",
            "logic": (
                "N-CEN reports an ETF for this series and the fund ticker matches "
                "the N-CEN ETF listing ticker."
            ),
            "evidence": evidence,
        }

    if has_etf and etf_ticker and ticker and ticker != etf_ticker:
        return {
            "classification": WRAPPER_MUTUAL_FUND,
            "source": "edgar_n_cen",
            "logic": (
                "N-CEN reports an ETF for this series but the fund ticker differs from "
                "the N-CEN ETF listing ticker; classified as a mutual-fund share class "
                "of the same series."
            ),
            "evidence": evidence,
        }

    if has_etf and not etf_ticker:
        return {
            "classification": None,
            "source": "edgar_n_cen",
            "logic": (
                "N-CEN marks the series as having an ETF but no ETF ticker was parsed; "
                "cannot assign wrapper at share-class level."
            ),
            "evidence": evidence,
        }

    if not has_etf:
        return {
            "classification": WRAPPER_MUTUAL_FUND,
            "source": "edgar_n_cen",
            "logic": (
                "N-CEN open-end series without an ETF flag supports a mutual fund wrapper."
            ),
            "evidence": evidence,
        }

    return {
        "classification": None,
        "source": "edgar_n_cen",
        "logic": "N-CEN ETF flag set but market ticker missing; cannot match share class.",
        "evidence": evidence,
    }


def proof_wrapper_from_yahoo(yahoo_row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(yahoo_row, dict):
        return _empty_proof()

    quote_type = yahoo_row.get("quote_type")
    evidence = {
        "quote_type": quote_type,
        "symbol": yahoo_row.get("symbol"),
        "legal_type": yahoo_row.get("legal_type"),
        "category_name": yahoo_row.get("category_name"),
    }

    if isinstance(quote_type, str):
        normalized = quote_type.strip().upper()
        if normalized == "ETF":
            return {
                "classification": WRAPPER_ETF,
                "source": "yahoo",
                "logic": "Yahoo quote type is ETF.",
                "evidence": evidence,
            }
        if normalized == "MUTUALFUND":
            return {
                "classification": WRAPPER_MUTUAL_FUND,
                "source": "yahoo",
                "logic": "Yahoo quote type is MUTUALFUND.",
                "evidence": evidence,
            }

    return {
        "classification": None,
        "source": "yahoo",
        "logic": "Yahoo profile present but quote type is not ETF or MUTUALFUND.",
        "evidence": evidence,
    }


def proof_wrapper_from_fmp(fmp: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fmp, dict):
        return _empty_proof()

    profile = fmp.get("profile") if isinstance(fmp.get("profile"), dict) else {}
    info = fmp.get("info") if isinstance(fmp.get("info"), dict) else {}
    evidence = {
        "listed": fmp.get("listed"),
        "profile_is_etf": profile.get("isEtf"),
        "profile_is_fund": profile.get("isFund"),
        "has_etf_info": bool(info),
    }

    if profile.get("isEtf") is True or info:
        return {
            "classification": WRAPPER_ETF,
            "source": "fmp",
            "logic": "FMP profile marks isEtf or ETF info endpoint returned data.",
            "evidence": evidence,
        }
    if profile.get("isEtf") is False:
        return {
            "classification": WRAPPER_MUTUAL_FUND,
            "source": "fmp",
            "logic": "FMP profile isEtf is false.",
            "evidence": evidence,
        }
    if profile.get("isFund") is True:
        return {
            "classification": WRAPPER_MUTUAL_FUND,
            "source": "fmp",
            "logic": "FMP profile isFund is true.",
            "evidence": evidence,
        }

    return {
        "classification": None,
        "source": "fmp",
        "logic": "FMP payload present but no clear ETF or mutual-fund signal.",
        "evidence": evidence,
    }


def evaluate_fund_row(
    *,
    isin: str,
    name: Any,
    lipper_fund_wrapper: Any,
    market_identifier: Any,
    edgartools_series_id: Any,
    filing_facts: dict,
    yahoo_cache: dict,
    fd_cache: dict,
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
    open_end_proof = (
        proof_open_end_from_ncen(n_cen)
        if n_cen
        else {
            **_empty_proof(),
            "logic": "No N-CEN slice in cache for this series (missing EDGAR match or filing facts).",
        }
    )

    wrapper_proof = _empty_proof()
    if n_cen:
        wrapper_proof = proof_wrapper_from_ncen(
            n_cen, ticker, open_end_proof.get("classification")
        )

    if wrapper_proof.get("classification") is None:
        yahoo_row = yahoo_cache.get(ticker) if ticker else None
        yahoo_proof = proof_wrapper_from_yahoo(
            yahoo_row if isinstance(yahoo_row, dict) else None
        )
        if yahoo_proof.get("classification") is not None:
            wrapper_proof = yahoo_proof

    if wrapper_proof.get("classification") is None and ticker:
        fd_row = fd_cache.get(ticker)
        fmp = fd_row.get("fmp") if isinstance(fd_row, dict) else None
        fmp_proof = proof_wrapper_from_fmp(fmp if isinstance(fmp, dict) else None)
        if fmp_proof.get("classification") is not None:
            wrapper_proof = fmp_proof

    lipper_norm = normalize_lipper_wrapper(lipper_fund_wrapper)
    edgar_norm = wrapper_proof.get("classification")
    match = None
    if lipper_norm is not None and edgar_norm is not None:
        match = lipper_norm == edgar_norm

    return {
        "isin": isin,
        "name": None if pd.isna(name) else name,
        "market_identifier": ticker,
        "edgartools_series_id": series_id,
        "lipper_fund_wrapper": None if pd.isna(lipper_fund_wrapper) else lipper_fund_wrapper,
        "open_end": open_end_proof,
        "fund_wrapper": wrapper_proof,
        "comparison": {
            "lipper_wrapper_normalized": lipper_norm,
            "edgar_wrapper_normalized": edgar_norm,
            "lipper_matches_edgar_wrapper": match,
        },
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def load_dq_fund_wrapper_cache(cache_path: Path | None = None) -> dict:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_dq_fund_wrapper_cache(cache: dict, cache_path: Path | None = None) -> Path:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, default=str) + "\n")
    return path


def build_dq_fund_wrapper_edgar_cache(
    funds: pd.DataFrame,
    *,
    cache_path: Path | None = None,
    filing_facts_path: Path | None = None,
    yahoo_cache_path: Path | None = None,
    fd_cache_path: Path | None = None,
) -> dict[str, Any]:
    filing_facts = load_filing_facts_cache(filing_facts_path)
    yahoo_cache = load_yahoo_cache(yahoo_cache_path)
    fd_cache = load_fd_cache(fd_cache_path)

    records: dict[str, Any] = {}
    for _, row in funds.iterrows():
        isin = row.get("ISIN")
        if pd.isna(isin) or not str(isin).strip():
            continue
        isin_key = str(isin).strip()
        records[isin_key] = evaluate_fund_row(
            isin=isin_key,
            name=row.get("Name"),
            lipper_fund_wrapper=row.get("fund_wrapper"),
            market_identifier=row.get("market_identifier"),
            edgartools_series_id=row.get("edgartools_series_id"),
            filing_facts=filing_facts,
            yahoo_cache=yahoo_cache,
            fd_cache=fd_cache,
        )

    cache = {
        "records": records,
        "meta": {
            "fund_count": len(records),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }
    save_dq_fund_wrapper_cache(cache, cache_path)
    return cache


def summarize_lipper_edgar_wrapper_comparison(
    cache: dict | None = None,
    cache_path: Path | None = None,
) -> dict[str, int]:
    """Count Lipper vs EDGAR-derived wrapper agreement from the DQ cache."""
    if cache is None:
        cache = load_dq_fund_wrapper_cache(cache_path)
    records = cache.get("records") if isinstance(cache, dict) else {}
    if not isinstance(records, dict):
        records = {}

    match = 0
    mismatch = 0
    no_edgar_wrapper = 0

    for row in records.values():
        if not isinstance(row, dict):
            continue
        edgar_wrapper = (row.get("fund_wrapper") or {}).get("classification")
        if not edgar_wrapper:
            no_edgar_wrapper += 1
            continue
        lipper_match = (row.get("comparison") or {}).get("lipper_matches_edgar_wrapper")
        if lipper_match is True:
            match += 1
        elif lipper_match is False:
            mismatch += 1

    return {
        "total_funds": len(records),
        "lipper_edgar_match": match,
        "lipper_edgar_mismatch": mismatch,
        "no_edgar_fund_wrapper": no_edgar_wrapper,
    }


def fund_wrapper_mismatches_dataframe(
    cache: dict | None = None,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """Funds where Lipper and EDGAR-derived wrappers disagree."""
    if cache is None:
        cache = load_dq_fund_wrapper_cache(cache_path)
    records = cache.get("records") if isinstance(cache, dict) else {}
    rows: list[dict[str, Any]] = []
    if not isinstance(records, dict):
        return pd.DataFrame(rows)

    for isin, row in records.items():
        if not isinstance(row, dict):
            continue
        if (row.get("comparison") or {}).get("lipper_matches_edgar_wrapper") is not True:
            if (row.get("comparison") or {}).get("lipper_matches_edgar_wrapper") is False:
                rows.append(
                    {
                        "ISIN": isin,
                        "Name": row.get("name"),
                        "market_identifier": row.get("market_identifier"),
                        "lipper_fund_wrapper": row.get("lipper_fund_wrapper"),
                        "edgar_fund_wrapper": (row.get("fund_wrapper") or {}).get(
                            "classification"
                        ),
                        "wrapper_source": (row.get("fund_wrapper") or {}).get("source"),
                        "wrapper_logic": (row.get("fund_wrapper") or {}).get("logic"),
                    }
                )
    return pd.DataFrame(rows)


def dq_fund_wrapper_edgar(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """Build wrapper/open-end proof for each fund; write ``dq-fund_wraper-edgar.json``."""
    cache = build_dq_fund_wrapper_edgar_cache(funds, cache_path=cache_path, **kwargs)
    records = cache.get("records") or {}
    with_open = sum(
        1
        for row in records.values()
        if isinstance(row, dict) and row.get("open_end", {}).get("classification") is True
    )
    with_wrapper = sum(
        1
        for row in records.values()
        if isinstance(row, dict) and row.get("fund_wrapper", {}).get("classification")
    )
    matches = sum(
        1
        for row in records.values()
        if isinstance(row, dict) and row.get("comparison", {}).get("lipper_matches_edgar_wrapper") is True
    )
    mismatches = sum(
        1
        for row in records.values()
        if isinstance(row, dict) and row.get("comparison", {}).get("lipper_matches_edgar_wrapper") is False
    )
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    print(
        f"Fund wrapper DQ (EDGAR): {len(records)} funds written to {path} "
        f"({with_open} open-end, {with_wrapper} with EDGAR/Yahoo/FMP wrapper proof, "
        f"{matches} Lipper matches, {mismatches} Lipper mismatches)"
    )
    return funds
