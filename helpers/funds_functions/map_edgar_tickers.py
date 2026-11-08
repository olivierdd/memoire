import html
import json
import os
import re
from pathlib import Path

import pandas as pd
from dotenv import find_dotenv, load_dotenv
from edgar import set_identity
from edgar.funds.reference import get_fund_reference_data
from edgar.reference.tickers import get_mutual_fund_tickers

DEFAULT_TICKERS_CACHE = Path("cache") / "cache-edgar-tickers.json"
DEFAULT_FUND_DATA_CACHE = Path("cache") / "cache-edgar-fund-data.json"
RECORDS_KEY = "records"


def _code_root(start: Path | None = None) -> Path:
    origin = (start or Path.cwd()).resolve()
    for directory in [origin, *origin.parents]:
        if (directory / "helpers").is_dir():
            return directory
    raise FileNotFoundError(f"Could not find helpers/, starting from {origin}")


def resolve_cache_path(
    cache_path: Path | None = None,
    *,
    default: Path = DEFAULT_TICKERS_CACHE,
) -> Path:
    relative = default if cache_path is None else Path(cache_path)
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


def _records_to_jsonable(df: pd.DataFrame) -> list[dict]:
    rows = df.where(pd.notna(df), None).to_dict(orient="records")
    for row in rows:
        for key, value in list(row.items()):
            if value is None:
                continue
            if isinstance(value, float) and value.is_integer():
                row[key] = int(value)
    return rows


def _load_edgar_records_cache(
    cache_path: Path | None,
    *,
    default: Path,
) -> pd.DataFrame | None:
    path = resolve_cache_path(cache_path, default=default)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    records = payload.get(RECORDS_KEY)
    if not isinstance(records, list) or not records:
        return None
    return pd.DataFrame(records)


def _save_edgar_records_cache(
    df: pd.DataFrame,
    cache_path: Path | None,
    *,
    default: Path,
) -> Path:
    path = resolve_cache_path(cache_path, default=default)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {RECORDS_KEY: _records_to_jsonable(df)}
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def load_edgar_tickers_cache(cache_path: Path | None = None) -> pd.DataFrame | None:
    return _load_edgar_records_cache(cache_path, default=DEFAULT_TICKERS_CACHE)


def save_edgar_tickers_cache(df: pd.DataFrame, cache_path: Path | None = None) -> Path:
    return _save_edgar_records_cache(df, cache_path, default=DEFAULT_TICKERS_CACHE)


def load_edgar_fund_data_cache(cache_path: Path | None = None) -> pd.DataFrame | None:
    return _load_edgar_records_cache(cache_path, default=DEFAULT_FUND_DATA_CACHE)


def save_edgar_fund_data_cache(df: pd.DataFrame, cache_path: Path | None = None) -> Path:
    return _save_edgar_records_cache(df, cache_path, default=DEFAULT_FUND_DATA_CACHE)


def ensure_sec_identity() -> None:
    load_dotenv(find_dotenv(usecwd=True))
    user_agent = os.getenv("SEC_USER_AGENT")
    if not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT is missing from .env. EDGAR requires a contact string such as 'Name (email@domain.com)'."
        )
    set_identity(user_agent)


def load_all_mutual_fund_tickers(cache_path: Path | None = None) -> pd.DataFrame:
    """Full SEC mutual-fund ticker table (cik, seriesId, classId, ticker). Uses cache when present."""
    cached = load_edgar_tickers_cache(cache_path)
    if cached is not None:
        print(f"{len(cached):,} EDGAR mutual-fund tickers loaded from the cache")
        return cached

    ensure_sec_identity()
    fund_tickers = get_mutual_fund_tickers()
    path = save_edgar_tickers_cache(fund_tickers, cache_path)
    print(f"Downloaded {len(fund_tickers):,} EDGAR mutual-fund tickers, saved to {path}")
    return fund_tickers


def load_all_fund_reference_data(cache_path: Path | None = None) -> pd.DataFrame:
    """SEC investment-company series/class reference (names, IDs, registrant address). Uses cache when present."""
    cached = load_edgar_fund_data_cache(cache_path)
    if cached is not None:
        print(f"{len(cached):,} EDGAR fund reference rows loaded from the cache")
        return cached

    ensure_sec_identity()
    fund_data = get_fund_reference_data().to_dataframe()
    path = save_edgar_fund_data_cache(fund_data, cache_path)
    print(f"Downloaded {len(fund_data):,} EDGAR fund reference rows, saved to {path}")
    return fund_data


def cik_text(value) -> str | None:
    if pd.isna(value):
        return None
    try:
        return str(int(value)).zfill(10)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None


def _id_text(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _normalize_ref_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = html.unescape(str(value)).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


# Lipper class suffixes that do not appear as words in the SEC class name.
_CLASS_HINT_ALIASES = {
    "invp": "investor p",
    "inva": "investor a",
}


def _class_key(value) -> str:
    text = _normalize_ref_text(value)
    text = re.sub(r"\bshares?\b", " ", text)
    text = re.sub(r"\bclass\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _CLASS_HINT_ALIASES.get(text, text)


def _lipper_series_and_class(name) -> tuple[str, str] | None:
    """Split a Lipper name like 'iShares S&P 500 Index Fund;Service'."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return None
    text = str(name)
    if ";" not in text:
        return None
    series, hint = text.split(";", 1)
    series_key = _normalize_ref_text(series)
    class_key = _class_key(hint)
    if not series_key or not class_key:
        return None
    return series_key, class_key


def _reference_name_index(fund_reference: pd.DataFrame) -> dict[tuple[str, str], object | None]:
    """Map (series name, class) to one SEC row. Ambiguous keys map to None."""
    needed = {"series_name", "class_name", "series_id", "class_id", "cik"}
    if not needed.issubset(fund_reference.columns):
        return {}
    buckets: dict[tuple[str, str], list] = {}
    for row in fund_reference.itertuples(index=False):
        key = (_normalize_ref_text(row.series_name), _class_key(row.class_name))
        if not key[0] or not key[1]:
            continue
        buckets.setdefault(key, []).append(row)
    index: dict[tuple[str, str], object | None] = {}
    for key, rows in buckets.items():
        series_ids = {_id_text(row.series_id) for row in rows}
        class_ids = {_id_text(row.class_id) for row in rows}
        index[key] = rows[0] if len(series_ids) == 1 and len(class_ids) == 1 else None
    return index


def _apply_name_match(out: pd.DataFrame, fund_reference: pd.DataFrame) -> int:
    if "Name" not in out.columns:
        return 0
    for column in (
        "edgartools_cik",
        "edgar_company_name",
        "edgar_series_name",
        "edgar_class_name",
    ):
        out[column] = out[column].astype("object")
    name_index = _reference_name_index(fund_reference)
    hits = 0
    for idx, fund in out.iterrows():
        if pd.notna(fund["edgartools_cik"]):
            continue
        key = _lipper_series_and_class(fund["Name"])
        if key is None:
            continue
        hit = name_index.get(key)
        if hit is None:
            continue
        out.at[idx, "edgartools_cik"] = cik_text(hit.cik)
        out.at[idx, "edgartools_series_id"] = _id_text(hit.series_id)
        out.at[idx, "edgartools_class_id"] = _id_text(hit.class_id)
        out.at[idx, "edgar_company_name"] = hit.company_name
        out.at[idx, "edgar_series_name"] = hit.series_name
        out.at[idx, "edgar_class_name"] = hit.class_name
        hits += 1
    return hits


def map_edgar_tickers(
    funds: pd.DataFrame,
    fund_data_cache_path: Path | None = None,
    fund_reference: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Match funds to EDGAR registrant / series / class using the SEC fund reference table.

    Ticker is the first key. Rows the SEC table lists with a blank ticker are then
    matched on Lipper ``Name`` (text before ``;`` = series, text after = class).
    """
    if fund_reference is None:
        fund_reference = load_all_fund_reference_data(fund_data_cache_path)
    lookup = fund_reference.dropna(subset=["ticker"]).copy()
    lookup["ticker"] = lookup["ticker"].astype(str).str.upper()
    records = lookup.drop_duplicates("ticker").set_index("ticker")

    keys = [
        ticker.upper() if isinstance(ticker, str) and ticker else None
        for ticker in funds["market_identifier"]
    ]
    matched = records.reindex(keys)

    out = funds.copy()
    out["edgartools_cik"] = [cik_text(value) for value in matched["cik"]]
    out["edgartools_series_id"] = (
        matched["series_id"].astype("string").mask(matched["series_id"].isna()).tolist()
    )
    out["edgartools_class_id"] = (
        matched["class_id"].astype("string").mask(matched["class_id"].isna()).tolist()
    )
    out["edgar_company_name"] = matched["company_name"].tolist()
    out["edgar_series_name"] = matched["series_name"].tolist()
    out["edgar_class_name"] = matched["class_name"].tolist()
    out["is_edgartools"] = out["edgartools_cik"].notna()
    ticker_count = int(out["is_edgartools"].sum())
    name_count = _apply_name_match(out, fund_reference)
    out["is_edgartools"] = out["edgartools_cik"].notna()
    print(f"{ticker_count} of {len(out)} funds match an EDGAR mutual-fund ticker")
    print(f"{name_count} additional funds matched by SEC series and class name")
    print(f"{out['edgartools_cik'].nunique(dropna=True)} distinct CIKs")
    return out
