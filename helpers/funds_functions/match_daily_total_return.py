import re

import pandas as pd

TOTAL_RETURN_NOTE = "Total return index, daily"
_LABEL_ROWS = 6
_SERIES_SUFFIX = " - TOT RETURN IND"
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
_NAME_COLUMNS = ("Name", "openfigi_name", "edgar_name")

# Datastream cuts words and uses its own short forms. The value is the word
# those letters stand for when it is compared with a fund name.
_ABBREVIATIONS = {
    "ASST": "ASSET",
    "ADVG": "ADVANTAGE",
    "AUG": "AUGUST",
    "BDS": "BONDS",
    "CHRTR": "CHARTER",
    "ADVS": "ADVISOR",
    "ADVY": "ADVISORY",
    "AGRSIV": "AGGRESSIVE",
    "AMER": "AMERICAN",
    "BLCHP": "BLUE CHIP",
    "CAPTL": "CAPITAL",
    "CENT": "CENTURY",
    "CO": "COMPANY",
    "CP": "CAP",
    "CRE": "CORE",
    "CTRY": "CENTURY",
    "DIS": "DISCIPLINED",
    "DIST": "DISTRIBUTION",
    "DIV": "DIVIDEND",
    "DSPD": "DISCIPLINED",
    "ENH": "ENHANCED",
    "EQ": "EQUITY",
    "EQTY": "EQUITY",
    "EQT": "EQUITY",
    "EQWGT": "EQUAL WEIGHT",
    "FDS": "FUNDS",
    "FST": "FIRST",
    "FD": "FUND",
    "FID": "FIDELITY",
    "FND": "FUND",
    "FNDM": "FUNDAMENTAL",
    "FNDMNTL": "FUNDAMENTAL",
    "FOCD": "FOCUSED",
    "FUN": "FUND",
    "GD": "GOLD",
    "GLDMN": "GOLDMAN",
    "GLDS": "GOLDMAN",
    "GRW": "GROWTH",
    "GW": "GROWTH",
    "IDX": "INDEX",
    "INS": "INSTITUTIONAL",
    "INST": "INSTITUTIONAL",
    "INSTL": "INSTITUTIONAL",
    "INV": "INVESTMENT",
    "INVR": "INVESTOR",
    "INVRS": "INVESTORS",
    "INVST": "INVESTORS",
    "INVSTMT": "INVESTMENT",
    "INVS": "INVESTMENTS",
    "INX": "INDEX",
    "IS": "INSTITUTIONAL",
    "IVS": "INVESCO",
    "JAN": "JANUARY",
    "LG": "LARGE",
    "LGE": "LARGE",
    "LGCP": "LARGECAP",
    "LRG": "LARGE",
    "MGD": "MANAGED",
    "MUT": "MUTUAL",
    "MTH": "MONTH",
    "RDV": "DIVIDEND",
    "NWIDE": "NATIONWIDE",
    "NY": "NEW YORK",
    "OPPS": "OPPORTUNITIES",
    "PFOLIO": "PORTFOLIO",
    "PRCL": "PRINCIPAL",
    "PRI": "PRIME",
    "PRTF": "PORTFOLIO",
    "PT": "PORTFOLIO",
    "QLT": "QUALITY",
    "RESH": "RESEARCH",
    "REYND": "REYNOLDS",
    "SELCT": "SELECT",
    "SHRE": "SHARES",
    "SHS": "SHARES",
    "SP5": "SP 500",
    "STK": "STOCK",
    "STKS": "STOCKS",
    "STD": "STANDARD",
    "STRUCD": "STRUCTURED",
    "TST": "TRUST",
    "UN": "UNION",
    "VAL": "VALUE",
    "VANGD": "VANGUARD",
    "VLU": "VALUE",
    "WASH": "WASHINGTON",
}
_STOP = {
    "AND",
    "CLASS",
    "CL",
    "COMPANY",
    "FUND",
    "FUNDS",
    "MUTUAL",
    "OF",
    "PORTFOLIO",
    "SERIES",
    "SHARE",
    "SHARES",
    "THE",
    "TRUST",
}
_VOWELS = set("AEIOU")


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


def _isin(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    text = text.upper()
    return text if _ISIN.fullmatch(text) else None


def series_label(value: object) -> str | None:
    """Datastream instrument name, without the total-return suffix."""
    text = _text(value)
    if text is None:
        return None
    if text.endswith(_SERIES_SUFFIX):
        text = text[: -len(_SERIES_SUFFIX)].strip()
    return text or None


def _tokens(value: object) -> list[str]:
    text = _text(value)
    if text is None:
        return []
    text = text.upper().replace("S&P", "SP").replace("U.S.", "US").replace("U.S", "US")
    text = text.replace("CAPITALIZATION", "CAPITAL").replace("&", " AND ")
    raw = re.findall(r"[A-Z0-9]+", text)
    tokens: list[str] = []
    for token in raw:
        expanded = _ABBREVIATIONS.get(token, token)
        tokens.extend(re.findall(r"[A-Z0-9]+", expanded))
    return [token for token in tokens if token not in _STOP and len(token) > 1]


def _skeleton(token: str) -> str:
    letters = "".join(character for character in token if character not in _VOWELS)
    return letters or token


def _truncation(shorter: str, longer: str, *, limit: int) -> bool:
    return longer.startswith(shorter) and 0 < len(longer) - len(shorter) <= limit


def _same_word(left: str, right: str) -> bool:
    """True when two tokens are the same word or a short form of it."""
    if left == right:
        return True
    if left.startswith("INVEST") and right.startswith("INVEST"):
        return True
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    extra = len(long) - len(short)
    if long.startswith(short) and (
        (len(short) >= 5 and extra <= 8) or (len(short) >= 3 and extra <= 4)
    ):
        return True
    short_skeleton = _skeleton(short)
    long_skeleton = _skeleton(long)
    if short_skeleton == long_skeleton and len(short_skeleton) >= 3:
        return True
    return (
        len(short_skeleton) >= 3
        and long_skeleton.startswith(short_skeleton)
        and len(long_skeleton) - len(short_skeleton) <= 2
    )


def _join_fits(joined: str, unit: str) -> bool:
    """A joined Datastream token matches one fund word, without swallowing a suffix."""
    if joined == unit:
        return True
    joined_skeleton = _skeleton(joined)
    unit_skeleton = _skeleton(unit)
    if joined_skeleton == unit_skeleton and len(joined_skeleton) >= 3:
        return True
    return len(joined) >= 4 and _truncation(joined, unit, limit=4)


def _joined(tokens: list[str]) -> list[str]:
    units = list(tokens)
    for width in (2, 3):
        for start in range(len(tokens) - width + 1):
            units.append("".join(tokens[start : start + width]))
    return units


def datastream_names_match(series_name: object, fund_name: object) -> bool:
    """True when a Datastream label and a fund name are the same fund.

    Dots and short forms still match. An extra word of five letters or more,
    such as Value against Equity, does not.
    """
    series = _tokens(series_name)
    fund = _tokens(fund_name)
    if not series or not fund:
        return False
    units = _joined(fund)
    used = [False] * len(series)
    for width in (3, 2):
        start = 0
        while start <= len(series) - width:
            if any(used[start : start + width]):
                start += 1
                continue
            joined = "".join(series[start : start + width])
            if any(_join_fits(joined, unit) for unit in units):
                used[start : start + width] = [True] * width
                start += width
            else:
                start += 1
    for index, token in enumerate(series):
        if not used[index] and any(_same_word(token, unit) for unit in units):
            used[index] = True
    content = [(token, ok) for token, ok in zip(series, used) if len(token) >= 3]
    if not content:
        return all(used)
    unmatched = [token for token, ok in content if not ok]
    matched = [token for token, ok in content if ok]
    if any(len(token) >= 5 for token in unmatched) or not matched:
        return False
    if len(matched) / len(content) < 0.6:
        return False
    return all(ok for _, ok in content) or any(len(token) >= 4 for token in matched)


def _confirm(label: str | None, row: pd.Series) -> str | None:
    if label is None:
        return None
    for column in _NAME_COLUMNS:
        if column not in row.index:
            continue
        if datastream_names_match(label, row[column]):
            return column
    return None


def daily_total_return_catalog(daily: pd.DataFrame) -> pd.DataFrame:
    """One row per daily total-return column on the D-Timeseries sheet.

    The sheet has no column header. Row 1 is the id, row 2 the name, and row 5
    the note. Observations start on row 7.
    """
    if len(daily) <= _LABEL_ROWS:
        raise ValueError("D-Timeseries has labels but no observations")
    identifiers = daily.iloc[0].tolist()
    names = daily.iloc[1].tolist()
    notes = daily.iloc[4].tolist()
    rows: list[dict] = []
    for position, note in enumerate(notes):
        if note != TOTAL_RETURN_NOTE:
            continue
        observations = pd.to_numeric(daily.iloc[_LABEL_ROWS:, position], errors="coerce")
        rows.append(
            {
                "column": position,
                "isin": _isin(identifiers[position]),
                "label": series_label(names[position]),
                "observations": int(observations.notna().sum()),
            }
        )
    return pd.DataFrame(rows, columns=["column", "isin", "label", "observations"])


def _insert(frame: pd.DataFrame, after: str, column: str, values: list) -> pd.DataFrame:
    if column in frame.columns:
        frame = frame.drop(columns=[column])
    loc = frame.columns.get_loc(after) + 1 if after in frame.columns else len(frame.columns)
    frame.insert(loc, column, values)
    return frame


def match_daily_total_return(funds: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Mark which funds have a daily total return series on D-Timeseries.

    The ISIN is the key. The series name is then checked against the sheet
    name. When that does not confirm the series, the OpenFIGI name is used,
    then the EDGAR name. A column with no ISIN can still match by name when
    that name fits exactly one selected fund.
    """
    catalog = daily_total_return_catalog(daily)
    by_isin: dict[str, pd.Series] = {}
    for _, series in catalog.iterrows():
        if series["isin"] is None or int(series["observations"]) <= 0:
            continue
        current = by_isin.get(series["isin"])
        if current is None or int(series["observations"]) > int(current["observations"]):
            by_isin[series["isin"]] = series

    assigned: dict[object, tuple[pd.Series, str | None]] = {}
    for index, row in funds.iterrows():
        series = by_isin.get(_isin(row["ISIN"]) if "ISIN" in funds.columns else None)
        if series is None:
            continue
        assigned[index] = (series, _confirm(series["label"], row))

    used = {id(series) for series, _ in assigned.values()}
    pending = [index for index in funds.index if index not in assigned]
    claims: list[tuple[pd.Series, object, str]] = []
    for _, series in catalog.iterrows():
        if series["isin"] is not None or int(series["observations"]) <= 0:
            continue
        if id(series) in used:
            continue
        hits = [
            (index, source)
            for index in pending
            if (source := _confirm(series["label"], funds.loc[index])) is not None
        ]
        if len(hits) == 1:
            claims.append((series, hits[0][0], hits[0][1]))
    fund_claims: dict[object, int] = {}
    column_claims: dict[int, int] = {}
    for series, index, _source in claims:
        fund_claims[index] = fund_claims.get(index, 0) + 1
        column_claims[int(series["column"])] = column_claims.get(int(series["column"]), 0) + 1
    for series, index, source in claims:
        if fund_claims[index] == 1 and column_claims[int(series["column"])] == 1:
            assigned[index] = (series, source)

    has_series: list[bool] = []
    observations: list[int] = []
    labels: list[str | None] = []
    matches: list[bool] = []
    sources: list[str | None] = []
    for index in funds.index:
        found = assigned.get(index)
        if found is None:
            has_series.append(False)
            observations.append(0)
            labels.append(None)
            matches.append(False)
            sources.append(None)
            continue
        series, source = found
        has_series.append(True)
        observations.append(int(series["observations"]))
        labels.append(series["label"])
        matches.append(source is not None)
        sources.append(source)

    out = funds.copy()
    anchor = "ISIN" if "ISIN" in out.columns else out.columns[-1]
    for column, values in (
        ("daily_tr_name_source", sources),
        ("daily_tr_name_match", matches),
        ("daily_tr_name", labels),
        ("daily_tr_observations", observations),
        ("has_daily_total_return", has_series),
    ):
        out = _insert(out, anchor, column, values)
    found = sum(has_series)
    print(f"{found} of {len(out)} funds have a daily total return series")
    print(f"{sum(matches)} of {found} series names match Name, OpenFIGI, or EDGAR")
    return out
