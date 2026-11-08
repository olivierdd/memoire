import time
from pathlib import Path

import pandas as pd
import yfinance as yf
from curl_cffi.requests.exceptions import HTTPError
from yfinance.exceptions import YFException, YFRateLimitError

from helpers.funds_functions.map_yahoo_static import (
    MAX_ATTEMPTS,
    PAUSE_SECONDS,
    RATE_LIMIT_SLEEP_SECONDS,
    SAVE_EVERY,
    load_yahoo_cache,
    save_yahoo_cache,
)

TIMESERIES_ARE_FINAL = "_timeseries_are_final"


def _unique_market_identifiers(funds: pd.DataFrame) -> list[str]:
    return list(
        dict.fromkeys(
            ticker
            for ticker in funds["market_identifier"]
            if isinstance(ticker, str) and ticker
        )
    )


def timeseries_was_checked(row) -> bool:
    return isinstance(row, dict) and "timeseries" in row


def store_timeseries(cache: dict, ticker: str, result: dict | None) -> None:
    """Attach a series result without dropping a static profile already cached."""
    row = cache.get(ticker)
    if isinstance(row, dict):
        row["timeseries"] = result
        return
    cache[ticker] = {"timeseries": result}


def date_text(value) -> str:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC")
    return stamp.date().isoformat()


def series_bounds(ticker: str) -> dict | None:
    """First and last close Yahoo has for this identifier. None when it has none."""
    history = yf.Ticker(ticker).history(period="max", auto_adjust=False, repair=False)
    if history is None or history.empty or "Close" not in history.columns:
        return None
    closes = history["Close"].dropna()
    if closes.empty:
        return None
    return {
        "start": date_text(closes.index.min()),
        "end": date_text(closes.index.max()),
        "source": "Yahoo",
    }


def _fetch_timeseries_with_retries(ticker: str) -> tuple[dict | None, bool]:
    """Return (bounds, finished). finished is False when rate-limited out of retries."""
    for _attempt in range(MAX_ATTEMPTS):
        try:
            return series_bounds(ticker), True
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
        except YFException:
            return None, True
    return None, False


def refresh_yahoo_timeseries_cache(
    market_identifiers: list[str],
    cache_path: Path | None = None,
    *,
    pause_seconds: float = PAUSE_SECONDS,
    save_every: int = SAVE_EVERY,
) -> dict:
    """Probe Yahoo price history spans for market identifiers and persist cache."""
    yahoo_cache = load_yahoo_cache(cache_path)
    if not yahoo_cache.pop(TIMESERIES_ARE_FINAL, False):
        cleared = 0
        for ticker, row in list(yahoo_cache.items()):
            if not timeseries_was_checked(row) or row["timeseries"] is not None:
                continue
            if row.get("description"):
                del row["timeseries"]
            else:
                yahoo_cache[ticker] = None
            cleared += 1
        if cleared:
            print(f"dropped {cleared} cached timeseries misses from the incomplete run")

    pending = [
        ticker
        for ticker in market_identifiers
        if not timeseries_was_checked(yahoo_cache.get(ticker))
    ]
    print(
        f"{len(market_identifiers) - len(pending)} timeseries results loaded from the cache, "
        f"{len(pending)} still to look up"
    )

    finished = True
    for index, ticker in enumerate(pending, start=1):
        bounds, stored = _fetch_timeseries_with_retries(ticker)
        if not stored:
            finished = False
            print(
                "Yahoo rate limit. Cached timeseries dates are saved; run the cell again to continue."
            )
            break
        store_timeseries(yahoo_cache, ticker, bounds)
        if index % save_every == 0 or index == len(pending):
            found = sum(
                isinstance(row, dict) and isinstance(row.get("timeseries"), dict)
                for row in yahoo_cache.values()
            )
            print(
                f"{found} timeseries cached, {index} of {len(pending)} identifiers requested"
            )
            save_yahoo_cache(yahoo_cache, cache_path)
        if index < len(pending):
            time.sleep(pause_seconds)

    if finished:
        yahoo_cache[TIMESERIES_ARE_FINAL] = True
    save_yahoo_cache(yahoo_cache, cache_path)
    return yahoo_cache


def apply_yahoo_timeseries_flags(
    funds: pd.DataFrame, yahoo_cache: dict
) -> pd.DataFrame:
    out = funds.copy()
    out["is_yahoo_timeseries"] = [
        isinstance(yahoo_cache.get(ticker), dict)
        and isinstance(yahoo_cache[ticker].get("timeseries"), dict)
        if isinstance(ticker, str) and ticker
        else False
        for ticker in out["market_identifier"]
    ]
    return out


def map_yahoo_timeseries(
    funds: pd.DataFrame,
    cache_path: Path | None = None,
    *,
    pause_seconds: float = PAUSE_SECONDS,
) -> pd.DataFrame:
    """Store first/last Yahoo close dates per market identifier (not full history)."""
    market_identifiers = _unique_market_identifiers(funds)
    yahoo_cache = refresh_yahoo_timeseries_cache(
        market_identifiers,
        cache_path,
        pause_seconds=pause_seconds,
    )
    enriched = apply_yahoo_timeseries_flags(funds, yahoo_cache)
    found_count = sum(enriched["is_yahoo_timeseries"])
    print(f"{found_count} of {len(enriched)} funds have a Yahoo price timeseries")
    return enriched
