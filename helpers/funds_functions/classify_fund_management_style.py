"""Classify each EDGAR series as Passive, Active, Other, or Unknown.

N-CEN decides when the census states the style. Otherwise Jev reads the
prospectus text. Share classes of one series share one label.
"""

from __future__ import annotations

import json
import re
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from edgar import Company
from edgar.funds import Fund
from typesafe_sdk import Choice, TypeSafeClient

from helpers.funds_functions.fetch_edgar_filing_facts import parse_ncen_fund_types_for_series
from helpers.funds_functions.fund_management_style_rules import (
    STYLE_ACTIVE,
    STYLE_OTHER,
    STYLE_PASSIVE,
    STYLE_UNKNOWN,
    label_from_ncen,
    prospectus_excerpt,
    style_from_jev_choice,
)
from helpers.funds_functions.map_edgar_tickers import (
    cik_text,
    ensure_sec_identity,
    resolve_cache_path,
)

DEFAULT_CACHE = Path("cache") / "cache-fund-management-style.json"
RULE_VERSION = "ncen-jev-v1"
JEV_MODEL = "jev-latest"
PAUSE_SECONDS = 0.2
SERIES_ID = re.compile(r"S\d+", re.IGNORECASE)

NcenFetcher = Callable[[str], str | None]
ObjectiveFetcher = Callable[[str], str | None]
StatutoryFetcher = Callable[[str], tuple[str | None, str | None]]
ProspectusJudge = Callable[[str, str | None], tuple[str, str]]

MANAGEMENT_STYLE_QUESTION = Choice(
    instructions=(
        "Read `prospectus_text` for the fund named in `series_name`. "
        "How is that fund managed? Judge the fund's own job. "
        "A comparison index, or an index used only to describe which stocks "
        "the manager may buy, does not by itself make the fund passive."
    ),
    criteria={
        "Passive": (
            "The fund's job is to track, match, or approximate a stated index. "
            "It is not actively managed."
        ),
        "Active": (
            "A manager selects securities to meet an objective such as growth or income. "
            "Naming an index as a comparison or as a screen does not make the fund passive."
        ),
        "Other": (
            "The fund is a target-date fund, a fund of funds, or an interval fund, "
            "rather than a plain active or index fund."
        ),
    },
)


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False


def _text(value: object) -> str | None:
    if _missing(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "<na>"}:
        return None
    return text


def _series_id(value: object) -> str | None:
    text = _text(value)
    if text is None or SERIES_ID.fullmatch(text) is None:
        return None
    return text.upper()


def _cik(value: object) -> str | None:
    """Ten-digit CIK. A missing cell stays None; pandas map would turn that into float nan."""
    if _missing(value):
        return None
    cik = cik_text(value)
    if cik is None or not cik.isdigit():
        return None
    return cik


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if SERIES_ID.fullmatch(str(key))}


def _save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2))


def _cached_decision(cache: dict[str, Any], series_id: str, cik: str) -> dict[str, str] | None:
    entry = cache.get(series_id)
    if not isinstance(entry, dict):
        return None
    style = entry.get("style")
    if entry.get("cik") != cik:
        return None
    if entry.get("rule") != RULE_VERSION:
        return None
    if style not in {STYLE_PASSIVE, STYLE_ACTIVE, STYLE_OTHER, STYLE_UNKNOWN}:
        return None
    return {
        "style": style,
        "source": str(entry.get("source") or ""),
        "detail": str(entry.get("detail") or ""),
    }


def _store_decision(
    cache: dict[str, Any],
    path: Path,
    *,
    series_id: str,
    cik: str,
    decision: dict[str, str],
) -> None:
    cache[series_id] = {
        "rule": RULE_VERSION,
        "cik": cik,
        "style": decision["style"],
        "source": decision["source"],
        "detail": decision["detail"],
    }
    _save_cache(path, cache)


def _default_ncen_xml(cik: str) -> str | None:
    filings = Company(cik).get_filings(form="N-CEN")
    if filings is None or len(filings) == 0:
        return None
    xml = filings[0].xml()
    if isinstance(xml, bytes):
        return xml.decode("utf-8", "ignore")
    return xml or None


def _default_497k_objective(series_id: str) -> str | None:
    filings = Fund(series_id).get_filings(form="497K")
    if filings is None or len(filings) == 0:
        return None
    for index, filing in enumerate(filings):
        if index >= 5:
            break
        try:
            prospectus = filing.obj()
        except Exception:
            continue
        filed_series = getattr(prospectus, "series_id", None)
        if filed_series and str(filed_series) != series_id:
            continue
        objective = getattr(prospectus, "investment_objective", None)
        if objective:
            return str(objective)
    return None


def _default_485_text(series_id: str) -> tuple[str | None, str | None]:
    for form in ("485BPOS", "485APOS"):
        filings = Fund(series_id).get_filings(form=form)
        if filings is None or len(filings) == 0:
            continue
        try:
            text = filings[0].text() or ""
        except Exception:
            continue
        if text.strip():
            return text, form
    return None, None


def _ask_jev(client: TypeSafeClient, text: str, series_name: str | None) -> tuple[str, str]:
    response = client.system_one(
        state={"series_name": series_name or "", "prospectus_text": text},
        questions={"management_style": MANAGEMENT_STYLE_QUESTION},
        model=JEV_MODEL,
        timeout=120.0,
    )
    answer = response.choices["management_style"]
    style = style_from_jev_choice(answer.choice, float(answer.confidence))
    if style is None:
        return (
            STYLE_UNKNOWN,
            f"Jev chose {answer.choice} with confidence {float(answer.confidence):.2f}",
        )
    return style, f"Jev {style} confidence {float(answer.confidence):.2f}"


def _series_name_for(
    names: pd.Series,
    cik: pd.Series | None,
    series: pd.Series | None,
    cik_value: str,
    series_id: str,
) -> str | None:
    if cik is None or series is None:
        return None
    name_rows = names.loc[(cik == cik_value) & (series == series_id)]
    if len(name_rows) == 0:
        return None
    return next((value for value in name_rows.tolist() if value), None)


def _judge_prospectus(
    series_id: str,
    *,
    cik_value: str,
    cik: pd.Series | None,
    series: pd.Series | None,
    names: pd.Series,
    objective_fetcher: ObjectiveFetcher,
    statutory_fetcher: StatutoryFetcher,
    judge: ProspectusJudge,
    uses_network: bool,
    pause_seconds: float,
    ncen_detail: str,
) -> tuple[str, str, str]:
    """Send the prospectus objective, or the 485 strategy section, to the judge."""
    series_name = _series_name_for(names, cik, series, cik_value, series_id)
    try:
        objective = objective_fetcher(series_id)
    except Exception as exc:
        print(f"497K failed for {series_id}: {exc}")
        objective = None
    if uses_network:
        time.sleep(pause_seconds)

    prospectus = str(objective).strip() if objective and str(objective).strip() else ""
    if not prospectus:
        try:
            statutory, _form = statutory_fetcher(series_id)
        except Exception as exc:
            print(f"485 failed for {series_id}: {exc}")
            statutory = None
        if uses_network:
            time.sleep(pause_seconds)
        prospectus = prospectus_excerpt(statutory or "", series_name).strip()

    if not prospectus:
        return STYLE_UNKNOWN, "none", f"{ncen_detail}; no prospectus text"
    try:
        label, detail = judge(prospectus, series_name)
    except Exception as exc:
        print(f"Jev failed for {series_id}: {exc}")
        return STYLE_UNKNOWN, "none", f"Jev failed: {exc}"
    return label, "Jev", detail


def _insert(frame: pd.DataFrame, after: str, column: str, values: list) -> pd.DataFrame:
    if column in frame.columns:
        frame = frame.drop(columns=[column])
    loc = frame.columns.get_loc(after) + 1 if after in frame.columns else len(frame.columns)
    frame.insert(loc, column, values)
    return frame


def classify_fund_management_style(
    funds: pd.DataFrame,
    *,
    cache_path: Path | None = None,
    fetch_ncen_xml: NcenFetcher | None = None,
    fetch_497k_objective: ObjectiveFetcher | None = None,
    fetch_485_text: StatutoryFetcher | None = None,
    judge_prospectus: ProspectusJudge | None = None,
    pause_seconds: float = PAUSE_SECONDS,
) -> pd.DataFrame:
    """Add management-style columns for each row of ``funds``.

    Rows that share ``edgartools_cik`` and ``edgartools_series_id`` share one
    decision. Results are cached by series id so a later run does not repeat
    SEC requests.
    """
    uses_network = (
        fetch_ncen_xml is None or fetch_497k_objective is None or fetch_485_text is None
    )
    uses_jev = judge_prospectus is None
    if uses_network or uses_jev:
        ensure_sec_identity()
    ncen_fetcher = fetch_ncen_xml or _default_ncen_xml
    objective_fetcher = fetch_497k_objective or _default_497k_objective
    statutory_fetcher = fetch_485_text or _default_485_text

    path = resolve_cache_path(cache_path, default=DEFAULT_CACHE)
    cache = _load_cache(path)
    ncen_by_cik: dict[str, str | None] = {}

    # Build identifiers in Python. Series.map leaves a missing cell as float nan,
    # and float nan is truthy, so it was sent to EDGAR as a CIK.
    if "edgartools_cik" in funds.columns:
        cik = pd.Series(
            [_cik(value) for value in funds["edgartools_cik"].tolist()],
            index=funds.index,
        )
    else:
        cik = None
    if "edgartools_series_id" in funds.columns:
        series = pd.Series(
            [_series_id(value) for value in funds["edgartools_series_id"].tolist()],
            index=funds.index,
        )
    else:
        series = None
    if "edgar_series_name" in funds.columns:
        names = pd.Series(
            [_text(value) for value in funds["edgar_series_name"].tolist()],
            index=funds.index,
        )
    else:
        names = pd.Series([None] * len(funds), index=funds.index)

    decisions: dict[tuple[str, str], dict[str, str]] = {}
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if cik is not None and series is not None:
        for cik_value, series_id in zip(cik.tolist(), series.tolist()):
            if not cik_value or not series_id:
                continue
            pair = (cik_value, series_id)
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)

    print(f"{len(pairs)} EDGAR series to classify")
    with ExitStack() as stack:
        client: TypeSafeClient | None = None

        def judge(text: str, series_name: str | None) -> tuple[str, str]:
            nonlocal client
            if judge_prospectus is not None:
                return judge_prospectus(text, series_name)
            if client is None:
                client = stack.enter_context(TypeSafeClient(model=JEV_MODEL))
            return _ask_jev(client, text, series_name)

        for index, (cik_value, series_id) in enumerate(pairs, start=1):
            cached = _cached_decision(cache, series_id, cik_value)
            if cached is not None:
                decisions[(cik_value, series_id)] = cached
                continue

            if cik_value not in ncen_by_cik:
                try:
                    ncen_by_cik[cik_value] = ncen_fetcher(cik_value)
                except Exception as exc:
                    ncen_by_cik[cik_value] = None
                    print(f"N-CEN failed for CIK {cik_value}: {exc}")
                if uses_network:
                    time.sleep(pause_seconds)

            xml = ncen_by_cik[cik_value]
            parsed = parse_ncen_fund_types_for_series(xml, series_id) if xml else None
            label, detail = label_from_ncen(parsed)
            if label is None:
                label, source, detail = _judge_prospectus(
                    series_id,
                    cik_value=cik_value,
                    cik=cik,
                    series=series,
                    names=names,
                    objective_fetcher=objective_fetcher,
                    statutory_fetcher=statutory_fetcher,
                    judge=judge,
                    uses_network=uses_network,
                    pause_seconds=pause_seconds,
                    ncen_detail=detail,
                )
            else:
                source = "N-CEN"

            decision = {"style": label, "source": source, "detail": detail}
            decisions[(cik_value, series_id)] = decision
            _store_decision(cache, path, series_id=series_id, cik=cik_value, decision=decision)
            print(f"{index} of {len(pairs)} {series_id}: {label} ({source})")

    styles: list[str] = []
    sources: list[str | None] = []
    details: list[str] = []
    if cik is None or series is None:
        styles = [STYLE_UNKNOWN] * len(funds)
        sources = [None] * len(funds)
        details = ["no EDGAR series"] * len(funds)
    else:
        for cik_value, series_id in zip(cik.tolist(), series.tolist()):
            decision = decisions.get((cik_value or "", series_id or ""))
            if decision is None:
                styles.append(STYLE_UNKNOWN)
                sources.append(None)
                details.append("no EDGAR series")
            else:
                styles.append(decision["style"])
                sources.append(decision["source"])
                details.append(decision["detail"])

    out = funds.copy()
    anchor = "edgar_series_name" if "edgar_series_name" in out.columns else "edgartools_series_id"
    out = _insert(out, anchor, "fund_management_style", styles)
    out = _insert(out, "fund_management_style", "fund_management_style_source", sources)
    out = _insert(out, "fund_management_style_source", "fund_management_style_detail", details)

    counts = out["fund_management_style"].value_counts()
    summary = ", ".join(f"{count} {name}" for name, count in counts.items())
    print(summary)
    return out
