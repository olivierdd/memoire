"""Fetch latest N-CEN and prospectus slices per fund series; cache for future DQ checks."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from lxml import etree

from edgar.funds import Fund
from edgar.funds.ncen import FundCensus
from edgar.funds.prospectus497k import PROSPECTUS497K_FORMS, Prospectus497K
from edgar.funds.reports import _strip_namespaces

from helpers.funds_functions.map_edgar_tickers import ensure_sec_identity, resolve_cache_path

DEFAULT_CACHE = Path("cache") / "cache-edgar-filing-facts.json"
NULLS_ARE_FINAL = "_nulls_are_final"
PROSPECTUS_FORMS = [*PROSPECTUS497K_FORMS, "485BPOS", "485APOS"]
MAX_PROSPECTUS_FILINGS_SCAN = 400
MAX_NCEN_FILINGS_SCAN = 40
PAUSE_SECONDS = 0.5
SAVE_EVERY = 5
OPEN_END_REGISTRANT_CLASSIFICATION = "N-1A"
INDEX_FUND_LABEL = "Index Fund"
MANAGEMENT_STYLE_PASSIVE = "Passive"
MANAGEMENT_STYLE_ACTIVE = "Active"


def is_open_end_registrant(classification_type: str | None) -> bool | None:
    """True for N-1A open-end companies; False when another form is known; None if unknown."""
    if classification_type is None:
        return None
    text = str(classification_type).strip()
    if not text or text.upper() == "N/A":
        return None
    return text == OPEN_END_REGISTRANT_CLASSIFICATION


def _registrant_fields_from_census(census: FundCensus) -> dict[str, Any]:
    classification_type = _json_safe(getattr(census, "classification_type", None))
    return {
        "registrant_classification_type": classification_type,
        "is_open_end": is_open_end_registrant(classification_type),
    }


def _ncen_needs_registrant_refresh(n_cen: Any) -> bool:
    if not isinstance(n_cen, dict):
        return True
    return "registrant_classification_type" not in n_cen


def _ncen_needs_fund_types_refresh(n_cen: Any) -> bool:
    if not isinstance(n_cen, dict):
        return False
    if _ncen_needs_registrant_refresh(n_cen):
        return False
    fund_types = n_cen.get("fund_types")
    if not isinstance(fund_types, dict):
        return True
    return "is_index_fund" not in fund_types


def _ncen_is_cache_complete(n_cen: Any) -> bool:
    return not _ncen_needs_registrant_refresh(n_cen) and not _ncen_needs_fund_types_refresh(
        n_cen
    )


def _xml_local_tag(element: etree._Element) -> str:
    return etree.QName(element).localname


def _parse_index_fund_info(info_el: Any) -> dict[str, Any]:
    def child_text(tag: str) -> str | None:
        for child in info_el:
            if _xml_local_tag(child) == tag and child.text:
                return child.text.strip()
        return None

    def child_decimal(tag: str) -> float | None:
        text = child_text(tag)
        if not text:
            return None
        try:
            return float(Decimal(text))
        except (ArithmeticError, ValueError):
            return None

    return _json_safe(
        {
            "is_affiliated": child_text("isIndexFundAffiliated"),
            "is_exclusive": child_text("isIndexFundExclusive"),
            "return_diff_before_expense_pct": child_decimal(
                "indexFundReturnDiffBeforeExpense"
            ),
            "return_diff_after_expense_pct": child_decimal(
                "indexFundReturnDiffAfterExpense"
            ),
            "daily_stdev_before_expense_pct": child_decimal(
                "indexFundReturnDailyStdevBeforeExpense"
            ),
            "daily_stdev_after_expense_pct": child_decimal(
                "indexFundReturnDailyStdevAfterExpense"
            ),
        }
    )


def _labels_from_fund_types_container(container: Any) -> tuple[list[str], dict[str, Any] | None]:
    labels: list[str] = []
    index_fund_info: dict[str, Any] | None = None
    for child in container:
        tag = _xml_local_tag(child)
        if tag == "fundType" and child.text:
            text = child.text.strip()
            if text and text.upper() != "N/A":
                labels.append(text)
            continue
        attr_type = child.get("fundType")
        if attr_type:
            text = attr_type.strip()
            if text and text.upper() != "N/A":
                labels.append(text)
        if tag == "indexFundInfo" and index_fund_info is None:
            index_fund_info = _parse_index_fund_info(child)
    return labels, index_fund_info


def _labels_from_management_question(q_el: Any) -> tuple[list[str], dict[str, Any] | None]:
    fund_types_el = None
    legacy_fund_type: str | None = None
    for child in q_el:
        tag = _xml_local_tag(child)
        if tag == "fundTypes":
            fund_types_el = child
        elif tag == "fundType" and child.text:
            legacy_fund_type = child.text.strip()

    if fund_types_el is not None:
        return _labels_from_fund_types_container(fund_types_el)

    if legacy_fund_type and legacy_fund_type.upper() != "N/A":
        return [legacy_fund_type], None
    if legacy_fund_type is not None:
        return [], None
    return [], None


def management_style_from_ncen_labels(
    labels: list[str], *, has_legacy_na: bool = False
) -> str | None:
    if INDEX_FUND_LABEL in labels:
        return MANAGEMENT_STYLE_PASSIVE
    if labels or has_legacy_na:
        return MANAGEMENT_STYLE_ACTIVE
    return None


def parse_ncen_fund_types_for_series(xml: str | bytes, series_id: str) -> dict[str, Any] | None:
    """Parse N-CEN fundTypes / indexFundInfo for one series from filing XML."""
    if isinstance(xml, str):
        xml_bytes = xml.encode("utf-8")
    else:
        xml_bytes = xml

    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_bytes, parser=parser)

    _strip_namespaces(root)
    if _xml_local_tag(root) != "edgarSubmission":
        found = root.find(".//edgarSubmission")
        if found is not None:
            root = found

    form_data = root.find("formData")
    if form_data is None:
        return None

    mgmt_container = form_data.find("managementInvestmentQuestionSeriesInfo")
    if mgmt_container is None:
        return None

    target_id = str(series_id)
    for q_el in mgmt_container.findall("managementInvestmentQuestion"):
        series_el = q_el.find("mgmtInvSeriesId")
        if series_el is None or not series_el.text:
            continue
        if series_el.text.strip() != target_id:
            continue

        has_legacy_na = False
        for child in q_el:
            if _xml_local_tag(child) == "fundType" and child.text:
                has_legacy_na = child.text.strip().upper() == "N/A"
                break

        labels, index_fund_info = _labels_from_management_question(q_el)
        deduped: list[str] = []
        seen: set[str] = set()
        for label in labels:
            if label not in seen:
                seen.add(label)
                deduped.append(label)

        is_index_fund = INDEX_FUND_LABEL in deduped
        management_style = management_style_from_ncen_labels(
            deduped, has_legacy_na=has_legacy_na
        )
        return _json_safe(
            {
                "labels": deduped,
                "is_index_fund": is_index_fund,
                "management_style": management_style,
                "index_fund_info": index_fund_info,
            }
        )

    return None


def _fund_types_from_ncen_filing(filing, series_id: str) -> dict[str, Any] | None:
    xml = filing.xml()
    if not xml:
        return None
    return parse_ncen_fund_types_for_series(xml, series_id)


def _apply_fund_types_to_ncen_blob(blob: dict[str, Any], fund_types: dict[str, Any]) -> None:
    blob["fund_types"] = fund_types
    for key in ("series", "series_attributes"):
        section = blob.get(key)
        if not isinstance(section, dict):
            continue
        section["fund_type_labels"] = fund_types.get("labels")
        section["is_index_fund"] = fund_types.get("is_index_fund")
        section["management_style"] = fund_types.get("management_style")


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def load_filing_facts_cache(cache_path: Path | None = None) -> dict:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_filing_facts_cache(cache: dict, cache_path: Path | None = None) -> Path:
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, default=str) + "\n")
    return path


def _series_worklist(funds: pd.DataFrame) -> pd.DataFrame:
    required = ["edgartools_series_id", "edgartools_cik"]
    missing = [col for col in required if col not in funds.columns]
    if missing:
        raise KeyError(
            f"funds is missing EDGAR match columns {missing}. Run map_edgar_tickers first."
        )
    rows = funds.dropna(subset=["edgartools_series_id"]).copy()
    rows["edgartools_series_id"] = rows["edgartools_series_id"].astype(str)
    rows["edgartools_cik"] = rows["edgartools_cik"].astype(str)
    return rows.drop_duplicates("edgartools_series_id")


def _filing_meta(filing) -> dict[str, Any]:
    filing_date = getattr(filing, "filing_date", None)
    return _json_safe(
        {
            "accession_number": getattr(filing, "accession_no", None)
            or getattr(filing, "accession_number", None),
            "filing_date": filing_date,
            "form": getattr(filing, "form", None),
        }
    )


def _series_row_from_census(census: FundCensus, series_id: str) -> dict[str, Any] | None:
    df = census.series_data()
    if df.empty or "series_id" not in df.columns:
        return None
    match = df[df["series_id"].astype(str) == series_id]
    if match.empty:
        return None
    return _json_safe(match.iloc[0].to_dict())


def _etf_row_from_census(census: FundCensus, series_id: str) -> dict[str, Any] | None:
    df = census.etf_data()
    if df.empty or "series_id" not in df.columns:
        return None
    match = df[df["series_id"].astype(str) == series_id]
    if match.empty:
        return None
    return _json_safe(match.iloc[0].to_dict())


def _pydantic_series_fields(census: FundCensus, series_id: str) -> dict[str, Any]:
    for series in census.series:
        if series.series_id == series_id:
            return _json_safe(
                {
                    "is_diversified": series.is_diversified,
                    "is_securities_lending": series.is_securities_lending,
                    "fund_type": series.fund_type,
                    "share_class_count_hint": len(
                        [c for c in getattr(series, "classes", []) or []]
                    )
                    if hasattr(series, "classes")
                    else None,
                }
            )
    return {}


def extract_ncen_blob(census: FundCensus, filing, series_id: str) -> dict[str, Any]:
    series_row = _series_row_from_census(census, series_id)
    if series_row is None:
        raise ValueError(f"series_id {series_id} not in N-CEN filing")

    blob: dict[str, Any] = {
        **_filing_meta(filing),
        "report_date": _json_safe(getattr(census, "report_date", None)),
        "registrant_name": _json_safe(getattr(census, "name", None)),
        **_registrant_fields_from_census(census),
        "series": series_row,
        "etf": _etf_row_from_census(census, series_id),
        "series_attributes": _pydantic_series_fields(census, series_id),
    }
    fund_types = _fund_types_from_ncen_filing(filing, series_id)
    if fund_types is not None:
        _apply_fund_types_to_ncen_blob(blob, fund_types)
    return blob


def _filing_accession(filing) -> str | None:
    acc = getattr(filing, "accession_no", None) or getattr(filing, "accession_number", None)
    if acc is None:
        return None
    text = str(acc).strip()
    return text or None


def _cik_for_edgar_path(cik: str) -> str:
    digits = "".join(ch for ch in str(cik) if ch.isdigit())
    if not digits:
        return str(cik).strip()
    return str(int(digits))


def _accession_folder(accession: str) -> str:
    return str(accession).replace("-", "")


def ncen_primary_doc_url(cik: str, accession: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{_cik_for_edgar_path(cik)}/{_accession_folder(accession)}/primary_doc.xml"
    )


def fetch_ncen_primary_doc_xml(cik: str, accession: str) -> str | None:
    """Download N-CEN primary_doc.xml for a known CIK and accession number."""
    ensure_sec_identity()
    user_agent = os.getenv("SEC_USER_AGENT", "")
    url = ncen_primary_doc_url(cik, accession)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/xml,text/xml"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError:
        return None


def backfill_ncen_fund_types(
    series_id: str,
    n_cen: dict[str, Any],
    *,
    cik: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Attach fund_types to an existing n_cen blob using its accession's N-CEN XML."""
    ensure_sec_identity()
    accession = n_cen.get("accession_number")
    if not accession:
        return None, "missing_accession_number"

    if cik:
        xml = fetch_ncen_primary_doc_xml(cik, str(accession))
        if xml:
            fund_types = parse_ncen_fund_types_for_series(xml, series_id)
            if fund_types is not None:
                updated = dict(n_cen)
                _apply_fund_types_to_ncen_blob(updated, fund_types)
                return updated, None

    fund = Fund(series_id)
    filings = fund.get_filings(form="N-CEN")
    if not filings or len(filings) == 0:
        return None, "no_n_cen_filings"

    scanned = 0
    for filing in filings:
        scanned += 1
        if scanned > MAX_NCEN_FILINGS_SCAN:
            break
        if _filing_accession(filing) != str(accession):
            continue
        fund_types = _fund_types_from_ncen_filing(filing, series_id)
        if fund_types is None:
            return None, "fund_types_not_in_filing"
        updated = dict(n_cen)
        _apply_fund_types_to_ncen_blob(updated, fund_types)
        return updated, None

    return None, "accession_not_found_in_filings"


def fetch_latest_ncen(series_id: str, cik: str) -> tuple[dict[str, Any] | None, str | None]:
    fund = Fund(series_id)
    filings = fund.get_filings(form="N-CEN")
    if not filings or len(filings) == 0:
        return None, "no_n_cen_filings"

    scanned = 0
    for filing in filings:
        scanned += 1
        if scanned > MAX_NCEN_FILINGS_SCAN:
            break
        try:
            census = filing.obj()
        except Exception as exc:
            continue
        if not isinstance(census, FundCensus):
            continue
        if _series_row_from_census(census, series_id) is None:
            continue
        try:
            return extract_ncen_blob(census, filing, series_id), None
        except Exception as exc:
            return None, str(exc)

    return None, "series_not_found_in_n_cen"


def _parse_prospectus(filing) -> Prospectus497K | None:
    try:
        obj = filing.obj()
        if isinstance(obj, Prospectus497K):
            return obj
    except Exception:
        pass
    try:
        return Prospectus497K.from_filing(filing)
    except Exception:
        return None


def _prospectus_matches(
    prospectus: Prospectus497K, series_id: str, sample_ticker: str | None
) -> bool:
    if prospectus.series_id and str(prospectus.series_id) == series_id:
        return True
    if sample_ticker and prospectus.tickers:
        tickers = {str(t).upper() for t in prospectus.tickers if t}
        if sample_ticker.upper() in tickers:
            return True
    return False


def _fee_rows(prospectus: Prospectus497K) -> list[dict[str, Any]]:
    df = prospectus.fees
    if df is None or df.empty:
        share_classes = []
        for sc in prospectus.share_classes:
            share_classes.append(
                _json_safe(
                    {
                        "class_name": sc.class_name,
                        "ticker": sc.ticker,
                        "class_id": sc.class_id,
                        "management_fee_pct": sc.management_fee,
                        "twelve_b1_fee_pct": sc.twelve_b1_fee,
                        "other_expenses_pct": sc.other_expenses,
                        "gross_expense_ratio_pct": sc.total_annual_expenses,
                        "fee_waiver_pct": sc.fee_waiver,
                        "net_expense_ratio_pct": sc.net_expenses,
                    }
                )
            )
        return share_classes

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        gross = row.get("total_annual_expenses")
        net = row.get("net_expenses")
        ter = net if pd.notna(net) and net is not None else gross
        rows.append(
            _json_safe(
                {
                    "class_name": row.get("class_name"),
                    "ticker": row.get("ticker"),
                    "class_id": row.get("class_id"),
                    "management_fee_pct": row.get("management_fee"),
                    "twelve_b1_fee_pct": row.get("twelve_b1_fee"),
                    "other_expenses_pct": row.get("other_expenses"),
                    "gross_expense_ratio_pct": gross,
                    "fee_waiver_pct": row.get("fee_waiver"),
                    "net_expense_ratio_pct": net,
                    "ter_pct": ter,
                }
            )
        )
    return rows


def _benchmark_indices(prospectus: Prospectus497K) -> list[str]:
    df = prospectus.performance
    if df is None or df.empty or "label" not in df.columns:
        return []
    labels = []
    fund_tickers = {str(t).upper() for t in (prospectus.tickers or []) if t}
    for label in df["label"].dropna().astype(str):
        text = label.strip()
        if not text:
            continue
        lower = text.lower()
        if lower.startswith("return"):
            continue
        if text.upper() in fund_tickers:
            continue
        if "index" in lower or "benchmark" in lower or "s&p" in lower:
            labels.append(text)
    return sorted(set(labels))


def extract_prospectus_blob(
    prospectus: Prospectus497K, filing, *, form: str
) -> dict[str, Any]:
    objective = prospectus.investment_objective
    return _json_safe(
        {
            **_filing_meta(filing),
            "form": form,
            "fund_name": prospectus.fund_name,
            "series_id": prospectus.series_id,
            "tickers": list(prospectus.tickers or []),
            "investment_objective": objective,
            "strategy_text": objective,
            "share_classes": _fee_rows(prospectus),
            "benchmark_indices": _benchmark_indices(prospectus),
            "num_share_classes": prospectus.num_share_classes,
        }
    )


def fetch_latest_prospectus(
    series_id: str,
    cik: str,
    sample_ticker: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    fund = Fund(series_id)
    for form in PROSPECTUS_FORMS:
        filings = fund.get_filings(form=form)
        if not filings or len(filings) == 0:
            continue

        scanned = 0
        for filing in filings:
            scanned += 1
            if scanned > MAX_PROSPECTUS_FILINGS_SCAN:
                break
            prospectus = _parse_prospectus(filing)
            if prospectus is None:
                continue
            if not _prospectus_matches(prospectus, series_id, sample_ticker):
                continue
            try:
                return extract_prospectus_blob(prospectus, filing, form=form), None
            except Exception as exc:
                return None, str(exc)

    return None, "not_found"


def _empty_entry(cik: str) -> dict[str, Any]:
    return {
        "cik": cik,
        "n_cen": None,
        "prospectus": None,
        "errors": {},
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def fetch_series_filing_facts(
    series_id: str,
    cik: str,
    sample_ticker: str | None = None,
) -> dict[str, Any]:
    entry = _empty_entry(cik)
    n_cen, n_err = fetch_latest_ncen(series_id, cik)
    entry["n_cen"] = n_cen
    if n_err:
        entry["errors"]["n_cen"] = n_err

    prospectus, p_err = fetch_latest_prospectus(series_id, cik, sample_ticker)
    entry["prospectus"] = prospectus
    if p_err:
        entry["errors"]["prospectus"] = p_err

    entry["fetched_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return _json_safe(entry)


def refresh_edgar_filing_facts_cache(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    *,
    pause_seconds: float = PAUSE_SECONDS,
    save_every: int = SAVE_EVERY,
) -> dict:
    ensure_sec_identity()
    cache = load_filing_facts_cache(cache_path)
    cache.pop(NULLS_ARE_FINAL, None)

    worklist = _series_worklist(funds)
    pending_fetch: list[tuple[str, str, str | None]] = []
    pending_fund_types: list[tuple[str, str]] = []
    for _, row in worklist.iterrows():
        series_id = str(row["edgartools_series_id"])
        cik = str(row["edgartools_cik"])
        cached = cache.get(series_id)
        n_cen = cached.get("n_cen") if isinstance(cached, dict) else None
        if _ncen_is_cache_complete(n_cen):
            continue
        if isinstance(cached, dict) and _ncen_needs_fund_types_refresh(n_cen):
            pending_fund_types.append((series_id, cik))
            continue
        ticker = row.get("market_identifier")
        sample_ticker = (
            str(ticker).strip().upper()
            if isinstance(ticker, str) and ticker.strip()
            else None
        )
        pending_fetch.append((series_id, cik, sample_ticker))

    skipped = len(worklist) - len(pending_fetch) - len(pending_fund_types)
    print(
        f"{skipped} series loaded from the cache, "
        f"{len(pending_fund_types)} need N-CEN fund-type backfill, "
        f"{len(pending_fetch)} still to fetch"
    )

    # Process fund-type backfill first (N-CEN XML only), then full fetches.
    operations: list[tuple[str, str, str | None, str]] = [
        (series_id, cik, None, "fund_types")
        for series_id, cik in pending_fund_types
    ] + [
        (series_id, cik, sample_ticker, "fetch")
        for series_id, cik, sample_ticker in pending_fetch
    ]

    for index, (series_id, cik, sample_ticker, op) in enumerate(operations, start=1):
        try:
            if op == "fund_types":
                cached = cache.get(series_id)
                if not isinstance(cached, dict):
                    raise ValueError("missing cache entry for fund_types backfill")
                n_cen = cached.get("n_cen")
                if not isinstance(n_cen, dict):
                    raise ValueError("missing n_cen for fund_types backfill")
                entry_cik = cached.get("cik") if isinstance(cached.get("cik"), str) else cik
                updated, err = backfill_ncen_fund_types(
                    series_id, n_cen, cik=str(entry_cik or cik)
                )
                if updated is not None:
                    cached = dict(cached)
                    cached["n_cen"] = updated
                    if err:
                        errors = dict(cached.get("errors") or {})
                        errors["n_cen_fund_types"] = err
                        cached["errors"] = errors
                    cache[series_id] = cached
                elif err:
                    errors = dict((cached or {}).get("errors") or {})
                    errors["n_cen_fund_types"] = err
                    cached = dict(cached)
                    cached["errors"] = errors
                    cache[series_id] = cached
            else:
                cache[series_id] = fetch_series_filing_facts(
                    series_id, cik, sample_ticker
                )
        except Exception as exc:
            entry = _empty_entry(cik)
            entry["errors"]["fetch"] = str(exc)
            cache[series_id] = entry
            print(f"Failed {series_id}: {exc}")

        if index % save_every == 0 or index == len(operations):
            save_filing_facts_cache(cache, cache_path)
            ok_ncen = sum(
                isinstance(v, dict) and v.get("n_cen") is not None
                for k, v in cache.items()
                if not str(k).startswith("_")
            )
            ok_prosp = sum(
                isinstance(v, dict) and v.get("prospectus") is not None
                for k, v in cache.items()
                if not str(k).startswith("_")
            )
            print(
                f"{ok_ncen} series with N-CEN, {ok_prosp} with prospectus, "
                f"{index} of {len(operations)} requested"
            )

        if index < len(operations):
            time.sleep(pause_seconds)

    if operations:
        cache[NULLS_ARE_FINAL] = True
    save_filing_facts_cache(cache, cache_path)
    return cache


def fetch_edgar_filing_facts(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Refresh filing-facts cache for matched series; return funds unchanged."""
    cache = refresh_edgar_filing_facts_cache(funds, cache_path, **kwargs)
    series_keys = [
        k
        for k in cache
        if not str(k).startswith("_") and isinstance(cache[k], dict)
    ]
    with_ncen = sum(1 for k in series_keys if cache[k].get("n_cen"))
    with_prospectus = sum(1 for k in series_keys if cache[k].get("prospectus"))
    with_fund_types = sum(
        1
        for k in series_keys
        if isinstance((cache[k].get("n_cen") or {}).get("fund_types"), dict)
        and "is_index_fund" in (cache[k]["n_cen"]["fund_types"])
    )
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    print(
        f"EDGAR filing facts cache: {len(series_keys)} series at {path} "
        f"({with_ncen} N-CEN, {with_prospectus} prospectus, {with_fund_types} with fund_types)"
    )
    return funds
