"""Build tabular rows for the Edgar-checks export sheet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from helpers.funds_functions.dq_fund_benchmark_edgar import load_dq_fund_benchmark_cache
from helpers.funds_functions.dq_fund_type_edgar import (
    FUND_TYPE_ACTIVE,
    FUND_TYPE_PASSIVE,
    load_dq_fund_type_cache,
)
from helpers.funds_functions.dq_fund_wrapper_edgar import load_dq_fund_wrapper_cache
from helpers.funds_functions.fetch_edgar_filing_facts import load_filing_facts_cache
from helpers.funds_functions.map_edgar_tickers import (
    cik_text,
    load_edgar_fund_data_cache,
)

ColumnKind = Literal["text", "bool", "number", "result", "wrap"]


@dataclass(frozen=True)
class ColumnSpec:
    family: str
    header: str
    key: str
    width: float
    kind: ColumnKind = "text"


# Blank separator columns use family "" and key starting with "_gap"
COLUMN_FAMILIES: list[ColumnSpec] = [
    ColumnSpec("Fund (Lipper)", "ISIN", "lipper_isin", 16),
    ColumnSpec("Fund (Lipper)", "Name", "lipper_name", 43),
    ColumnSpec("", "", "_gap1", 1.5),
    ColumnSpec("EDGAR identification", "Ticker", "ticker", 12),
    ColumnSpec("EDGAR identification", "CIK", "cik", 12),
    ColumnSpec("EDGAR identification", "Series ID", "series_id", 14),
    ColumnSpec("EDGAR identification", "Class ID", "class_id", 14),
    ColumnSpec("EDGAR identification", "Registrant", "registrant", 28),
    ColumnSpec("EDGAR identification", "Series name", "series_name", 28),
    ColumnSpec("EDGAR identification", "Class name", "class_name", 22),
    ColumnSpec("", "", "_gap2", 1.5),
    ColumnSpec("EDGAR N-CEN", "N-CEN filing date", "ncen_filing_date", 14),
    ColumnSpec("EDGAR N-CEN", "Report date", "ncen_report_date", 14),
    ColumnSpec("EDGAR N-CEN", "Registrant class.", "ncen_registrant_class", 12),
    ColumnSpec("EDGAR N-CEN", "Open-end", "ncen_open_end", 10, "bool"),
    ColumnSpec("EDGAR N-CEN", "Has ETF", "ncen_has_etf", 10, "bool"),
    ColumnSpec("EDGAR N-CEN", "ETF ticker", "ncen_etf_ticker", 12),
    ColumnSpec("EDGAR N-CEN", "Fund type labels", "ncen_fund_type_labels", 22),
    ColumnSpec("EDGAR N-CEN", "Index fund", "ncen_index_fund", 10, "bool"),
    ColumnSpec("", "", "_gap3", 1.5),
    ColumnSpec("EDGAR prospectus", "Form", "prospectus_form", 10),
    ColumnSpec("EDGAR prospectus", "Filing date", "prospectus_filing_date", 14),
    ColumnSpec("EDGAR prospectus", "Fund name", "prospectus_fund_name", 28),
    ColumnSpec("EDGAR prospectus", "Net expense ratio %", "prospectus_net_ter", 14, "number"),
    ColumnSpec("EDGAR prospectus", "Benchmark indices", "prospectus_benchmarks", 36, "wrap"),
    ColumnSpec("EDGAR prospectus", "Investment objective", "prospectus_objective", 40, "wrap"),
    ColumnSpec("", "", "_gap4", 1.5),
    ColumnSpec("Check: fund_wrapper", "Lipper fund_wrapper", "wrap_lipper", 14),
    ColumnSpec("Check: fund_wrapper", "EDGAR fund_wrapper", "wrap_edgar", 16),
    ColumnSpec("Check: fund_wrapper", "Proof source", "wrap_source", 14),
    ColumnSpec("Check: fund_wrapper", "Result", "wrap_result", 14, "result"),
    ColumnSpec("Check: fund_wrapper", "Justification", "wrap_justification", 48, "wrap"),
    ColumnSpec("", "", "_gap5", 1.5),
    ColumnSpec("Check: fund_type", "Lipper fund_type", "type_lipper", 14),
    ColumnSpec("Check: fund_type", "EDGAR fund_type", "type_edgar", 14),
    ColumnSpec("Check: fund_type", "Result", "type_result", 14, "result"),
    ColumnSpec("Check: fund_type", "Justification", "type_justification", 48, "wrap"),
    ColumnSpec("", "", "_gap6", 1.5),
    ColumnSpec("Check: benchmark", "Lipper Benchmark Name", "bench_lipper_name", 28),
    ColumnSpec("Check: benchmark", "Lipper is_S&P500", "bench_lipper_flag", 14, "bool"),
    ColumnSpec("Check: benchmark", "EDGAR S&P 500 benchmark", "bench_edgar_sp500", 12, "bool"),
    ColumnSpec("Check: benchmark", "EDGAR variant", "bench_edgar_variant", 18),
    ColumnSpec("Check: benchmark", "Result (presence)", "bench_result_presence", 16, "result"),
    ColumnSpec("Check: benchmark", "Variant result", "bench_result_variant", 14, "result"),
    ColumnSpec("Check: benchmark", "Justification", "bench_justification", 48, "wrap"),
    ColumnSpec("", "", "_gap7", 1.5),
    ColumnSpec("Decision", "Include fund", "decision_include", 12, "bool"),
    ColumnSpec("Decision", "Final fund_wrapper", "decision_final_wrapper", 16),
    ColumnSpec("Decision", "Final fund_type", "decision_final_type", 14),
]

DATA_COLUMN_KEYS = [c.key for c in COLUMN_FAMILIES if not c.key.startswith("_gap")]

__all__ = [
    "COLUMN_FAMILIES",
    "DATA_COLUMN_KEYS",
    "build_edgar_checks_rows",
    "load_edgar_checks_sources",
    "wrapper_result_label",
    "fund_type_result_label",
    "benchmark_presence_result_label",
    "benchmark_variant_result_label",
    "default_decision_include",
]


def _cell(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    return text if text else None


def _labels_join(labels: Any) -> str | None:
    if not labels:
        return None
    if isinstance(labels, list):
        parts = [str(x).strip() for x in labels if str(x).strip()]
        return "; ".join(parts) if parts else None
    return str(labels)


def _net_ter_for_ticker(prospectus: dict[str, Any] | None, ticker: str | None) -> float | None:
    if not prospectus or not ticker:
        return None
    ticker_u = ticker.strip().upper()
    for row in prospectus.get("share_classes") or []:
        if not isinstance(row, dict):
            continue
        sc_ticker = row.get("ticker")
        if isinstance(sc_ticker, str) and sc_ticker.strip().upper() == ticker_u:
            val = row.get("net_expense_ratio_pct")
            if val is None:
                val = row.get("ter_pct")
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None
    if len(prospectus.get("share_classes") or []) == 1:
        row = (prospectus.get("share_classes") or [None])[0]
        if isinstance(row, dict):
            val = row.get("net_expense_ratio_pct") or row.get("ter_pct")
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
    return None


def _objective_trim(text: Any, max_len: int = 500) -> str | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    s = str(text).replace("\n", " ").strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s or None


def wrapper_result_label(comparison: dict[str, Any] | None, edgar_wrapper: Any) -> str:
    if not edgar_wrapper:
        return "Not comparable"
    if not comparison:
        return "Not comparable"
    match = comparison.get("lipper_matches_edgar_wrapper")
    if match is True:
        return "Match"
    if match is False:
        return "Mismatch"
    return "Not comparable"


def fund_type_result_label(comparison: dict[str, Any] | None, edgar_type: Any) -> str:
    if not edgar_type:
        return "Not comparable"
    if not comparison:
        return "Not comparable"
    lipper_norm = comparison.get("lipper_fund_type_normalized")
    if lipper_norm not in (FUND_TYPE_ACTIVE, FUND_TYPE_PASSIVE):
        return "Not comparable"
    match = comparison.get("lipper_matches_edgar_fund_type")
    if match is True:
        return "Match"
    if match is False:
        return "Mismatch"
    return "Not comparable"


def benchmark_presence_result_label(comparison: dict[str, Any] | None) -> str:
    if not comparison:
        return "Not comparable"
    match = comparison.get("lipper_matches_edgar_sp500_presence")
    if match is True:
        return "Match"
    if match is False:
        return "Mismatch"
    return "Not comparable"


def benchmark_variant_result_label(comparison: dict[str, Any] | None) -> str:
    if not comparison:
        return "Not comparable"
    if not comparison.get("edgar_references_sp500") or not comparison.get(
        "lipper_references_sp500"
    ):
        return "Not comparable"
    match = comparison.get("lipper_matches_edgar_sp500_variant")
    if match is True:
        return "Match"
    if match is False:
        return "Mismatch"
    return "Not comparable"


def _dq_records(cache: dict) -> dict[str, Any]:
    records = cache.get("records") if isinstance(cache, dict) else {}
    return records if isinstance(records, dict) else {}


def _lipper_fund_type_raw(row: pd.Series, t_rec: dict[str, Any] | None) -> Any:
    if "fund_type" in row.index and pd.notna(row.get("fund_type")):
        return row.get("fund_type")
    if t_rec:
        return t_rec.get("lipper_fund_type")
    return None


def _lipper_fund_wrapper_raw(row: pd.Series, w_rec: dict[str, Any] | None) -> Any:
    if "fund_wrapper" in row.index and pd.notna(row.get("fund_wrapper")):
        return row.get("fund_wrapper")
    if w_rec:
        return w_rec.get("lipper_fund_wrapper")
    return None


def default_decision_include(lipper_fund_type: Any) -> bool:
    """Default Include fund = TRUE when Lipper fund_type is not blank."""
    if lipper_fund_type is None or (isinstance(lipper_fund_type, float) and pd.isna(lipper_fund_type)):
        return False
    return bool(str(lipper_fund_type).strip())


def _normalize_isin(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _fund_reference_by_ticker() -> dict[str, dict[str, Any]]:
    """Ticker → SEC fund reference row (CIK, series/class IDs and names)."""
    ref = load_edgar_fund_data_cache()
    if ref is None or ref.empty or "ticker" not in ref.columns:
        return {}
    lookup = ref.dropna(subset=["ticker"]).copy()
    lookup["ticker"] = lookup["ticker"].astype(str).str.strip().str.upper()
    lookup = lookup.drop_duplicates("ticker", keep="first")
    out: dict[str, dict[str, Any]] = {}
    for row in lookup.itertuples(index=False):
        ticker = getattr(row, "ticker", None)
        if not ticker:
            continue
        out[str(ticker)] = row._asdict()
    return out


def _resolve_ticker_and_series(
    row: pd.Series,
    dq_records: tuple[dict[str, Any] | None, ...],
) -> tuple[str | None, str | None]:
    ticker = _cell(row.get("market_identifier"))
    series_id = _cell(row.get("edgartools_series_id"))
    for rec in dq_records:
        if not isinstance(rec, dict):
            continue
        if not ticker:
            ticker = _cell(rec.get("market_identifier"))
        if not series_id:
            series_id = _cell(rec.get("edgartools_series_id"))
    if ticker and isinstance(ticker, str):
        ticker = ticker.strip().upper()
    return ticker, series_id


def _identification_from_reference(
    ref_row: dict[str, Any] | None,
) -> dict[str, Any]:
    if not ref_row:
        return {}
    series_id = ref_row.get("series_id")
    class_id = ref_row.get("class_id")
    return {
        "cik": cik_text(ref_row.get("cik")),
        "series_id": _cell(series_id),
        "class_id": _cell(class_id),
        "registrant": _cell(ref_row.get("company_name")),
        "series_name": _cell(ref_row.get("series_name")),
        "class_name": _cell(ref_row.get("class_name")),
    }


def _row_for_fund(
    row: pd.Series,
    filing_facts: dict,
    wrapper_by_isin: dict[str, Any],
    type_by_isin: dict[str, Any],
    bench_by_isin: dict[str, Any],
    ref_by_ticker: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    isin = _normalize_isin(row.get("ISIN"))

    w_rec = wrapper_by_isin.get(isin) if isin else None
    t_rec = type_by_isin.get(isin) if isin else None
    b_rec = bench_by_isin.get(isin) if isin else None

    ticker, series_id = _resolve_ticker_and_series(row, (w_rec, t_rec, b_rec))
    ref_row = ref_by_ticker.get(ticker) if ticker else None
    ref_ids = _identification_from_reference(ref_row)

    if not series_id:
        series_id = ref_ids.get("series_id")

    facts = filing_facts.get(str(series_id)) if series_id else None
    if not isinstance(facts, dict):
        facts = {}

    n_cen = facts.get("n_cen") if isinstance(facts.get("n_cen"), dict) else {}
    prospectus = facts.get("prospectus") if isinstance(facts.get("prospectus"), dict) else {}
    series = n_cen.get("series") if isinstance(n_cen.get("series"), dict) else {}
    etf = n_cen.get("etf") if isinstance(n_cen.get("etf"), dict) else None
    fund_types = n_cen.get("fund_types") if isinstance(n_cen.get("fund_types"), dict) else {}

    wrap_proof = (w_rec or {}).get("fund_wrapper") or {}
    type_proof = (t_rec or {}).get("fund_type") or {}
    bench_proof = (b_rec or {}).get("sp500_benchmark") or {}

    benchmarks = prospectus.get("benchmark_indices") or []
    bench_text = "; ".join(str(b) for b in benchmarks) if benchmarks else None

    lipper_type_raw = _lipper_fund_type_raw(row, t_rec)
    lipper_wrapper_raw = _lipper_fund_wrapper_raw(row, w_rec)

    return {
        "lipper_isin": isin or None,
        "lipper_name": _cell(row.get("Name")),
        "ticker": ticker,
        "cik": _cell(row.get("edgartools_cik")) or ref_ids.get("cik"),
        "series_id": series_id,
        "class_id": _cell(row.get("edgartools_class_id")) or ref_ids.get("class_id"),
        "registrant": _cell(row.get("edgar_company_name"))
        or ref_ids.get("registrant")
        or _cell(n_cen.get("registrant_name")),
        "series_name": _cell(row.get("edgar_series_name"))
        or ref_ids.get("series_name")
        or _cell(series.get("name")),
        "class_name": _cell(row.get("edgar_class_name")) or ref_ids.get("class_name"),
        "ncen_filing_date": _cell(n_cen.get("filing_date")),
        "ncen_report_date": _cell(n_cen.get("report_date")),
        "ncen_registrant_class": _cell(n_cen.get("registrant_classification_type")),
        "ncen_open_end": n_cen.get("is_open_end"),
        "ncen_has_etf": series.get("has_etf"),
        "ncen_etf_ticker": _cell(etf.get("ticker")) if etf else None,
        "ncen_fund_type_labels": _labels_join(
            fund_types.get("labels") or series.get("fund_type_labels")
        ),
        "ncen_index_fund": fund_types.get("is_index_fund"),
        "prospectus_form": _cell(prospectus.get("form")),
        "prospectus_filing_date": _cell(prospectus.get("filing_date")),
        "prospectus_fund_name": _cell(prospectus.get("fund_name")),
        "prospectus_net_ter": _net_ter_for_ticker(prospectus, ticker),
        "prospectus_benchmarks": bench_text,
        "prospectus_objective": _objective_trim(prospectus.get("investment_objective")),
        "wrap_lipper": _cell(row.get("fund_wrapper"))
        or _cell((w_rec or {}).get("lipper_fund_wrapper")),
        "wrap_edgar": _cell(wrap_proof.get("classification")),
        "wrap_source": _cell(wrap_proof.get("source")),
        "wrap_result": wrapper_result_label(
            (w_rec or {}).get("comparison"), wrap_proof.get("classification")
        ),
        "wrap_justification": _cell(wrap_proof.get("logic")),
        "type_lipper": _cell(row.get("fund_type")) or _cell((t_rec or {}).get("lipper_fund_type")),
        "type_edgar": _cell(type_proof.get("classification")),
        "type_result": fund_type_result_label(
            (t_rec or {}).get("comparison"), type_proof.get("classification")
        ),
        "type_justification": _cell(type_proof.get("logic")),
        "bench_lipper_name": _cell(row.get("Benchmark Name"))
        or _cell((b_rec or {}).get("lipper_benchmark_name")),
        "bench_lipper_flag": row.get("is_S&P500")
        if pd.notna(row.get("is_S&P500"))
        else (b_rec or {}).get("lipper_is_sp500"),
        "bench_edgar_sp500": bench_proof.get("classification"),
        "bench_edgar_variant": _cell(bench_proof.get("variant")),
        "bench_result_presence": benchmark_presence_result_label((b_rec or {}).get("comparison")),
        "bench_result_variant": benchmark_variant_result_label((b_rec or {}).get("comparison")),
        "bench_justification": _cell(bench_proof.get("logic")),
        "decision_include": default_decision_include(lipper_type_raw),
        "decision_final_wrapper": _cell(lipper_wrapper_raw),
        "decision_final_type": _cell(lipper_type_raw),
    }


def load_edgar_checks_sources() -> tuple[dict, dict, dict, dict]:
    filing_facts = load_filing_facts_cache()
    wrapper = load_dq_fund_wrapper_cache()
    fund_type = load_dq_fund_type_cache()
    benchmark = load_dq_fund_benchmark_cache()
    return filing_facts, wrapper, fund_type, benchmark


def build_edgar_checks_rows(
    funds: pd.DataFrame,
    filing_facts: dict | None = None,
    dq_wrapper: dict | None = None,
    dq_type: dict | None = None,
    dq_benchmark: dict | None = None,
    fund_reference_by_ticker: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """One export row per fund row, preserving sheet order."""
    if filing_facts is None or dq_wrapper is None or dq_type is None or dq_benchmark is None:
        loaded = load_edgar_checks_sources()
        filing_facts = filing_facts if filing_facts is not None else loaded[0]
        dq_wrapper = dq_wrapper if dq_wrapper is not None else loaded[1]
        dq_type = dq_type if dq_type is not None else loaded[2]
        dq_benchmark = dq_benchmark if dq_benchmark is not None else loaded[3]

    wrapper_by_isin = _dq_records(dq_wrapper)
    type_by_isin = _dq_records(dq_type)
    bench_by_isin = _dq_records(dq_benchmark)
    ref_by_ticker = (
        fund_reference_by_ticker
        if fund_reference_by_ticker is not None
        else _fund_reference_by_ticker()
    )

    rows = [
        _row_for_fund(
            row,
            filing_facts,
            wrapper_by_isin,
            type_by_isin,
            bench_by_isin,
            ref_by_ticker,
        )
        for _, row in funds.iterrows()
    ]
    return pd.DataFrame(rows, columns=DATA_COLUMN_KEYS)
