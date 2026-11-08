"""EDGAR-backed proof for S&P 500 benchmark (and TR / Price variants) vs Lipper."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from helpers.funds_functions.fetch_edgar_filing_facts import load_filing_facts_cache
from helpers.funds_functions.map_edgar_tickers import resolve_cache_path

DEFAULT_CACHE = Path("cache") / "dq-fund_benchmark-edgar.json"

SP500_TOTAL_RETURN = "sp500_total_return"
SP500_PRICE = "sp500_price"
SP500_UNSPECIFIED = "sp500_unspecified"

__all__ = [
    "SP500_PRICE",
    "SP500_TOTAL_RETURN",
    "SP500_UNSPECIFIED",
    "build_dq_fund_benchmark_edgar_cache",
    "classify_sp500_benchmark_label",
    "dq_fund_benchmark_edgar",
    "evaluate_fund_row",
    "is_sp500_series_name",
    "load_dq_fund_benchmark_cache",
    "normalize_lipper_benchmark",
    "proof_sp500_benchmark",
    "save_dq_fund_benchmark_cache",
    "sp500_in_prospectus_text",
    "benchmark_mismatches_dataframe",
    "summarize_lipper_edgar_benchmark_comparison",
]

_SP500_CORE = re.compile(
    r"(?:s\s*&\s*p|standard\s*(?:&|and)\s*poor(?:'?s)?|s&p)\s*(?:500|five\s*hundred)"
    r"|(?:^|\s)sp\s*500(?:\s|$)"
    r"|composite\s*stock\s*price\s*index",
    re.I,
)
_SP500_EXCLUDE = re.compile(
    r"growth|value|equal\s*weight|mid\s*cap|midcap|completion|buffer|sector|"
    r"information\s*technology|health\s*care|financial|energy|"
    r"500\s*equal|500\s*esg",
    re.I,
)
_SP500_TOTAL = re.compile(r"total\s*return", re.I)
_SP500_PRICE = re.compile(
    r"(?:price\s*index|composite\s*stock\s*price)(?!\s*return)",
    re.I,
)
_SP500_REINVEST = re.compile(r"reinvest(?:ment)?\s+of\s+dividend", re.I)
_OBJECTIVE_MIN_LEN = 120
# EDGAR HTML often uses a typographic apostrophe in "Poor's" (U+2019).
_TYPOGRAPHIC_APOSTROPHE = re.compile(r"[\u2018\u2019\u201b\u02bc\u2032]")


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _normalize_match_text(text: str) -> str:
    return _TYPOGRAPHIC_APOSTROPHE.sub("'", _collapse_ws(text))


def _empty_proof() -> dict[str, Any]:
    return {
        "classification": None,
        "variant": None,
        "source": "none",
        "logic": "No EDGAR evidence that this series benchmarks core S&P 500.",
        "evidence": {},
    }


def classify_sp500_benchmark_label(label: str) -> dict[str, Any] | None:
    """Map a prospectus performance-table label to a core S&P 500 benchmark variant."""
    raw = _collapse_ws(label)
    text = _TYPOGRAPHIC_APOSTROPHE.sub("'", raw)
    if not text or _SP500_EXCLUDE.search(text):
        return None
    if not _SP500_CORE.search(text):
        return None

    if _SP500_TOTAL.search(text):
        variant = SP500_TOTAL_RETURN
    elif _SP500_PRICE.search(text):
        variant = SP500_PRICE
    elif _SP500_REINVEST.search(text):
        variant = SP500_TOTAL_RETURN
    elif re.search(r"index\s+return", text, re.I):
        variant = SP500_UNSPECIFIED
    else:
        variant = SP500_UNSPECIFIED

    return {
        "variant": variant,
        "raw_label": raw,
    }


def is_sp500_series_name(name: str) -> bool:
    text = _normalize_match_text(name)
    if not text or _SP500_EXCLUDE.search(text):
        return False
    if re.search(r"s\s*&\s*p\s*500|sp\s*500", text, re.I):
        return True
    if re.search(r"(?:equity|large\s*cap|500)\s+index\s+fund", text, re.I) and re.search(
        r"\b500\b", text
    ):
        return True
    return False


def sp500_in_prospectus_text(text: str) -> bool:
    normalized = _normalize_match_text(text)
    if len(normalized) < 40:
        return False
    if _SP500_EXCLUDE.search(normalized):
        return False
    if _SP500_CORE.search(normalized):
        return True
    return "composite stock price index" in normalized.lower()


def _variant_rank(variant: str | None) -> int:
    return {
        SP500_TOTAL_RETURN: 3,
        SP500_PRICE: 2,
        SP500_UNSPECIFIED: 1,
    }.get(variant or "", 0)


def _best_sp500_from_labels(labels: list[str]) -> dict[str, Any] | None:
    parsed = [classify_sp500_benchmark_label(label) for label in labels]
    hits = [p for p in parsed if p]
    if not hits:
        return None
    best = max(hits, key=lambda item: _variant_rank(item["variant"]))
    return {
        "variant": best["variant"],
        "matched_labels": [h["raw_label"] for h in hits],
        "best_label": best["raw_label"],
    }


def _filing_facts_entry(filing_facts: dict, series_id: str | None) -> dict[str, Any] | None:
    if not series_id:
        return None
    entry = filing_facts.get(str(series_id))
    return entry if isinstance(entry, dict) else None


def proof_sp500_benchmark(
    *,
    series_id: str | None,
    fund_name: str | None,
    filing_facts: dict,
) -> dict[str, Any]:
    entry = _filing_facts_entry(filing_facts, series_id)
    if not entry:
        return {
            **_empty_proof(),
            "logic": (
                "No filing-facts cache entry for this series "
                "(missing EDGAR match or facts not fetched)."
            ),
        }

    n_cen = entry.get("n_cen") if isinstance(entry.get("n_cen"), dict) else {}
    prospectus = entry.get("prospectus") if isinstance(entry.get("prospectus"), dict) else {}
    series = n_cen.get("series") if isinstance(n_cen.get("series"), dict) else {}

    benchmark_labels = list(prospectus.get("benchmark_indices") or [])
    sp500_hit = _best_sp500_from_labels(benchmark_labels)
    if sp500_hit:
        all_benchmarks = benchmark_labels
        sp500_only = len(all_benchmarks) == len(sp500_hit["matched_labels"]) == 1
        logic = (
            "Prospectus performance table lists core S&P 500 "
            f"({sp500_hit['best_label']!r})."
        )
        if not sp500_only and len(all_benchmarks) > 1:
            logic += f" Also lists other indices: {len(all_benchmarks) - len(sp500_hit['matched_labels'])} additional row(s)."
        return {
            "classification": True,
            "variant": sp500_hit["variant"],
            "source": "edgar_prospectus_benchmark_indices",
            "logic": logic,
            "evidence": {
                "series_id": series_id,
                "prospectus_accession_number": prospectus.get("accession_number"),
                "prospectus_filing_date": prospectus.get("filing_date"),
                "prospectus_form": prospectus.get("form"),
                "fund_name_prospectus": prospectus.get("fund_name"),
                "benchmark_indices_all": all_benchmarks,
                "sp500_matched_labels": sp500_hit["matched_labels"],
                "sp500_only_benchmark": sp500_only,
            },
        }

    objective = prospectus.get("investment_objective") or ""
    strategy = prospectus.get("strategy_text") or objective
    prospectus_name = prospectus.get("fund_name") or ""
    if len(objective) >= _OBJECTIVE_MIN_LEN and sp500_in_prospectus_text(objective):
        return {
            "classification": True,
            "variant": SP500_UNSPECIFIED,
            "source": "edgar_prospectus_objective",
            "logic": (
                "Prospectus investment objective text references core S&P 500 "
                "(variant not explicit in extracted objective snippet)."
            ),
            "evidence": {
                "series_id": series_id,
                "prospectus_accession_number": prospectus.get("accession_number"),
                "prospectus_filing_date": prospectus.get("filing_date"),
                "objective_excerpt": objective[:500],
            },
        }

    name_candidates = [
        fund_name or "",
        prospectus_name,
        series.get("name") or "",
    ]
    for source_name, label in (
        ("edgar_prospectus_fund_name", prospectus_name),
        ("edgar_n_cen_series_name", series.get("name") or ""),
        ("lipper_fund_name", fund_name or ""),
    ):
        if is_sp500_series_name(label):
            return {
                "classification": True,
                "variant": SP500_UNSPECIFIED,
                "source": source_name,
                "logic": (
                    f"Fund/series name {label!r} indicates core S&P 500; "
                    "prospectus benchmark table had no parseable S&P 500 row."
                ),
                "evidence": {
                    "series_id": series_id,
                    "matched_name": label,
                    "name_candidates": [n for n in name_candidates if n],
                    "benchmark_indices_all": benchmark_labels,
                    "objective_length": len(objective),
                    "strategy_length": len(strategy),
                },
            }

    if not prospectus:
        logic = "Filing facts exist but prospectus slice is missing."
    elif not benchmark_labels:
        logic = (
            "Prospectus cached but benchmark_indices is empty and name/objective "
            "did not match core S&P 500 heuristics."
        )
    else:
        logic = (
            "Prospectus benchmark_indices present but no core S&P 500 label matched "
            f"({len(benchmark_labels)} other index row(s))."
        )

    return {
        "classification": False,
        "variant": None,
        "source": "edgar_prospectus",
        "logic": logic,
        "evidence": {
            "series_id": series_id,
            "benchmark_indices_all": benchmark_labels,
            "prospectus_accession_number": prospectus.get("accession_number"),
            "series_name": series.get("name"),
            "fund_name_prospectus": prospectus_name,
        },
    }


def normalize_lipper_benchmark(
    benchmark_name: Any,
    is_sp500_flag: Any,
) -> dict[str, Any]:
    """Normalize Lipper benchmark fields for comparison (not used as EDGAR evidence)."""
    name = None
    if benchmark_name is not None and not (isinstance(benchmark_name, float) and pd.isna(benchmark_name)):
        text = str(benchmark_name).strip()
        if text:
            name = text

    flag = None
    if is_sp500_flag is True or str(is_sp500_flag).strip().lower() in ("true", "1", "yes"):
        flag = True
    elif is_sp500_flag is False or str(is_sp500_flag).strip().lower() in ("false", "0", "no"):
        flag = False

    references_sp500 = flag is True
    variant = None
    if name:
        lowered = name.lower()
        if "s&p" in lowered or "s & p" in lowered or "standard" in lowered:
            if "500" in lowered:
                if "price" in lowered and "total" not in lowered:
                    variant = SP500_PRICE
                elif "tr" in lowered or "total return" in lowered:
                    variant = SP500_TOTAL_RETURN
                else:
                    variant = SP500_UNSPECIFIED
                references_sp500 = True

    return {
        "benchmark_name": name,
        "is_sp500_flag": flag,
        "references_sp500": references_sp500,
        "variant": variant,
    }


def _variants_compatible(lipper_variant: str | None, edgar_variant: str | None) -> bool | None:
    if lipper_variant is None or edgar_variant is None:
        return None
    if lipper_variant == edgar_variant:
        return True
    if lipper_variant == SP500_TOTAL_RETURN and edgar_variant == SP500_UNSPECIFIED:
        return True
    if lipper_variant == SP500_UNSPECIFIED and edgar_variant == SP500_TOTAL_RETURN:
        return True
    return False


def evaluate_fund_row(
    *,
    isin: str,
    name: Any,
    lipper_benchmark_name: Any,
    lipper_is_sp500: Any,
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
    fund_name = None if pd.isna(name) else name

    benchmark_proof = proof_sp500_benchmark(
        series_id=series_id,
        fund_name=str(fund_name) if fund_name is not None else None,
        filing_facts=filing_facts,
    )

    lipper = normalize_lipper_benchmark(lipper_benchmark_name, lipper_is_sp500)
    edgar_classification = benchmark_proof.get("classification")
    edgar_known = edgar_classification is True or edgar_classification is False
    edgar_has_sp500 = edgar_classification is True
    lipper_has_sp500 = lipper["references_sp500"]

    presence_match = None
    if edgar_known and (
        lipper_has_sp500 or edgar_has_sp500 or lipper["is_sp500_flag"] is False
    ):
        if lipper_has_sp500 and edgar_has_sp500:
            presence_match = True
        elif lipper_has_sp500 != edgar_has_sp500:
            presence_match = False
        elif lipper["is_sp500_flag"] is False and not edgar_has_sp500:
            presence_match = True

    variant_match = None
    if edgar_has_sp500 and lipper_has_sp500:
        variant_match = _variants_compatible(lipper.get("variant"), benchmark_proof.get("variant"))

    return {
        "isin": isin,
        "name": fund_name,
        "market_identifier": ticker,
        "edgartools_series_id": series_id,
        "lipper_benchmark_name": lipper["benchmark_name"],
        "lipper_is_sp500": lipper["is_sp500_flag"],
        "sp500_benchmark": benchmark_proof,
        "comparison": {
            "lipper_references_sp500": lipper_has_sp500,
            "lipper_variant_normalized": lipper.get("variant"),
            "edgar_references_sp500": edgar_has_sp500 if edgar_known else None,
            "edgar_variant_normalized": benchmark_proof.get("variant"),
            "lipper_matches_edgar_sp500_presence": presence_match,
            "lipper_matches_edgar_sp500_variant": variant_match,
        },
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def load_dq_fund_benchmark_cache(cache_path: Path | None = None) -> dict:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_dq_fund_benchmark_cache(cache: dict, cache_path: Path | None = None) -> Path:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, default=str) + "\n")
    return path


def build_dq_fund_benchmark_edgar_cache(
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
            lipper_benchmark_name=row.get("Benchmark Name"),
            lipper_is_sp500=row.get("is_S&P500"),
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
    save_dq_fund_benchmark_cache(cache, cache_path)
    return cache


def summarize_lipper_edgar_benchmark_comparison(
    cache: dict | None = None,
    cache_path: Path | None = None,
) -> dict[str, int]:
    if cache is None:
        cache = load_dq_fund_benchmark_cache(cache_path)
    records = cache.get("records") if isinstance(cache, dict) else {}
    if not isinstance(records, dict):
        records = {}

    presence_match = 0
    presence_mismatch = 0
    no_edgar = 0
    lipper_not_sp500 = 0
    edgar_sp500 = 0
    variant_match = 0
    variant_mismatch = 0

    for row in records.values():
        if not isinstance(row, dict):
            continue
        comp = row.get("comparison") or {}
        if comp.get("edgar_references_sp500"):
            edgar_sp500 += 1
        lipper_ref = comp.get("lipper_references_sp500")
        if not lipper_ref and row.get("lipper_is_sp500") is not True:
            lipper_not_sp500 += 1
        if not comp.get("edgar_references_sp500") and comp.get("lipper_references_sp500"):
            no_edgar += 1
        pm = comp.get("lipper_matches_edgar_sp500_presence")
        if pm is True:
            presence_match += 1
        elif pm is False:
            presence_mismatch += 1
        vm = comp.get("lipper_matches_edgar_sp500_variant")
        if vm is True:
            variant_match += 1
        elif vm is False:
            variant_mismatch += 1

    return {
        "total_funds": len(records),
        "edgar_sp500_benchmark_proof": edgar_sp500,
        "lipper_edgar_presence_match": presence_match,
        "lipper_edgar_presence_mismatch": presence_mismatch,
        "lipper_edgar_variant_match": variant_match,
        "lipper_edgar_variant_mismatch": variant_mismatch,
        "lipper_sp500_flag_without_edgar_proof": no_edgar,
        "lipper_not_marked_sp500": lipper_not_sp500,
    }


def benchmark_mismatches_dataframe(
    cache: dict | None = None,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    if cache is None:
        cache = load_dq_fund_benchmark_cache(cache_path)
    records = cache.get("records") if isinstance(cache, dict) else {}
    rows: list[dict[str, Any]] = []
    if not isinstance(records, dict):
        return pd.DataFrame(rows)

    for isin, row in records.items():
        if not isinstance(row, dict):
            continue
        if (row.get("comparison") or {}).get("lipper_matches_edgar_sp500_presence") is False:
            proof = row.get("sp500_benchmark") or {}
            rows.append(
                {
                    "ISIN": isin,
                    "Name": row.get("name"),
                    "market_identifier": row.get("market_identifier"),
                    "lipper_benchmark_name": row.get("lipper_benchmark_name"),
                    "lipper_is_sp500": row.get("lipper_is_sp500"),
                    "edgar_sp500": proof.get("classification"),
                    "edgar_variant": proof.get("variant"),
                    "benchmark_source": proof.get("source"),
                    "benchmark_logic": proof.get("logic"),
                }
            )
    return pd.DataFrame(rows)


def dq_fund_benchmark_edgar(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """Build S&P 500 benchmark proof for each fund; write ``dq-fund_benchmark-edgar.json``."""
    cache = build_dq_fund_benchmark_edgar_cache(funds, cache_path=cache_path, **kwargs)
    records = cache.get("records") or {}
    with_proof = sum(
        1
        for row in records.values()
        if isinstance(row, dict) and row.get("sp500_benchmark", {}).get("classification") is True
    )
    summary = summarize_lipper_edgar_benchmark_comparison(cache=cache)
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    print(
        f"S&P 500 benchmark DQ (EDGAR): {len(records)} funds written to {path} "
        f"({with_proof} with EDGAR S&P 500 benchmark proof; "
        f"{summary['lipper_edgar_presence_match']} Lipper presence matches, "
        f"{summary['lipper_edgar_presence_mismatch']} presence mismatches)"
    )
    return funds
