import re
import time
from pathlib import Path

import pandas as pd

from helpers.funds_functions.map_market_identifiers import (
    BATCH_SIZE,
    NULLS_ARE_FINAL,
    PAUSE_SECONDS,
    _row_label,
    cusip_shape_ok,
    job_is_definitive,
    load_isin_cache,
    _unique_cusips,
    normalize_cusip,
    place_openfigi_columns,
    post_mapping,
    reconcile_openfigi_value,
    refresh_cusip_cache,
    save_isin_cache,
)

DEFAULT_ISIN_RECORD_CACHE = Path("cache") / "cache-isin-openfigi-record.json"
_ABBREVIATIONS = {
    "AM": "AMERICA",
    "CO": "COMPANY",
    "FUN": "FUND",
    "SRV": "SERVICE",
    "AMER": "AMERICAN",
    "BFR": "BUFFER",
    "COMP": "COMPANY",
    "COR": "CORE",
    "CP": "CAP",
    "DISC": "DISCIPLINED",
    "ENHANC": "ENHANCED",
    "EQ": "EQUITY",
    "EQTY": "EQUITY",
    "FD": "FUND",
    "FND": "FUND",
    "FNDMNTL": "FUNDAMENTAL",
    "GLDMN": "GOLDMAN",
    "GRW": "GROWTH",
    "IDX": "INDEX",
    "INST": "INSTITUTIONAL",
    "INV": "INVESTOR",
    "INVST": "INVESTORS",
    "INX": "INDEX",
    "IS": "INSTITUTIONAL",
    "LRG": "LARGE",
    "MTL": "MUTUAL",
    "MUT": "MUTUAL",
    "NATIONWD": "NATIONWIDE",
    "NTNWD": "NATIONWIDE",
    "NTWD": "NATIONWIDE",
    "PORT": "PORTFOLIO",
    "QLTY": "QUALITY",
    "SCHS": "SACHS",
    "SIIT": "SEI",
    "SIMT": "SEI",
    "STK": "STOCK",
    "STOC": "STOCK",
    "VLU": "VALUE",
    "WASH": "WASHINGTON",
}
_NAME_STOPWORDS = {"AND", "CLASS", "FUND", "FUNDS", "MUTUAL", "OF", "PORTFOLIO", "SERIES", "THE"}


def _name_tokens(value: object) -> list[str]:
    """Expand OpenFIGI short forms and drop words that are not part of the name."""
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except TypeError:
        pass
    text = str(value).upper().replace("&", " AND ").replace("L/C", " LARGE CAP ")
    text = text.replace("LARGECAP", "LARGE CAP").replace("MIDCAP", "MID CAP")
    text = text.replace("S AND P", "SP")
    text = text.replace("INV CO", "INVESTMENT COMPANY")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    words = [_ABBREVIATIONS.get(word, word) for word in text.split()]
    collapsed: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        nxt = words[index + 1] if index + 1 < len(words) else ""
        if len(word) == 1 and word.isalpha() and nxt.isdigit():
            collapsed.append(word + nxt)
            index += 2
            continue
        collapsed.append(word)
        index += 1
    kept = [word for word in collapsed if word not in _NAME_STOPWORDS]
    merged: list[str] = []
    for word in kept:
        if merged and len(merged[-1]) == 1 and merged[-1].isalpha() and word[:1].isalpha():
            merged[-1] = merged[-1] + word
            continue
        merged.append(word)
    return merged


def names_match(sheet_name: object, openfigi_name: object) -> bool:
    """True when the sheet name and the OpenFIGI name are the same fund.

    OpenFIGI shortens sponsors and share classes. The shorter token set must
    sit inside the longer one, so a real word change such as Core versus
    Growth still fails.
    """
    left = set(_name_tokens(sheet_name))
    right = set(_name_tokens(openfigi_name))
    if len(left) < 2 or len(right) < 2:
        return left == right and bool(left)
    smaller, larger = (left, right) if len(left) <= len(right) else (right, left)
    return smaller <= larger and len(smaller) / len(larger) >= 0.5


def preferred_row(job: dict) -> dict | None:
    """Pick the US listing when OpenFIGI returns more than one venue."""
    rows = job.get("data") or []
    for row in rows:
        if row.get("exchCode") == "US" and (row.get("ticker") or row.get("name")):
            return row
    return rows[0] if rows else None


def record_from_job(job: dict) -> dict | None:
    """Keep the name, ticker, and FIGI from one mapping result.

    The mapping payload includes ``name`` and does not include ``cusip``.
    """
    row = preferred_row(job)
    if row is None:
        return None
    record = {
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "figi": row.get("figi"),
    }
    if row.get("cusip"):
        record["cusip"] = row["cusip"]
    return record


def _unique_isins(funds: pd.DataFrame) -> list[str]:
    return list(
        dict.fromkeys(
            isin.strip()
            for isin in funds["ISIN"].dropna().astype(str)
            if isin.strip()
        )
    )


def refresh_isin_record_cache(
    isins: list[str],
    cache_path: Path | None = None,
    *,
    batch_size: int = BATCH_SIZE,
    pause_seconds: float = PAUSE_SECONDS,
) -> dict:
    """Fetch ISIN mapping records from OpenFIGI and persist them."""
    path = DEFAULT_ISIN_RECORD_CACHE if cache_path is None else cache_path
    cache = load_isin_cache(path)
    if not cache.pop(NULLS_ARE_FINAL, False):
        dropped = [isin for isin, record in cache.items() if record is None]
        for isin in dropped:
            del cache[isin]
        if dropped:
            print(f"dropped {len(dropped)} cached ISIN misses from the rate-limited run")

    pending = [isin for isin in isins if isin not in cache]
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        for isin, job in zip(batch, post_mapping(batch, "ID_ISIN")):
            if not job_is_definitive(job):
                continue
            cache[isin] = record_from_job(job)
        done = start + len(batch)
        found = sum(record is not None for record in cache.values())
        print(f"{found} ISINs found, {done} of {len(pending)} requested")
        save_isin_cache(cache, path)
        if done < len(pending):
            time.sleep(pause_seconds)

    cache[NULLS_ARE_FINAL] = True
    save_isin_cache(cache, path)
    return cache


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


def _listing_identity(value: object) -> tuple[str | None, str | None]:
    """Return the FIGI and ticker stored for one OpenFIGI listing."""
    if isinstance(value, dict):
        figi = _text(value.get("figi"))
        ticker = _text(value.get("ticker"))
        return figi, ticker.upper() if ticker else None
    if isinstance(value, str):
        ticker = _text(value)
        return None, ticker.upper() if ticker else None
    return None, None


def same_openfigi_record(isin_record: dict | None, cusip_entry: object) -> bool:
    """True when the ISIN lookup and the CUSIP lookup returned the same listing.

    FIGI is the listing id. When either cached entry has no FIGI, the tickers
    decide.
    """
    if not isinstance(isin_record, dict):
        return False
    left_figi, left_ticker = _listing_identity(isin_record)
    right_figi, right_ticker = _listing_identity(cusip_entry)
    if left_figi and right_figi:
        return left_figi == right_figi
    return bool(left_ticker and right_ticker and left_ticker == right_ticker)


def cusip_matches_record(
    sheet_cusip: object, isin_record: dict | None, cusip_cache: dict
) -> bool:
    """True when the file CUSIP maps to the same OpenFIGI listing as the ISIN."""
    if not isinstance(isin_record, dict):
        return False
    cusip = normalize_cusip(sheet_cusip)
    if not cusip or not cusip_shape_ok(cusip):
        return False
    return same_openfigi_record(isin_record, cusip_cache.get(cusip))


def apply_isin_checks(
    funds: pd.DataFrame, cache: dict, cusip_cache: dict | None = None
) -> pd.DataFrame:
    """Add ISIN hit and name/CUSIP agreement columns.

    The ISIN record's ticker and name are stored in ``openfigi_market_id`` and
    ``openfigi_name``. A value already stored there is replaced only when this
    lookup returns a different one. ``cusip_matches`` is true when a lookup of
    the file CUSIP returns the same OpenFIGI listing as the ISIN.
    """
    if cusip_cache is None:
        cusip_cache = {}
    isin_found: list[bool] = []
    market_ids: list[str | None] = []
    openfigi_names: list[str | None] = []
    name_ok: list[bool] = []
    cusip_ok: list[bool] = []
    has_market_identifier = "openfigi_market_id" in funds.columns
    has_name = "openfigi_name" in funds.columns
    for position in range(len(funds)):
        row = funds.iloc[position]
        isin = _text(row["ISIN"] if "ISIN" in funds.columns else None)
        record = cache.get(isin) if isin else None
        if not isinstance(record, dict):
            record = None
        fetched_name = record.get("name") if record else None
        fetched_id = record.get("ticker") if record else None
        label = _row_label(funds, position)
        prior_id = row["openfigi_market_id"] if has_market_identifier else None
        prior_name = row["openfigi_name"] if has_name else None
        isin_found.append(record is not None)
        market_ids.append(
            reconcile_openfigi_value(
                prior_id,
                fetched_id,
                column="openfigi_market_id",
                row_label=label,
                source="ISIN",
            )
        )
        openfigi_names.append(
            reconcile_openfigi_value(
                prior_name,
                fetched_name,
                column="openfigi_name",
                row_label=label,
                source="ISIN",
            )
        )
        sheet_name = row["Name"] if "Name" in funds.columns else None
        sheet_cusip = row["CUSIP"] if "CUSIP" in funds.columns else None
        name_ok.append(names_match(sheet_name, fetched_name))
        cusip_ok.append(cusip_matches_record(sheet_cusip, record, cusip_cache))

    out = funds.copy()
    for column in ("isin_found", "name_matches", "cusip_matches"):
        if column in out.columns:
            out = out.drop(columns=[column])
    out = place_openfigi_columns(out, market_ids, openfigi_names)
    columns = {
        "isin_found": isin_found,
        "name_matches": name_ok,
        "cusip_matches": cusip_ok,
    }
    insert_at = (
        out.columns.get_loc("openfigi_cusip_ok") + 1
        if "openfigi_cusip_ok" in out.columns
        else len(out.columns)
    )
    for offset, (column, values) in enumerate(columns.items()):
        out.insert(insert_at + offset, column, values)
    return out


def check_openfigi_isins(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    cusip_cache_path: Path | None = None,
    *,
    batch_size: int = BATCH_SIZE,
    pause_seconds: float = PAUSE_SECONDS,
) -> pd.DataFrame:
    """Map each ISIN, then map each file CUSIP, and compare the two listings."""
    cache = refresh_isin_record_cache(
        _unique_isins(funds),
        cache_path,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
    )
    cusips = _unique_cusips(funds) if "CUSIP" in funds.columns else []
    cusip_cache = refresh_cusip_cache(
        cusips,
        cusip_cache_path,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
    )
    checked = apply_isin_checks(funds, cache, cusip_cache)
    found = int(checked["isin_found"].sum())
    names = int(checked["name_matches"].sum())
    matched = int(checked["cusip_matches"].sum())
    print(f"{found} of {len(checked)} ISINs found in OpenFIGI")
    print(f"{names} of {len(checked)} names match the OpenFIGI record")
    print(f"{matched} of {len(checked)} CUSIPs return the same OpenFIGI record as the ISIN")
    return checked
