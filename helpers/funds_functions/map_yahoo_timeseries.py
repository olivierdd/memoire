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


def _yahoo_close_levels(ticker: str, *, auto_adjust: bool) -> pd.Series | None:
    """Date-indexed Yahoo Close levels, or None when Yahoo has no history."""
    history = yf.Ticker(ticker).history(
        period="max", auto_adjust=auto_adjust, repair=False
    )
    if history is None or history.empty or "Close" not in history.columns:
        return None
    closes = history["Close"].dropna().copy()
    if closes.empty:
        return None
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes[~closes.index.duplicated(keep="last")].sort_index()
    closes.name = ticker
    return closes


def fetch_yahoo_total_return_levels(ticker: str) -> pd.Series | None:
    """Dividend-and-split-adjusted close levels (Yahoo total-return proxy).

    Uses ``auto_adjust=True`` so ``Close`` is adjusted for splits **and**
    dividends — not the raw NAV/price series. Returns a date-indexed Series, or
    None when Yahoo has no history.
    """
    return _yahoo_close_levels(ticker, auto_adjust=True)


def fetch_yahoo_price_levels(ticker: str) -> pd.Series | None:
    """Unadjusted close levels (Yahoo price/NAV proxy).

    Uses ``auto_adjust=False`` so ``Close`` is the raw price series, not the
    total-return proxy. Returns a date-indexed Series, or None when Yahoo has
    no history.
    """
    return _yahoo_close_levels(ticker, auto_adjust=False)


def align_yahoo_levels_to_index(
    levels: pd.Series,
    dates: pd.DatetimeIndex | pd.Index,
) -> pd.Series:
    """Map Yahoo levels onto the panel dates; missing Yahoo prints stay blank."""
    level_map = levels.copy()
    level_map.index = pd.to_datetime(level_map.index).normalize()
    level_map = level_map[~level_map.index.duplicated(keep="last")].sort_index()
    keys = pd.to_datetime(dates, errors="coerce")
    normalized = keys.normalize()
    aligned = level_map.reindex(normalized)
    aligned.index = dates
    return aligned.astype("float64")


def spx_flat_holiday_mask(
    market_level: pd.Series,
    *,
    level_tolerance: float = 1e-6,
) -> pd.Series:
    """True on dates where the S&P 500 TR level equals the prior close."""
    previous = market_level.shift(1)
    return (
        market_level.notna()
        & previous.notna()
        & (market_level - previous).abs().le(level_tolerance)
    )


def levels_and_returns_with_holiday_na(
    levels: pd.Series,
    holiday_mask: pd.Series | None,
) -> tuple[pd.Series, pd.Series]:
    """Align Yahoo levels; blank S&P-flat holidays; recompute the next session %."""
    filled = levels.astype("float64").copy()
    returns = filled.pct_change()
    if holiday_mask is None:
        return filled, returns
    mask = holiday_mask.reindex(filled.index).fillna(False)
    for index in range(len(filled)):
        if not bool(mask.iloc[index]):
            continue
        prior = filled.iloc[index - 1] if index > 0 else float("nan")
        filled.iloc[index] = float("nan")
        returns.iloc[index] = float("nan")
        if index + 1 < len(filled):
            nxt = filled.iloc[index + 1]
            if pd.notna(prior) and pd.notna(nxt) and float(prior) != 0.0:
                returns.iloc[index + 1] = float(nxt) / float(prior) - 1.0
    return filled, returns


def daily_sheet_observation_dates(daily: pd.DataFrame) -> pd.DatetimeIndex:
    """Date index for Datastream-shaped D-Timeseries rows 6+."""
    if len(daily) < 7 or daily.shape[1] < 1:
        raise ValueError("D-Timeseries has no label/observation rows")
    return pd.DatetimeIndex(pd.to_datetime(daily.iloc[6:, 0], errors="coerce"))


def holiday_mask_from_daily_sheet(
    daily: pd.DataFrame,
    *,
    header: str = "S&P 500 TR",
    level_tolerance: float = 1e-6,
) -> pd.Series | None:
    """S&P-flat holiday mask from a Datastream-shaped daily sheet, or None."""
    dates = daily_sheet_observation_dates(daily)
    header_row = daily.iloc[5, 1:]
    matches = [
        int(column)
        for column, value in header_row.items()
        if str(value).strip() == header
    ]
    if not matches:
        return None
    market = pd.to_numeric(daily.iloc[6:, matches[0]], errors="coerce")
    market.index = dates
    return spx_flat_holiday_mask(market, level_tolerance=level_tolerance)


def _append_level_return_pair(
    daily: pd.DataFrame,
    *,
    isin: str,
    level_name: str,
    return_name: str,
    category: str,
    fee: object,
    level_note: str,
    level_header: str,
    return_header: str,
    aligned: pd.Series,
    holiday_mask: pd.Series | None,
) -> pd.DataFrame:
    filled, returns = levels_and_returns_with_holiday_na(aligned, holiday_mask)
    level_meta = [isin, level_name, category, fee, level_note, level_header]
    return_meta = [
        isin,
        return_name,
        category,
        fee,
        "Daily simple return = P(t)/P(t-1) - 1",
        return_header,
    ]
    out = daily.copy()
    level_key = int(out.shape[1])
    return_key = level_key + 1
    out[level_key] = pd.Series(
        list(level_meta) + filled.tolist(), index=daily.index, dtype="object"
    )
    out[return_key] = pd.Series(
        list(return_meta) + returns.tolist(), index=daily.index, dtype="object"
    )
    out.columns = range(out.shape[1])
    return out


def append_yahoo_price_and_tr_columns(
    daily: pd.DataFrame,
    *,
    isin: str,
    ticker: str,
    fund_name: str,
    tr_levels: pd.Series,
    price_levels: pd.Series,
    category: str = "Yahoo TR",
    fee: object = None,
    holiday_mask: pd.Series | None = None,
) -> tuple[pd.DataFrame, int]:
    """Append Yahoo Price + TR pairs using the same recipe as series-check.

    - Price / Price % ← unadjusted Close (``auto_adjust=False``)
    - TR / TR % ← adjusted Close (``auto_adjust=True``)
    - Align to sheet dates; missing Yahoo prints stay blank
    - On S&P-flat holidays (when ``holiday_mask`` is provided), level and % are
      left NA and the next session’s return is recomputed from the prior close
    - Headers are primary ``{ISIN} Price`` / ``{ISIN} TR`` (and ``%`` companions)

    Returns the wider frame and the count of non-null TR observations.
    """
    dates = daily_sheet_observation_dates(daily)
    tr_aligned = align_yahoo_levels_to_index(tr_levels, dates)
    price_aligned = align_yahoo_levels_to_index(price_levels, dates)
    tr_observations = int(tr_aligned.notna().sum())
    price_observations = int(price_aligned.notna().sum())
    if tr_observations <= 0 or price_observations <= 0:
        return daily, 0

    stem = str(fund_name).strip() or ticker
    out = _append_level_return_pair(
        daily,
        isin=isin,
        level_name=f"{stem} - PRICE",
        return_name=f"{stem} - PRICE - daily return",
        category=category,
        fee=fee,
        level_note="Price, daily",
        level_header=f"{isin} Price",
        return_header=f"{isin} Price %",
        aligned=price_aligned,
        holiday_mask=holiday_mask,
    )
    out = _append_level_return_pair(
        out,
        isin=isin,
        level_name=f"{stem} - TOT RETURN IND",
        return_name=f"{stem} - TOT RETURN IND - daily return",
        category=category,
        fee=fee,
        level_note="Total return index, daily",
        level_header=f"{isin} TR",
        return_header=f"{isin} TR %",
        aligned=tr_aligned,
        holiday_mask=holiday_mask,
    )
    return out, tr_observations


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
