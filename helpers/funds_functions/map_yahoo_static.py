import json
import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from curl_cffi.requests.exceptions import HTTPError
from yfinance.exceptions import YFDataException, YFRateLimitError

DEFAULT_CACHE = Path("cache") / "cache-yahoo.json"
NULLS_ARE_FINAL = "_nulls_are_final"
PAUSE_SECONDS = 0.5
SAVE_EVERY = 10
MAX_ATTEMPTS = 6
RATE_LIMIT_SLEEP_SECONDS = 60


def _code_root(start: Path | None = None) -> Path:
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        if (directory / "helpers").is_dir():
            return directory
    raise FileNotFoundError(f"Could not find helpers/, starting from {origin}")


def resolve_cache_path(cache_path: Path | None = None) -> Path:
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


def load_yahoo_cache(cache_path: Path | None = None) -> dict:
    """Load the Yahoo static-profile cache. An unreadable file counts as empty."""
    path = resolve_cache_path(cache_path)
    if not path.is_file():
        return {}
    try:
        cache = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return cache if isinstance(cache, dict) else {}


def save_yahoo_cache(cache: dict, cache_path: Path | None = None) -> None:
    """Save the identifier-to-description cache so the next run can reuse it."""
    path = resolve_cache_path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2) + "\n")


def static_record(ticker: str) -> dict | None:
    """Yahoo fund description and profile. None when Yahoo has no description."""
    fund = yf.Ticker(ticker).funds_data
    description = (fund.description or "").strip()
    if not description:
        return None
    overview = fund.fund_overview or {}
    return {
        "symbol": ticker,
        "quote_type": fund.quote_type(),
        "description": description,
        "category_name": overview.get("categoryName"),
        "family": overview.get("family"),
        "legal_type": overview.get("legalType"),
    }


def _unique_market_identifiers(funds: pd.DataFrame) -> list[str]:
    return list(
        dict.fromkeys(
            ticker
            for ticker in funds["market_identifier"]
            if isinstance(ticker, str) and ticker
        )
    )


def _fetch_with_retries(ticker: str) -> tuple[dict | None, bool]:
    """Return (record, finished). finished is False when rate-limited out of retries."""
    for _attempt in range(MAX_ATTEMPTS):
        try:
            return static_record(ticker), True
        except YFRateLimitError:
            print("Yahoo rate limit, sleeping 60s")
            time.sleep(RATE_LIMIT_SLEEP_SECONDS)
        except HTTPError as error:
            status = getattr(error.response, "status_code", None)
            if status == 429:
                print("Yahoo rate limit, sleeping 60s")
                time.sleep(RATE_LIMIT_SLEEP_SECONDS)
                continue
            return None, True
        except YFDataException:
            return None, True
    return None, False


def refresh_yahoo_static_cache(
    market_identifiers: list[str],
    cache_path: Path | None = None,
    *,
    pause_seconds: float = PAUSE_SECONDS,
    save_every: int = SAVE_EVERY,
) -> dict:
    """Look up Yahoo fund descriptions for market identifiers and persist cache."""
    yahoo_cache = load_yahoo_cache(cache_path)
    if not yahoo_cache.pop(NULLS_ARE_FINAL, False):
        dropped = [ticker for ticker, row in yahoo_cache.items() if row is None]
        for ticker in dropped:
            del yahoo_cache[ticker]
        if dropped:
            print(f"dropped {len(dropped)} cached misses from the incomplete run")

    pending = [ticker for ticker in market_identifiers if ticker not in yahoo_cache]
    print(
        f"{len(market_identifiers) - len(pending)} descriptions loaded from the cache, "
        f"{len(pending)} still to look up"
    )

    finished = True
    for index, ticker in enumerate(pending, start=1):
        record, stored = _fetch_with_retries(ticker)
        if not stored:
            finished = False
            print(
                "Yahoo rate limit. Cached descriptions are saved; run the cell again to continue."
            )
            break
        yahoo_cache[ticker] = record
        if index % save_every == 0 or index == len(pending):
            described = sum(
                isinstance(row, dict) and bool(row.get("description"))
                for row in yahoo_cache.values()
            )
            print(
                f"{described} descriptions cached, {index} of {len(pending)} identifiers requested"
            )
            save_yahoo_cache(yahoo_cache, cache_path)
        if index < len(pending):
            time.sleep(pause_seconds)

    if finished:
        yahoo_cache[NULLS_ARE_FINAL] = True
    save_yahoo_cache(yahoo_cache, cache_path)
    return yahoo_cache


def apply_yahoo_static_flags(
    funds: pd.DataFrame, yahoo_cache: dict
) -> pd.DataFrame:
    out = funds.copy()
    out["is_yahoo_static"] = [
        isinstance(yahoo_cache.get(ticker), dict)
        and bool(yahoo_cache[ticker].get("description"))
        if isinstance(ticker, str) and ticker
        else False
        for ticker in out["market_identifier"]
    ]
    return out


def map_yahoo_static(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    *,
    pause_seconds: float = PAUSE_SECONDS,
) -> pd.DataFrame:
    """Fetch Yahoo static fund profiles for market identifiers."""
    market_identifiers = _unique_market_identifiers(funds)
    print(
        f"Attempting to look up {len(market_identifiers)} market identifiers with Yahoo..."
    )
    yahoo_cache = refresh_yahoo_static_cache(
        market_identifiers,
        cache_path,
        pause_seconds=pause_seconds,
    )
    enriched = apply_yahoo_static_flags(funds, yahoo_cache)
    found_count = sum(enriched["is_yahoo_static"])
    print(f"{found_count} of {len(enriched)} funds have a Yahoo static description")
    return enriched
