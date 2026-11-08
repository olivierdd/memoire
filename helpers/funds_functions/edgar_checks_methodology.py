"""Thesis-style documentation for the Edgar-checks export (second worksheet)."""

from __future__ import annotations

METHODOLOGY_SHEET_NAME = "Methodology"

# (section heading or None for continuation, body text)
METHODOLOGY_ROWS: list[tuple[str | None, str]] = [
    (
        "Purpose",
        "This workbook documents how U.S. mutual fund and ETF share classes from the Lipper "
        "static file were linked to SEC EDGAR filings and how three data-quality checks "
        "compare Lipper attributes to evidence extracted from regulatory sources. The "
        "Edgar-checks sheet is built only from the enriched fund table produced in the "
        "analysis notebook and from JSON caches written during that pipeline; the original "
        "Lipper Excel workbook is not embedded or copied.",
    ),
    (
        "Unit of observation",
        "Each row is one Lipper fund record (one ISIN). EDGAR filing facts are stored and "
        "fetched at the SEC series level (edgartools_series_id). Share-class identifiers "
        "(market ticker, class ID) are used to align a Lipper line with the correct series "
        "and, where applicable, with a specific share class in the prospectus fee table.",
    ),
    (
        "Linking Lipper to EDGAR",
        "ISINs are mapped to U.S. market tickers via the OpenFIGI API (cached in "
        "cache-isin-openfigi.json). Tickers are matched to the SEC investment-company "
        "reference table (get_fund_reference_data via edgartools, cached in "
        "cache-edgar-fund-data.json), yielding CIK, series ID, class ID, and registrant "
        "and series/class names. When the SEC row for a share class has a blank ticker, "
        "the Lipper name is used instead: the text before ';' must equal the SEC series "
        "name, and the text after ';' must equal the SEC class name (after dropping "
        "'Class'/'Shares' and expanding short hints such as InvP). A name match is kept "
        "only when it identifies exactly one series and one class. Only funds with a "
        "successful ticker or name match enter the EDGAR filing-facts and data-quality stages.",
    ),
    (
        "EDGAR access",
        "Requests to EDGAR use the edgartools library with SEC_USER_AGENT set per SEC "
        "fair-access policy. Filing metadata and parsed content are persisted locally to "
        "avoid repeated downloads and to keep notebook runs reproducible.",
    ),
    (
        "Source A — Form N-CEN (annual census)",
        "For each matched series, the latest available N-CEN filing is retrieved (up to "
        "40 filings scanned per series). From the census object and, where needed, the "
        "N-CEN primary_doc.xml for that accession, the pipeline stores in "
        "cache-edgar-filing-facts.json (keyed by series ID): filing accession number, "
        "filing date, form, report date, registrant name, registrant classification type "
        "(N-1A vs other), derived open-end flag (N-1A ⇒ open-end), series name and ID, "
        "series-level ETF flag (has_etf), ETF listing ticker and exchange when reported, "
        "fundTypes labels, indexFundInfo-derived is_index_fund, and management_style "
        "(Active / Passive) when parsed from the XML.",
    ),
    (
        "Source B — Prospectus filings",
        "For the same series, the latest matching prospectus is selected by scanning recent "
        "filings in order: 497K-family forms (via PROSPECTUS497K_FORMS), then 485BPOS, "
        "then 485APOS (up to 400 filings per form type). A filing is kept when its parsed "
        "series_id matches the fund series or when its ticker list contains the fund’s "
        "market ticker. Stored fields include: accession, filing date, form type, fund "
        "name, investment objective / strategy text, share-class fee rows (ticker, net "
        "expense ratio %), and benchmark_indices — labels taken from the prospectus "
        "performance table where the row name suggests an index or benchmark (including "
        "S&P-related wording).",
    ),
    (
        "Fields on the Edgar-checks sheet",
        "Identification columns combine Lipper ISIN/name, the resolved market ticker, SEC "
        "reference IDs (CIK, series, class), and N-CEN/prospectus metadata from the filing "
        "facts cache. Check columns repeat Lipper values, EDGAR-derived classifications, "
        "a discrete Result (Match / Mismatch / Not comparable), and a justification string "
        "copied from the data-quality cache (logic field), which states the exact rule "
        "that fired for that fund. Decision columns are pre-filled for manual review: "
        "Include fund defaults to TRUE when Lipper fund_type is non-blank; Final "
        "fund_wrapper and Final fund_type default to the Lipper values and may be edited "
        "in Excel to record the analyst’s retained classification after reviewing EDGAR checks.",
    ),
    (
        "Data-quality check 1 — fund_wrapper (mutual fund vs ETF)",
        "Objective: verify Lipper fund_wrapper against the legal/market wrapper implied by "
        "regulatory and market data.",
    ),
    (
        None,
        "Evidence hierarchy: (1) N-CEN — for open-end N-1A registrants, if the series "
        "reports an ETF and the N-CEN ETF ticker equals the fund’s market ticker, classify "
        "ETF; if an ETF exists on the series but tickers differ, classify mutual fund "
        "(share class of a series that also lists an ETF); if has_etf is false, classify "
        "mutual fund; non-open-end registrants are not assigned a wrapper. (2) If N-CEN "
        "does not classify, Yahoo Finance static metadata (quoteType, legal_type; "
        "cache-yahoo.json). (3) If still unknown, Financial Modeling Prep profile "
        "via FinanceDatabase (cache-financedatabase.json). Lipper values are normalised "
        "(“ETF” vs strings containing “mutual”). Comparison is exact equality on "
        "normalised labels; missing EDGAR-side classification ⇒ Result “Not comparable”. "
        "Proofs and comparisons are stored per ISIN in cache/dq-fund_wraper-edgar.json.",
    ),
    (
        "Data-quality check 2 — fund_type (Active vs Passive)",
        "Objective: verify Lipper fund_type (Active / Passive) against N-CEN fund style.",
    ),
    (
        None,
        "Only N-CEN is used (no Yahoo/FMP fallback). From fund_types on the cached N-CEN "
        "blob: if is_index_fund is true (Index Fund in fundTypes / indexFundInfo), classify "
        "Passive; else if management_style is Active, classify Active; else if "
        "management_style is Passive, classify Passive; otherwise classification is "
        "unknown. Lipper Active/Passive are normalised; Lipper “To Check” or other labels "
        "are not compared (Not comparable). Match is exact equality on Active vs Passive. "
        "Cache: cache/dq-fund_type-edgar.json.",
    ),
    (
        "Data-quality check 3 — S&P 500 benchmark",
        "Objective: compare Lipper benchmark naming and the Lipper is_S&P500 flag to "
        "whether EDGAR prospectus (and related) evidence supports a core S&P 500 benchmark, "
        "and whether total-return vs price variants align when both sides are explicit.",
    ),
    (
        None,
        "EDGAR side (strict order): (1) prospectus benchmark_indices — labels classified "
        "by regex: core S&P 500 wording required; Growth/Value/Equal Weight/sector "
        "variants excluded; variant sp500_total_return, sp500_price, or sp500_unspecified "
        "from label text. (2) If no table hit, investment objective text (≥120 characters) "
        "searched for core S&P 500 references. (3) Else fund/series name heuristics on "
        "prospectus fund name, N-CEN series name, or Lipper name. Lipper side: "
        "is_S&P500 flag and Benchmark Name parsed for S&P 500 and TR/price hints. "
        "Presence match: both reference core S&P 500, or neither does, with a special case "
        "when Lipper explicitly marks non-S&P 500 and EDGAR finds none. A missing series "
        "link or missing filing facts leaves the comparison unset (Not comparable), rather "
        "than counting as an EDGAR finding that the fund does not benchmark the S&P 500. "
        "Variant match is "
        "evaluated only when both sides reference S&P 500; total return and unspecified "
        "are treated as compatible. Cache: cache/dq-fund_benchmark-edgar.json.",
    ),
    (
        "Interpreting Result columns",
        "Match: normalised Lipper and EDGAR classifications agree under the rules above. "
        "Mismatch: both sides produced a comparable classification and they differ. "
        "Not comparable: missing EDGAR proof, missing Lipper label, or Lipper value outside "
        "the comparable set (e.g. fund_type “To Check”). Justification cells quote the "
        "rule-level explanation stored at evaluation time; they are the primary audit trail "
        "for the thesis.",
    ),
    (
        "Limitations",
        "EDGAR evidence reflects the latest cached N-CEN and prospectus filings at pipeline "
        "run time, not necessarily the Lipper snapshot date. Series-level N-CEN may not "
        "resolve ambiguous multi-class ETFs. Prospectus benchmark tables may omit indices "
        "present only in narrative sections (partially mitigated by objective/name "
        "fallbacks). External caches (Yahoo, FMP) introduce third-party coverage gaps. "
        "Disagreements should be read as hypotheses for manual review, not automatic "
        "corrections to Lipper.",
    ),
]

__all__ = ["METHODOLOGY_ROWS", "METHODOLOGY_SHEET_NAME"]
