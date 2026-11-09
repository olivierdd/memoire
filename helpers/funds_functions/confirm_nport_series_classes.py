"""Confirm share classes of one series against the series N-PORT filing.

The SEC fund-reference table supplies the series and class identifiers. The
N-PORT is a separate filing. Its ``genInfo/seriesId`` is the portfolio, the
``monthlyTotReturn`` class ids are the classes reported for that portfolio,
and ``invstOrSec`` is the single holdings list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from lxml import etree

from edgar.funds.reports import _strip_namespaces

from helpers.funds_functions.map_edgar_tickers import ensure_sec_identity, resolve_cache_path

DEFAULT_CACHE = Path("cache") / "cache-nport-series-classes.json"
RULE_VERSION = "nport-series-class-v1"
COLUMN = "nport_same_series"
MAX_FILINGS = 2

CONFIRMED = "confirmed"
NO_HOLDINGS = "no holdings"
CLASS_ABSENT = "class absent"
CIK_MISMATCH = "CIK mismatch"
SERIES_MISMATCH = "series mismatch"
NO_NPORT = "no N-PORT"
NO_CLASS_ID = "no class id"

_RANK = {
    CONFIRMED: 0,
    NO_HOLDINGS: 1,
    CLASS_ABSENT: 2,
    CIK_MISMATCH: 3,
    SERIES_MISMATCH: 4,
}


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


def _cik_key(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    digits = "".join(character for character in text if character.isdigit())
    if not digits:
        return None
    return str(int(digits))


def _child_text(element: etree._Element | None, tag: str) -> str | None:
    if element is None:
        return None
    for child in element:
        if child.tag == tag and child.text and child.text.strip():
            return child.text.strip()
    return None


def parse_nport_series_check(xml: str | bytes) -> dict[str, Any]:
    """Read the series id, class ids, and holdings flag from one N-PORT XML."""
    payload = xml.encode("utf-8") if isinstance(xml, str) else xml
    root = etree.fromstring(payload)
    _strip_namespaces(root)
    general = root.find(".//genInfo")
    class_ids: list[str] = []
    for monthly_return in root.findall(".//monthlyTotReturn"):
        class_id = (monthly_return.get("classId") or "").strip()
        if class_id and class_id not in class_ids:
            class_ids.append(class_id)
    return {
        "series_id": _child_text(general, "seriesId"),
        "cik": _child_text(general, "regCik"),
        "class_ids": class_ids,
        "has_holdings": root.find(".//invstOrSec") is not None,
        "report_date": _child_text(general, "repPdDate"),
    }


def _filing_outcome(
    filing: dict[str, Any],
    *,
    series_id: str,
    cik: str | None,
    class_id: str,
) -> tuple[str, str | None]:
    report_date = _text(filing.get("report_date"))
    filed_series = _text(filing.get("series_id"))
    if filed_series != series_id:
        return SERIES_MISMATCH, report_date
    filed_cik = _cik_key(filing.get("cik"))
    row_cik = _cik_key(cik)
    if filed_cik and row_cik and filed_cik != row_cik:
        return CIK_MISMATCH, report_date
    filed_classes = {_text(value) for value in filing.get("class_ids") or []}
    filed_classes.discard(None)
    if class_id in filed_classes and filing.get("has_holdings"):
        return CONFIRMED, report_date
    if class_id in filed_classes:
        return NO_HOLDINGS, report_date
    return CLASS_ABSENT, report_date


def label_for_class(
    *,
    series_id: str,
    cik: object = None,
    class_id: object = None,
    filings: list[dict[str, Any]],
) -> str:
    """Label one share class from newest-first N-PORT snapshots."""
    expected_class = _text(class_id)
    if expected_class is None:
        return NO_CLASS_ID
    expected_series = _text(series_id)
    if expected_series is None:
        return SERIES_MISMATCH
    if not filings:
        return NO_NPORT

    outcomes = [
        _filing_outcome(
            filing,
            series_id=expected_series,
            cik=_text(cik),
            class_id=expected_class,
        )
        for filing in filings
    ]
    best = min(_RANK[kind] for kind, _date in outcomes)
    dates: list[str] = []
    for kind, report_date in outcomes:
        if _RANK[kind] == best and report_date and report_date not in dates:
            dates.append(report_date)
    kind = next(name for name, rank in _RANK.items() if rank == best)
    if not dates:
        return kind
    return f"{kind} ({', '.join(dates)})"


def _all_confirmed(series_id: str, class_ids: set[str], filings: list[dict[str, Any]]) -> bool:
    if not class_ids or not filings:
        return False
    return all(
        label_for_class(series_id=series_id, class_id=class_id, filings=filings).startswith(
            CONFIRMED
        )
        for class_id in class_ids
    )


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"rule": RULE_VERSION, "series": {}}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {"rule": RULE_VERSION, "series": {}}
    if not isinstance(payload, dict) or payload.get("rule") != RULE_VERSION:
        return {"rule": RULE_VERSION, "series": {}}
    series = payload.get("series")
    if not isinstance(series, dict):
        payload["series"] = {}
    return payload


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _cache_answers(entry: dict[str, Any], series_id: str, class_ids: set[str]) -> bool:
    filings = entry.get("filings")
    if not isinstance(filings, list):
        return False
    if entry.get("exhausted"):
        return True
    return bool(class_ids) and _all_confirmed(series_id, class_ids, filings)


def _filing_xml(filing: Any) -> str | None:
    xml = filing.xml()
    if isinstance(xml, bytes):
        xml = xml.decode("utf-8", "ignore")
    text = _text(xml)
    return text


def fetch_nport_filings(
    series_id: str,
    class_ids: set[str],
    *,
    cache_path: Path | None = None,
    fund_factory: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Return up to two newest N-PORT snapshots for ``series_id``.

    The second filing is read only when the latest one does not confirm every
    requested class. A completed lookup is reused from the cache.
    """
    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    cache = _load_cache(path)
    cached = cache["series"].get(series_id)
    needed = {_text(value) for value in class_ids}
    needed.discard(None)
    if isinstance(cached, dict) and _cache_answers(cached, series_id, needed):
        return list(cached.get("filings") or [])

    ensure_sec_identity()
    factory = fund_factory or _fund
    filings = factory(series_id).get_filings(form="NPORT-P", series_only=True)
    parsed: list[dict[str, Any]] = []
    exhausted = True
    if filings:
        for filing in filings:
            xml = _filing_xml(filing)
            if xml is None:
                continue
            parsed.append(parse_nport_series_check(xml))
            if len(parsed) >= MAX_FILINGS:
                break
            if _all_confirmed(series_id, needed, parsed):
                exhausted = False
                break
        else:
            exhausted = True
    if filings and not parsed:
        raise RuntimeError(f"unreadable N-PORT for {series_id}")

    cache["series"][series_id] = {"filings": parsed, "exhausted": exhausted}
    _save_cache(path, cache)
    return parsed


def _fund(series_id: str) -> Any:
    from edgar.funds import Fund

    return Fund(series_id)


def add_nport_same_series(
    frame: pd.DataFrame,
    *,
    fetch_filings: Callable[[str, set[str]], list[dict[str, Any]]] | None = None,
) -> pd.DataFrame:
    """Copy ``frame`` and set ``nport_same_series`` for each row.

    Rows that share ``edgartools_series_id`` share one N-PORT lookup.
    ``fetch_filings(series_id, class_ids)`` returns newest-first snapshots.
    An empty list means the series has no N-PORT. An exception labels every
    class of that series ``error: ...``.
    """
    required = ["edgartools_cik", "edgartools_series_id", "edgartools_class_id"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")

    loader = fetch_filings or fetch_nport_filings
    out = frame.copy()
    labels = pd.Series(index=out.index, dtype="object")
    series_ids = []
    for value in out["edgartools_series_id"].tolist():
        series_id = _text(value)
        if series_id and series_id not in series_ids:
            series_ids.append(series_id)

    snapshots: dict[str, list[dict[str, Any]] | str] = {}
    for index, series_id in enumerate(series_ids, start=1):
        rows = out.loc[out["edgartools_series_id"].astype("string").str.strip().eq(series_id)]
        class_ids = {
            class_id
            for class_id in (_text(value) for value in rows["edgartools_class_id"].tolist())
            if class_id
        }
        try:
            filings = loader(series_id, class_ids)
        except Exception as exc:
            snapshots[series_id] = f"error: {exc}"
            print(f"{index} of {len(series_ids)} {series_id}: error: {exc}")
            continue
        snapshots[series_id] = filings
        print(f"{index} of {len(series_ids)} {series_id}: {_series_status(series_id, rows, filings)}")

    for row_index, row in out.iterrows():
        series_id = _text(row["edgartools_series_id"])
        if series_id is None:
            labels.at[row_index] = SERIES_MISMATCH
            continue
        loaded = snapshots.get(series_id)
        if isinstance(loaded, str):
            labels.at[row_index] = loaded
            continue
        labels.at[row_index] = label_for_class(
            series_id=series_id,
            cik=row["edgartools_cik"],
            class_id=row["edgartools_class_id"],
            filings=loaded or [],
        )
    out[COLUMN] = labels
    return out


def _series_status(series_id: str, rows: pd.DataFrame, filings: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for _index, row in rows.iterrows():
        label = label_for_class(
            series_id=series_id,
            cik=row["edgartools_cik"],
            class_id=row["edgartools_class_id"],
            filings=filings,
        )
        kind = label.split(" (", 1)[0]
        counts[kind] = counts.get(kind, 0) + 1
    return ", ".join(f"{kind} {count}" for kind, count in counts.items())
