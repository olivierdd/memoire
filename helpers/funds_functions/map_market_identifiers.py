import json
import time
from pathlib import Path

import pandas as pd
import requests

OPENFIGI_API_URL = "https://api.openfigi.com/v3/mapping"
DEFAULT_CACHE = Path("cache") / "cache-isin-openfigi.json"
DEFAULT_CUSIP_CACHE = Path("cache") / "cache-cusip-openfigi.json"
NULLS_ARE_FINAL = "_nulls_are_final"
BATCH_SIZE = 10
PAUSE_SECONDS = 2.5
NO_IDENTIFIER = "No identifier found."


def _code_root(start: Path | None = None) -> Path:
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        if (directory / "helpers").is_dir():
            return directory
    raise FileNotFoundError(f"Could not find helpers/, starting from {origin}")


def resolve_cache_path(cache_path: Path | None = None) -> Path:
    """Locate the OpenFIGI cache on disk.

    Relative paths prefer ``code_root / relative`` (the repo ``cache/`` folder)
    so a notebook kernel in ``notebooks/`` does not use a stray
    ``notebooks/cache/`` copy instead of the main cache.
    """
    relative = DEFAULT_CACHE if cache_path is None else Path(cache_path)
    if relative.is_absolute():
        return relative.resolve()

    origin = Path.cwd().resolve()
    try:
        canonical = (_code_root(origin) / relative).resolve()
        if canonical.is_file():
            return canonical
    except FileNotFoundError:
        canonical = None

    for directory in [origin, *origin.parents]:
        candidate = (directory / relative).resolve()
        if candidate.is_file():
            return candidate

    if canonical is not None:
        return canonical
    try:
        return (_code_root(origin) / relative).resolve()
    except FileNotFoundError:
        return (origin / relative).resolve()


def load_isin_cache(cache_path: Path | None = None) -> dict:
    """Load the ISIN-to-ticker mapping cache from disk as a dictionary."""
    path = resolve_cache_path(cache_path)
    if not path.is_file():
        return {}
    try:
        cache = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return cache if isinstance(cache, dict) else {}


def save_isin_cache(cache: dict, cache_path: Path | None = None) -> None:
    """Save the ISIN-to-ticker mapping cache to disk as a JSON file."""
    path = resolve_cache_path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2) + "\n")


def post_mapping(batch: list[str], id_type: str = "ID_ISIN") -> list[dict]:
    """
    Send a batch of identifiers to the OpenFIGI mapping API.
    Retries if rate-limited (HTTP 429). Unauthenticated calls allow 10 jobs
    per request and 25 requests per minute.
    """
    mapping = [{"idType": id_type, "idValue": value} for value in batch]
    headers = {"Content-Type": "application/json"}
    for _attempt in range(8):
        response = requests.post(
            OPENFIGI_API_URL, json=mapping, headers=headers, timeout=60
        )
        if response.status_code == 429:
            wait = int(
                response.headers.get("Retry-After")
                or response.headers.get("ratelimit-reset")
                or 60
            )
            print(f"OpenFIGI rate limit, sleeping {wait}s")
            time.sleep(wait)
            continue
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) != len(batch):
            raise RuntimeError("OpenFIGI returned an unexpected payload")
        return payload
    raise RuntimeError("OpenFIGI rate limit")


def ticker_from_job(job: dict) -> str | None:
    """Extract the market ticker symbol from an OpenFIGI API job response."""
    rows = job.get("data") or []
    if not rows:
        return None
    return rows[0].get("ticker")


def cusip_record_from_job(job: dict) -> dict | None:
    """Prefer the US listing and keep its ticker and name."""
    rows = job.get("data") or []
    chosen = next(
        (row for row in rows if row.get("exchCode") == "US" and row.get("ticker")),
        None,
    )
    if chosen is None and rows:
        chosen = rows[0]
    ticker = chosen.get("ticker") if chosen else None
    if not isinstance(ticker, str) or not ticker.strip():
        return None
    name = chosen.get("name") if chosen else None
    if not isinstance(name, str) or not name.strip():
        name = None
    record = {"ticker": ticker.strip(), "name": name.strip() if isinstance(name, str) else None}
    figi = chosen.get("figi") if chosen else None
    if isinstance(figi, str) and figi.strip():
        record["figi"] = figi.strip()
    return record


def cusip_ticker_from_job(job: dict) -> str | None:
    """Prefer the US listing ticker when OpenFIGI returns several venues."""
    record = cusip_record_from_job(job)
    return record["ticker"] if record else None


def cached_cusip_fields(value: object) -> tuple[str | None, str | None]:
    """Read a ticker and name from a current record or a legacy ticker string."""
    if isinstance(value, dict):
        ticker = value.get("ticker")
        name = value.get("name")
        ticker = ticker.strip() if isinstance(ticker, str) and ticker.strip() else None
        name = name.strip() if isinstance(name, str) and name.strip() else None
        return ticker, name
    if isinstance(value, str) and value.strip():
        return value.strip(), None
    return None, None


def cusip_cache_is_current(value: object) -> bool:
    """A current entry is a definitive miss or a record that includes the name."""
    if value is None:
        return True
    return isinstance(value, dict) and "ticker" in value and "name" in value


def _openfigi_text(value: object) -> str | None:
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


def _row_label(funds: pd.DataFrame, position: int) -> str:
    row = funds.iloc[position]
    for column in ("Name", "ISIN", "CUSIP"):
        if column not in funds.columns:
            continue
        text = _openfigi_text(row[column])
        if text:
            return text
    return str(funds.index[position])


def reconcile_openfigi_value(
    existing: object,
    fetched: object,
    *,
    column: str,
    row_label: str,
    source: str,
) -> str | None:
    """Keep a stored OpenFIGI value unless the new lookup returns a different one.

    A lookup that returns nothing leaves the stored value in place. A different
    ticker or name replaces the stored value and prints an alert.
    """
    current = _openfigi_text(existing)
    incoming = _openfigi_text(fetched)
    if incoming is None:
        return current
    if current is None or current.casefold() == incoming.casefold():
        return incoming
    print(
        f"OpenFIGI alert: {source} {column} for {row_label} "
        f"differs from the stored value ({current} -> {incoming}). "
        f"Replaced with {incoming}."
    )
    return incoming


def place_openfigi_columns(
    frame: pd.DataFrame,
    market_ids: list[str | None],
    names: list[str | None],
) -> pd.DataFrame:
    """Store the OpenFIGI ticker and name immediately after ``CUSIP``."""
    out = frame.copy()
    for column in ("openfigi_market_id", "openfigi_name"):
        if column in out.columns:
            out = out.drop(columns=[column])
    loc = out.columns.get_loc("CUSIP") + 1 if "CUSIP" in out.columns else len(out.columns)
    out.insert(loc, "openfigi_market_id", market_ids)
    out.insert(loc + 1, "openfigi_name", names)
    return out


def job_is_definitive(job: dict) -> bool:
    """True when OpenFIGI found a FIGI or reported that the identifier is unknown."""
    if not isinstance(job, dict):
        return False
    if job.get("data"):
        return True
    if job.get("warning"):
        return True
    return job.get("error") == NO_IDENTIFIER


def normalize_cusip(value: object) -> str | None:
    """Return a stripped CUSIP, or None when the cell is empty."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).strip().upper()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def cusip_shape_ok(cusip: str) -> bool:
    """CUSIPs sent to OpenFIGI are 9 alphanumeric characters."""
    return len(cusip) == 9 and cusip.isalnum()


def _unique_isins(funds: pd.DataFrame) -> list[str]:
    return list(
        dict.fromkeys(
            isin.strip()
            for isin in funds["ISIN"].dropna().astype(str)
            if isin.strip()
        )
    )


def refresh_isin_cache(
    isins: list[str],
    cache_path: Path | None = None,
    *,
    batch_size: int = BATCH_SIZE,
    pause_seconds: float = PAUSE_SECONDS,
) -> dict:
    """Fetch missing ISIN mappings from OpenFIGI and persist the cache."""
    isin_cache = load_isin_cache(cache_path)
    if not isin_cache.pop(NULLS_ARE_FINAL, False):
        dropped = [isin for isin, ticker in isin_cache.items() if ticker is None]
        for isin in dropped:
            del isin_cache[isin]
        if dropped:
            print(f"dropped {len(dropped)} cached misses from the rate-limited run")

    pending = [isin for isin in isins if isin not in isin_cache]
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        for isin, job in zip(batch, post_mapping(batch)):
            isin_cache[isin] = ticker_from_job(job)
        done = start + len(batch)
        mapped = sum(ticker is not None for ticker in isin_cache.values())
        print(f"{mapped} tickers cached, {done} of {len(pending)} ISINs requested")
        save_isin_cache(isin_cache, cache_path)
        if done < len(pending):
            time.sleep(pause_seconds)

    isin_cache[NULLS_ARE_FINAL] = True
    save_isin_cache(isin_cache, cache_path)
    return isin_cache


def apply_market_identifiers(
    funds: pd.DataFrame, isin_cache: dict
) -> pd.DataFrame:
    """Add ``market_identifier`` and ``market_ticker`` from an ISIN cache."""
    out = funds.copy()
    out["market_identifier"] = [
        isin_cache.get(isin.strip()) if isinstance(isin, str) and isin.strip() else None
        for isin in out["ISIN"]
    ]
    out["market_ticker"] = out["market_identifier"]
    return out


def map_market_identifiers(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    *,
    batch_size: int = BATCH_SIZE,
    pause_seconds: float = PAUSE_SECONDS,
) -> pd.DataFrame:
    """Resolve OpenFIGI tickers for fund ISINs and attach them to ``funds``."""
    isins = _unique_isins(funds)
    isin_cache = refresh_isin_cache(
        isins,
        cache_path,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
    )
    enriched = apply_market_identifiers(funds, isin_cache)
    mapped_rows = sum(ticker is not None for ticker in enriched["market_identifier"])
    print(f"{mapped_rows} of {len(enriched)} funds have a market identifier")
    return enriched


def _unique_cusips(funds: pd.DataFrame) -> list[str]:
    return list(
        dict.fromkeys(
            cusip
            for value in funds["CUSIP"]
            if (cusip := normalize_cusip(value)) and cusip_shape_ok(cusip)
        )
    )


def refresh_cusip_cache(
    cusips: list[str],
    cache_path: Path | None = None,
    *,
    batch_size: int = BATCH_SIZE,
    pause_seconds: float = PAUSE_SECONDS,
) -> dict:
    """Fetch missing CUSIP mappings from OpenFIGI and persist the cache."""
    path = DEFAULT_CUSIP_CACHE if cache_path is None else cache_path
    cusip_cache = load_isin_cache(path)
    if not cusip_cache.pop(NULLS_ARE_FINAL, False):
        dropped = [cusip for cusip, ticker in cusip_cache.items() if ticker is None]
        for cusip in dropped:
            del cusip_cache[cusip]
        if dropped:
            print(f"dropped {len(dropped)} cached CUSIP misses from the rate-limited run")

    pending = [
        cusip
        for cusip in cusips
        if not cusip_cache_is_current(cusip_cache.get(cusip, False))
    ]
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        for cusip, job in zip(batch, post_mapping(batch, "ID_CUSIP")):
            if not job_is_definitive(job):
                continue
            cusip_cache[cusip] = cusip_record_from_job(job)
        done = start + len(batch)
        mapped = sum(
            cached_cusip_fields(value)[0] is not None for value in cusip_cache.values()
        )
        print(f"{mapped} tickers cached, {done} of {len(pending)} CUSIPs requested")
        save_isin_cache(cusip_cache, path)
        if done < len(pending):
            time.sleep(pause_seconds)

    cusip_cache[NULLS_ARE_FINAL] = True
    save_isin_cache(cusip_cache, path)
    return cusip_cache


def apply_cusip_market_identifiers(
    funds: pd.DataFrame, cusip_cache: dict
) -> pd.DataFrame:
    """Insert the OpenFIGI ticker, name, and match flag immediately after ``CUSIP``.

    ``openfigi_cusip_ok`` is true only when OpenFIGI returned a ticker for that CUSIP.
    ``openfigi_name`` is the name on that same listing. A value already stored in
    either column is replaced only when this lookup returns a different one.
    """
    identifiers: list[str | None] = []
    names: list[str | None] = []
    cusip_ok: list[bool] = []
    has_id = "openfigi_market_id" in funds.columns
    has_name = "openfigi_name" in funds.columns
    for position, value in enumerate(funds["CUSIP"]):
        cusip = normalize_cusip(value)
        entry = cusip_cache.get(cusip) if cusip and cusip_shape_ok(cusip) else None
        ticker, name = cached_cusip_fields(entry)
        label = _row_label(funds, position)
        prior_id = funds.iloc[position]["openfigi_market_id"] if has_id else None
        prior_name = funds.iloc[position]["openfigi_name"] if has_name else None
        identifiers.append(
            reconcile_openfigi_value(
                prior_id, ticker, column="openfigi_market_id", row_label=label, source="CUSIP"
            )
        )
        names.append(
            reconcile_openfigi_value(
                prior_name, name, column="openfigi_name", row_label=label, source="CUSIP"
            )
        )
        cusip_ok.append(ticker is not None)

    out = funds.copy()
    for column in ("openfigi_cusip_ok", "market_identifier", "cusip_ok"):
        if column in out.columns:
            out = out.drop(columns=[column])
    out = place_openfigi_columns(out, identifiers, names)
    out.insert(out.columns.get_loc("openfigi_name") + 1, "openfigi_cusip_ok", cusip_ok)
    return out


def map_cusip_market_identifiers(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    *,
    batch_size: int = BATCH_SIZE,
    pause_seconds: float = PAUSE_SECONDS,
) -> pd.DataFrame:
    """Verify each CUSIP with OpenFIGI and attach the market identifier."""
    cusips = _unique_cusips(funds)
    cusip_cache = refresh_cusip_cache(
        cusips,
        cache_path,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
    )
    enriched = apply_cusip_market_identifiers(funds, cusip_cache)
    ok = int(enriched["openfigi_cusip_ok"].sum())
    print(f"{ok} of {len(enriched)} rows have a CUSIP OpenFIGI recognizes")
    return enriched
