import pandas as pd

from helpers.funds_functions.check_openfigi_isin import (
    DEFAULT_ISIN_RECORD_CACHE,
    names_match,
)
from helpers.funds_functions.map_edgar_tickers import (
    cik_text,
    load_all_fund_reference_data,
)
from helpers.funds_functions.map_market_identifiers import load_isin_cache


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


def _ticker(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("ticker")
    text = _text(value)
    if text is None or text.lower() in {"none", "nan", "<na>"}:
        return None
    return text.upper()


def ticker_index(fund_reference: pd.DataFrame) -> pd.DataFrame:
    """One SEC row per ticker."""
    lookup = fund_reference.dropna(subset=["ticker"]).copy()
    lookup["ticker"] = lookup["ticker"].map(_ticker)
    lookup = lookup.loc[lookup["ticker"].notna()]
    return lookup.drop_duplicates("ticker").set_index("ticker")


def edgar_fund_name(record: pd.Series | None) -> str | None:
    """Series name plus share-class name, which is the fund name on the sheet."""
    if record is None:
        return None
    parts = [_text(record.get("series_name")), _text(record.get("class_name"))]
    name = " ".join(part for part in parts if part)
    return name or None


def _insert(frame: pd.DataFrame, after: str, column: str, values: list) -> pd.DataFrame:
    if column in frame.columns:
        frame = frame.drop(columns=[column])
    loc = frame.columns.get_loc(after) + 1 if after in frame.columns else len(frame.columns)
    frame.insert(loc, column, values)
    return frame


def match_edgar_identifiers(
    funds: pd.DataFrame,
    fund_reference: pd.DataFrame | None = None,
    isin_tickers: dict | None = None,
) -> pd.DataFrame:
    """Mark whether each ISIN resolves to an EDGAR fund record.

    EDGAR's reference table is keyed by ticker. The ticker comes from the
    OpenFIGI ISIN cache. The CUSIP resolves to the same ticker, so it is not
    looked up separately. ``edgar_name`` is filled only when that ticker is in
    EDGAR.
    """
    if fund_reference is None:
        fund_reference = load_all_fund_reference_data()
    if isin_tickers is None:
        isin_tickers = load_isin_cache(DEFAULT_ISIN_RECORD_CACHE)
    records = ticker_index(fund_reference)

    isin_found: list[bool] = []
    edgar_names: list[str | None] = []
    name_matches: list[bool] = []
    chosen: list[pd.Series | None] = []

    for row in funds.itertuples(index=False):
        isin = _text(getattr(row, "ISIN", None))
        isin_ticker = _ticker(isin_tickers.get(isin)) if isin else None
        record = records.loc[isin_ticker] if isin_ticker in records.index else None
        isin_found.append(record is not None)
        chosen.append(record)
        name = edgar_fund_name(record)
        edgar_names.append(name)
        name_matches.append(names_match(getattr(row, "Name", None), name) if name else False)

    out = funds.copy()
    out = _insert(out, "ISIN", "edgar_isin_found", isin_found)
    out = _insert(out, "Name", "edgar_name", edgar_names)
    out = _insert(out, "edgar_name", "edgar_name_match", name_matches)

    out["edgartools_cik"] = [cik_text(row.get("cik")) if row is not None else None for row in chosen]
    out["edgartools_series_id"] = [_text(row.get("series_id")) if row is not None else None for row in chosen]
    out["edgartools_class_id"] = [_text(row.get("class_id")) if row is not None else None for row in chosen]
    out["edgar_company_name"] = [_text(row.get("company_name")) if row is not None else None for row in chosen]
    out["edgar_series_name"] = [_text(row.get("series_name")) if row is not None else None for row in chosen]
    out["edgar_class_name"] = [_text(row.get("class_name")) if row is not None else None for row in chosen]

    matched = int(out["edgar_isin_found"].sum())
    print(f"{matched} of {len(out)} ISINs match an EDGAR record")
    print(f"{int(out.loc[out['edgar_isin_found'], 'edgar_name_match'].sum())} of {matched} EDGAR names match the sheet")
    return out
