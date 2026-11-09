"""Corrections for the US funds whose OpenFIGI ticker missed the SEC series file.

The ticker join leaves three groups. A live series can be in the file with a
blank ticker, a series can have left the file after a merger or liquidation,
or the fund can be outside that file. Every reviewed fund stays in the dataset.
"""

import html

import pandas as pd

from helpers.funds_functions.check_openfigi_isin import names_match
from helpers.funds_functions.map_edgar_tickers import cik_text
from helpers.funds_functions.match_edgar_identifiers import _text, edgar_fund_name

STATUS_TICKER = "ticker"
STATUS_NAME = "name"
STATUS_CLOSED = "closed"
STATUS_UNMATCHABLE = "unmatchable"

# ISIN, class id, series id, resolution shown in the review.
NAME_CORRECTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("US0669235337", "C000117728", "S000004272", "iShares S&P 500 Index Fund, Service Shares (S000004272)"),
    ("US0669231948", "C000212062", "S000004272", "iShares S&P 500 Index Fund, Class G Shares (S000004272)"),
    ("US0669235667", "C000117725", "S000004272", "iShares S&P 500 Index Fund, Investor A Shares (S000004272)"),
    ("US00141B7588", "C000209245", "S000064631", "Invesco Main Street All Cap Fund, Class Y (S000064631). OpenFIGI's name says class A; the sheet class and this EDGAR class are Y."),
    ("US00141B7661", "C000209246", "S000064631", "Invesco Main Street All Cap Fund, Class R (S000064631)"),
    ("US00141B7828", "C000209248", "S000064631", "Invesco Main Street All Cap Fund, Class A (S000064631)"),
    ("US00141B6838", "C000209258", "S000064632", "Invesco Main Street Fund, Class Y (S000064632)"),
    ("US00141B7257", "C000209266", "S000064632", "Invesco Main Street Fund, Class A (S000064632)"),
    ("US00141B6911", "C000209256", "S000064632", "Invesco Main Street Fund, Class R (S000064632)"),
    ("US00141B6671", "C000209264", "S000064632", "Invesco Main Street Fund, Class R6 (S000064632)"),
    ("US00141B7174", "C000209253", "S000064632", "Invesco Main Street Fund, Class C (S000064632)"),
    ("US00141B5848", "C000209276", "S000064633", "Invesco Rising Dividends Fund, Class A (S000064633)"),
    ("US00141B5764", "C000209268", "S000064633", "Invesco Rising Dividends Fund, Class C (S000064633)"),
    ("US00141B5509", "C000209270", "S000064633", "Invesco Rising Dividends Fund, Class R (S000064633)"),
    ("US00141A1319", "C000188891", "S000027821", "Invesco S&P 500 Index Fund, Class R6 (S000027821)"),
    ("US7469167099", "C000202804", "S000006295", "Putnam Sustainable Leaders Fund, Class R6 Shares (S000006295)"),
    ("US64122Q1682", "C000244622", "S000007847", "Neuberger Quality Equity Fund, Class E (S000007847)"),
    ("US12811U3059", "C000238768", "S000078028", "Calamos Antetokounmpo Sustainable Equities Fund, Class I (S000078028)"),
    ("US15136Y4070", "C000234830", "S000075609", "Copley Fund (S000075609)"),
    ("US47805T7651", "C000173478", "S000055171", "U.S. Sector Rotation Fund, Class NAV (S000055171)"),
    ("US40169J4408", "C000272780", "S000102311", "Guggenheim Enhanced Equity Income ETF (S000102311)"),
    ("US66538R4415", "C000277295", "S000106434", "HCM Hedged Equity ETF (S000106434). The SEC ticker list assigns HAWG to a different series."),
    ("US45783Y5252", "C000245610", "S000082311", "Innovator Premium Income 20 Barrier ETF - October (S000082311)"),
    ("US45783Y4917", "C000245611", "S000082312", "Innovator Premium Income 30 Barrier ETF - October (S000082312)"),
    ("US45782C5085", "C000207058", "S000063995", "Innovator U.S. Equity Power Buffer ETF - January (S000063995)"),
    ("US45783Y6995", "C000237181", "S000077042", "Innovator Uncapped Accelerated U.S. Equity ETF (S000077042)"),
    ("US46090A6973", "C000250919", "S000085602", "Invesco S&P 500 Equal Weight Income Advantage ETF (S000085602)"),
    ("US66537J7708", "C000278281", "S000107377", "Main Active Rotation ETF (S000107377)"),
    ("US72201R5515", "C000266402", "S000097224", "PIMCO US Stocks PLUS Active Bond Exchange-Traded Fund (S000097224)"),
    ("US90386K5487", "C000267451", "S000097937", "Q3 All-Season Tactical Advantage ETF (S000097937)"),
    ("US77926Y8232", "C000273402", "S000102870", "Roundhill S&P 500 10,000 Target 2030 ETF (S000102870)"),
    ("US12811T5222", "C000273069", "S000102567", "Calamos Autocallable Growth ETF (S000102567)"),
    ("US2103225742", "C000267043", "S000097593", "TrueShares S&P Autocallable Defensive Income ETF (S000097593)"),
    ("US45259A1593", "C000277710", "S000106824", "VistaShares Shield S&P 500 Enhanced Protection ETF (S000106824)"),
)

CLOSED_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("US4791648656", "Merged into the Johnson Growth Fund on 16 December 2011."),
    ("US31678R6760", "Liquidated on 27 July 2012."),
    ("US31678R6273", "Liquidated on 27 July 2012."),
    ("US3167865654", "Liquidated on 27 July 2012."),
    ("US22540Y8663", "Merged into the Aberdeen U.S. Equity Fund in February 2013."),
    (
        "US31617F8178",
        "Terminated Fidelity-only feeder (FMALX). A different series from the live Fidelity Advisor Growth & Income Fund.",
    ),
)

UNMATCHABLE_CORRECTIONS: tuple[tuple[str, str], ...] = (
    (
        "US78462F1030",
        "Unit investment trust, CIK 0000884394. It files on EDGAR and is outside the open-end series-and-class file.",
    ),
    (
        "US92912M1053",
        "Unit investment trust, Series B, CIK 0000024924. Lipper labels it an open-end fund. It is a different fund from the Voya Corporate Leaders 100 Fund.",
    ),
    (
        "US00777X3970",
        "The SEC ticker list has class C000279343. That class is not in the series-and-class file, so there is no series id.",
    ),
)

_IDENTIFIER_COLUMNS = (
    "edgar_name",
    "edgartools_cik",
    "edgartools_series_id",
    "edgartools_class_id",
    "edgar_company_name",
    "edgar_series_name",
    "edgar_class_name",
)


def correction_catalog() -> pd.DataFrame:
    """One row per reviewed ISIN, in name, closed, then unmatchable order."""
    rows: list[dict] = []
    for isin, class_id, series_id, detail in NAME_CORRECTIONS:
        rows.append(
            {
                "ISIN": isin,
                "category": STATUS_NAME,
                "class_id": class_id,
                "series_id": series_id,
                "detail": detail,
            }
        )
    for isin, detail in CLOSED_CORRECTIONS:
        rows.append(
            {
                "ISIN": isin,
                "category": STATUS_CLOSED,
                "class_id": None,
                "series_id": None,
                "detail": detail,
            }
        )
    for isin, detail in UNMATCHABLE_CORRECTIONS:
        rows.append(
            {
                "ISIN": isin,
                "category": STATUS_UNMATCHABLE,
                "class_id": None,
                "series_id": None,
                "detail": detail,
            }
        )
    return pd.DataFrame(rows)


def correction_review(funds: pd.DataFrame) -> pd.DataFrame:
    """Reviewed funds with the sheet name, the planned resolution, and whether it is applied."""
    catalog = correction_catalog()
    sheet = funds.copy()
    sheet["ISIN"] = sheet["ISIN"].map(_text)
    keep = [column for column in ("Name", "openfigi_market_id", "edgar_match_status") if column in sheet.columns]
    review = catalog.merge(sheet.loc[:, ["ISIN", *keep]], on="ISIN", how="left")
    if "edgar_match_status" in review.columns:
        applied = review["edgar_match_status"].eq(review["category"])
    else:
        applied = pd.Series(False, index=review.index)
    review.insert(0, "applied", ["yes" if flag else "no" for flag in applied])
    review = review.drop(columns=["edgar_match_status"], errors="ignore")
    return review


def _object_column(frame: pd.DataFrame, column: str) -> None:
    if column not in frame.columns:
        frame[column] = pd.Series([None] * len(frame), index=frame.index, dtype="object")
    else:
        frame[column] = frame[column].astype("object")


def _clear_identifiers(out: pd.DataFrame, idx) -> None:
    for column in _IDENTIFIER_COLUMNS:
        out.at[idx, column] = None
    out.at[idx, "edgar_isin_found"] = False
    out.at[idx, "edgar_name_match"] = False


def _unescape_record(record: pd.Series) -> pd.Series:
    cleaned = record.copy()
    for key in ("series_name", "class_name", "company_name"):
        value = cleaned.get(key)
        if isinstance(value, str):
            cleaned[key] = html.unescape(value)
    return cleaned


def apply_edgar_unmatched_corrections(
    funds: pd.DataFrame,
    fund_reference: pd.DataFrame,
) -> pd.DataFrame:
    """Fill EDGAR identifiers for the reviewed funds and mark the other two groups.

    Name matches copy the SEC series and class whose ids are in the catalog.
    Closed and unmatchable funds stay in the frame with empty EDGAR identifiers.
    Rows already matched on ticker are marked ``ticker`` and left unchanged.
    """
    out = funds.copy()
    for column in ("edgar_match_status", "edgar_match_note", *_IDENTIFIER_COLUMNS):
        _object_column(out, column)
    if "edgar_isin_found" not in out.columns:
        out["edgar_isin_found"] = False
    if "edgar_name_match" not in out.columns:
        out["edgar_name_match"] = False

    reference = fund_reference.copy()
    reference["class_id"] = reference["class_id"].map(_text)
    reference["series_id"] = reference["series_id"].map(_text)
    name_by_isin = {
        isin: (class_id, series_id, detail)
        for isin, class_id, series_id, detail in NAME_CORRECTIONS
    }
    closed_notes = dict(CLOSED_CORRECTIONS)
    unmatchable_notes = dict(UNMATCHABLE_CORRECTIONS)

    name_count = 0
    closed_count = 0
    unmatchable_count = 0
    for idx, row in out.iterrows():
        isin = _text(row.get("ISIN"))
        if isin in name_by_isin:
            class_id, series_id, detail = name_by_isin[isin]
            hits = reference.loc[
                reference["class_id"].eq(class_id) & reference["series_id"].eq(series_id)
            ]
            if len(hits) != 1:
                out.at[idx, "edgar_match_status"] = None
                out.at[idx, "edgar_match_note"] = (
                    f"Class {class_id} in series {series_id} was not a single EDGAR row."
                )
                continue
            record = _unescape_record(hits.iloc[0])
            name = edgar_fund_name(record)
            out.at[idx, "edgar_isin_found"] = True
            out.at[idx, "edgar_name"] = name
            out.at[idx, "edgar_name_match"] = names_match(row.get("Name"), name) if name else False
            out.at[idx, "edgartools_cik"] = cik_text(record.get("cik"))
            out.at[idx, "edgartools_series_id"] = _text(record.get("series_id"))
            out.at[idx, "edgartools_class_id"] = _text(record.get("class_id"))
            out.at[idx, "edgar_company_name"] = _text(record.get("company_name"))
            out.at[idx, "edgar_series_name"] = _text(record.get("series_name"))
            out.at[idx, "edgar_class_name"] = _text(record.get("class_name"))
            out.at[idx, "edgar_match_status"] = STATUS_NAME
            out.at[idx, "edgar_match_note"] = detail
            name_count += 1
            continue
        if isin in closed_notes:
            _clear_identifiers(out, idx)
            out.at[idx, "edgar_match_status"] = STATUS_CLOSED
            out.at[idx, "edgar_match_note"] = closed_notes[isin]
            closed_count += 1
            continue
        if isin in unmatchable_notes:
            _clear_identifiers(out, idx)
            out.at[idx, "edgar_match_status"] = STATUS_UNMATCHABLE
            out.at[idx, "edgar_match_note"] = unmatchable_notes[isin]
            unmatchable_count += 1
            continue
        if bool(row.get("edgar_isin_found")):
            out.at[idx, "edgar_match_status"] = STATUS_TICKER
            out.at[idx, "edgar_match_note"] = None

    print(f"{name_count} funds matched by SEC series and class name")
    print(f"{closed_count} closed funds kept without an EDGAR series id")
    print(f"{unmatchable_count} funds kept with no series-and-class row")
    return out
