import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import financedatabase as fd
import pandas as pd
from dotenv import find_dotenv, load_dotenv

DEFAULT_CACHE = Path("cache") / "cache-financedatabase.json"
NULLS_ARE_FINAL = "_nulls_are_final"
FMP_ARE_FINAL = "_fmp_are_final"
FMP_BASE = "https://financialmodelingprep.com/stable"
PRICE_SEARCH_START_YEAR = 1990
FMP_BULK_KEYS = (
    "holdings",
    "sector_weightings",
    "country_weightings",
    "disclosure_dates",
    "disclosure_latest",
)


def _code_root(start: Path | None = None) -> Path:
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        if (directory / "helpers").is_dir():
            return directory
    raise FileNotFoundError(f"Could not find helpers/, starting from {origin}")


def resolve_cache_path(cache_path: Path | None = None) -> Path:
    """Locate the FinanceDatabase cache on disk.

    Relative paths prefer ``code_root / relative`` so a notebook kernel in
    ``notebooks/`` uses the repo ``cache/`` folder.
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


def load_fd_cache(cache_path: Path | None = None) -> dict:
    """Load the identifier cache. An unreadable file counts as empty."""
    path = resolve_cache_path(cache_path)
    if not path.is_file():
        return {}
    try:
        cache = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return cache if isinstance(cache, dict) else {}


def save_fd_cache(cache: dict, cache_path: Path | None = None) -> None:
    """Save the identifier-to-record cache so the next run can reuse it."""
    path = resolve_cache_path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2) + "\n")


def is_stored_record(row) -> bool:
    """A cache hit is the FinanceDatabase row, not an empty miss."""
    return isinstance(row, dict) and "name" in row


def fmp_was_fetched(row) -> bool:
    fmp = row.get("fmp") if isinstance(row, dict) else None
    return isinstance(fmp, dict) and "prices" in fmp


def has_cached_price_span(row) -> bool:
    """True when the cache records an available price history span."""
    if not isinstance(row, dict):
        return False
    fmp = row.get("fmp")
    if isinstance(fmp, dict) and fmp.get("prices", {}).get("available") is True:
        return True
    return isinstance(row.get("timeseries"), dict)


def _trim_fmp_payload(fmp: dict) -> dict:
    for key in FMP_BULK_KEYS:
        fmp.pop(key, None)
    return fmp


def record_from_row(ticker: str, row: pd.Series) -> dict:
    """JSON-ready copy of one FinanceDatabase row, including its symbol."""
    record = {"symbol": str(ticker)}
    for column, value in row.items():
        if pd.isna(value):
            record[column] = None
        elif hasattr(value, "item"):
            record[column] = value.item()
        else:
            record[column] = value
    return record


def _load_fmp_api_key() -> str:
    load_dotenv(find_dotenv(usecwd=True))
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise RuntimeError("FMP_API_KEY is missing from .env")
    return api_key


def fmp_get(path: str, params: dict, api_key: str) -> list | None:
    """Call one FMP stable endpoint and return a JSON list, or None on error."""
    query = dict(params)
    query["apikey"] = api_key
    url = FMP_BASE + path + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": "memoire-alix-funds"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        if data.get("Error Message") or data.get("error") or data.get("message"):
            return None
        return None
    if isinstance(data, list):
        return data
    return None


def _unwrap_record(rows: list | None) -> dict | None:
    if not rows:
        return None
    first = rows[0]
    return first if isinstance(first, dict) else None


def probe_fmp_price_range(symbol: str, api_key: str) -> dict:
    """Find whether FMP has EOD prices and their span without caching the series."""
    today = date.today()
    recent = fmp_get(
        "/historical-price-eod/light",
        {
            "symbol": symbol,
            "from": (today - timedelta(days=120)).isoformat(),
            "to": today.isoformat(),
        },
        api_key,
    )
    if not recent:
        return {"available": False, "start": None, "end": None}

    recent_dates = [row["date"] for row in recent if isinstance(row, dict) and row.get("date")]
    if not recent_dates:
        return {"available": False, "start": None, "end": None}
    end = max(recent_dates)

    lo, hi = PRICE_SEARCH_START_YEAR, today.year
    first_year = None
    while lo <= hi:
        mid = (lo + hi) // 2
        window = fmp_get(
            "/historical-price-eod/light",
            {
                "symbol": symbol,
                "from": f"{mid}-01-01",
                "to": f"{mid}-12-31",
            },
            api_key,
        )
        if window:
            first_year = mid
            hi = mid - 1
        else:
            lo = mid + 1

    if first_year is None:
        return {"available": True, "start": min(recent_dates), "end": end}

    year_rows = fmp_get(
        "/historical-price-eod/light",
        {
            "symbol": symbol,
            "from": f"{first_year}-01-01",
            "to": f"{first_year}-12-31",
        },
        api_key,
    )
    year_dates = [
        row["date"] for row in (year_rows or []) if isinstance(row, dict) and row.get("date")
    ]
    start = min(year_dates) if year_dates else f"{first_year}-01-01"
    return {"available": True, "start": start, "end": end}


def fetch_fmp_static(symbol: str, api_key: str) -> dict:
    """Pull fund metadata from FMP and probe price availability (no price history stored)."""
    info = _unwrap_record(fmp_get("/etf/info", {"symbol": symbol}, api_key))
    profile = _unwrap_record(fmp_get("/profile", {"symbol": symbol}, api_key))
    quote = _unwrap_record(fmp_get("/quote", {"symbol": symbol}, api_key))
    listed = bool(info or profile or quote)

    dividends = fmp_get("/dividends", {"symbol": symbol}, api_key) or []
    splits = fmp_get("/splits", {"symbol": symbol}, api_key) or []

    prices = (
        probe_fmp_price_range(symbol, api_key)
        if listed
        else {"available": False, "start": None, "end": None}
    )

    return {
        "listed": listed,
        "info": info,
        "profile": profile,
        "quote": quote,
        "dividends": dividends,
        "splits": splits,
        "prices": prices,
    }


def _ensure_cache_row(cache: dict, ticker: str) -> dict:
    row = cache.get(ticker)
    if isinstance(row, dict):
        return row
    record = {"symbol": ticker}
    cache[ticker] = record
    return record


def refresh_fmp_cache(
    market_identifiers: list[str],
    fd_cache: dict,
    cache_path: Path | None = None,
) -> dict:
    """Attach FMP static metadata and price span to each cached market identifier."""
    trimmed = 0
    for row in fd_cache.values():
        if isinstance(row, dict) and isinstance(row.get("fmp"), dict):
            before = len(row["fmp"])
            _trim_fmp_payload(row["fmp"])
            if len(row["fmp"]) < before:
                trimmed += 1
    if trimmed:
        print(f"trimmed bulky FMP fields from {trimmed} cached rows")

    if not fd_cache.pop(FMP_ARE_FINAL, False):
        cleared = 0
        for ticker, row in list(fd_cache.items()):
            if isinstance(row, dict) and "fmp" in row:
                del row["fmp"]
                cleared += 1
        if cleared:
            print(f"dropped fmp blocks from {cleared} cached rows after an incomplete run")

    cached = [ticker for ticker in market_identifiers if fmp_was_fetched(fd_cache.get(ticker))]
    pending = [ticker for ticker in market_identifiers if not fmp_was_fetched(fd_cache.get(ticker))]
    print(
        f"{len(cached)} FMP records loaded from the cache, {len(pending)} still to look up"
    )

    if pending:
        api_key = _load_fmp_api_key()
        for index, ticker in enumerate(pending, start=1):
            row = _ensure_cache_row(fd_cache, ticker)
            row["fmp"] = fetch_fmp_static(ticker, api_key)
            if index % 25 == 0 or index == len(pending):
                save_fd_cache(fd_cache, cache_path)
                listed = sum(
                    isinstance(fd_cache.get(t), dict)
                    and isinstance(fd_cache[t].get("fmp"), dict)
                    and fd_cache[t]["fmp"].get("listed")
                    for t in market_identifiers
                    if fmp_was_fetched(fd_cache.get(t))
                )
                print(f"{listed} FMP-listed funds cached, {index} of {len(pending)} requested")

    fd_cache[FMP_ARE_FINAL] = True
    save_fd_cache(fd_cache, cache_path)
    return fd_cache


def _unique_market_identifiers(funds: pd.DataFrame) -> list[str]:
    return list(
        dict.fromkeys(
            ticker
            for ticker in funds["market_identifier"]
            if isinstance(ticker, str) and ticker
        )
    )


def refresh_fd_static_cache(
    market_identifiers: list[str],
    cache_path: Path | None = None,
) -> dict:
    """Look up static FinanceDatabase rows for market identifiers and persist cache."""
    fd_cache = load_fd_cache(cache_path)
    if not fd_cache.pop(NULLS_ARE_FINAL, False):
        dropped = [
            ticker
            for ticker, row in fd_cache.items()
            if not (
                isinstance(row, dict)
                and ("name" in row or "timeseries" in row or "fmp" in row)
            )
        ]
        for ticker in dropped:
            del fd_cache[ticker]
        if dropped:
            print(f"dropped {len(dropped)} cached misses from the incomplete run")

    cached = [
        ticker for ticker in market_identifiers if is_stored_record(fd_cache.get(ticker))
    ]
    pending = [ticker for ticker in market_identifiers if ticker not in fd_cache]
    print(
        f"{len(cached)} records loaded from the cache, {len(pending)} still to look up"
    )

    if pending:
        all_funds = fd.Funds().select()
        all_funds.index = all_funds.index.astype(str)
        for ticker in pending:
            if ticker not in all_funds.index:
                fd_cache[ticker] = None
                continue
            row = all_funds.loc[ticker]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            fd_cache[ticker] = record_from_row(ticker, row)

    fd_cache[NULLS_ARE_FINAL] = True
    save_fd_cache(fd_cache, cache_path)
    return fd_cache


def apply_financedatabase_static_flags(
    funds: pd.DataFrame, fd_cache: dict
) -> pd.DataFrame:
    """Mark funds that have a static FinanceDatabase row."""
    out = funds.copy()
    has_row = [
        is_stored_record(fd_cache.get(ticker))
        if isinstance(ticker, str) and ticker
        else False
        for ticker in out["market_identifier"]
    ]
    out["is_financedb_static"] = has_row
    out["has_fmp_prices"] = [
        isinstance(fd_cache.get(ticker), dict)
        and isinstance(fd_cache[ticker].get("fmp"), dict)
        and fd_cache[ticker]["fmp"].get("prices", {}).get("available") is True
        if isinstance(ticker, str) and ticker
        else False
        for ticker in out["market_identifier"]
    ]
    out["has_financedb_timeries"] = [
        has_cached_price_span(fd_cache.get(ticker))
        if isinstance(ticker, str) and ticker
        else False
        for ticker in out["market_identifier"]
    ]
    return out


def map_financedatabase(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """Match market identifiers with FinanceDatabase static fund metadata."""
    market_identifiers = _unique_market_identifiers(funds)
    print(
        f"Attempting to look up {len(market_identifiers)} market identifiers "
        "with financedatabase..."
    )
    fd_cache = refresh_fd_static_cache(market_identifiers, cache_path)
    print(
        f"Attempting to look up {len(market_identifiers)} market identifiers with FMP..."
    )
    fd_cache = refresh_fmp_cache(market_identifiers, fd_cache, cache_path)
    enriched = apply_financedatabase_static_flags(funds, fd_cache)
    found_count = sum(enriched["is_financedb_static"])
    fmp_price_count = sum(enriched["has_fmp_prices"])
    price_span_count = sum(enriched["has_financedb_timeries"])
    print(f"{found_count} of {len(enriched)} funds have a FinanceDatabase row")
    print(f"{found_count} of {len(enriched)} funds are marked is_FinanceDatabase")
    print(f"{fmp_price_count} of {len(enriched)} funds have FMP price history")
    print(f"{price_span_count} of {len(enriched)} funds have a cached price span")
    return enriched
