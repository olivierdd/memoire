# Data gathering pipeline — review notes

**Thesis context:** mutual fund and ETF total returns, classified into four groups (active mutual funds, passive mutual funds, active ETFs, passive ETFs).

**Source:** Datastream / Lipper workbook `input-data/CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx`.

**Working artefact:** `output-data/v2-funds-normalized.xlsx` (single workbook enriched by all three notebooks).

**How this note was produced:** `load-funds-v2.py` was reviewed against its completed workbook state (re-opening that notebook rewrites the Funds sheet and would destroy later cleaning). `load-series-v2.py` was run live on port 2720 (including the distribution-rebuild button). Lipper regression metrics were computed with the same helpers as `compare-lipper-regressions.py`.

---

## Pipeline overview

```
CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx
        │
        ▼
load-funds-v2.py
  select → OpenFIGI → EDGAR → primary share class
  → active/passive (N-CEN / Jev) → match daily TR → Funds final
  → filter D-Timeseries final
        │
        ▼
load-series-v2.py
  QA → holidays → split/level fixes → Lipper 3Y/5Y/10Y consistency
  → distribution-day repairs → blank frozen tails → ^IRX
  → drop 4 closed funds → rewrite D-Timeseries final
        │
        ▼
compare-lipper-regressions.py
  monthly compound → OLS vs Lipper benchmark (3y / 5y / 10y)
  → total return, alpha, beta, R², TE, Sharpe checks
```

---

## Notebook 1 — `load-funds-v2.py`

### Purpose

Build a cleaned fund cross-section, enrich identifiers, classify management style, keep one share class per series, and retain only funds with a usable daily total-return series.

### Selection funnel (from completed workbook)

| Stage | Count | Rule / output |
|------:|------:|---------------|
| All rows on Funds sheet | 2,610 | Full Lipper/Datastream extract |
| Selected funds | 605 | Non-empty `fund_type` (asset class: Equity 554, Alternatives 46, Mixed Assets 4, Bond 1) |
| OpenFIGI ISIN found | 598 / 605 | 7 unmatched → sheet `No matching OPENFIGI` |
| After primary share-class filter | 314 kept | 292 secondary classes dropped from shared series |
| With daily total return | 307 | 7 without series → `No daily total return` |
| Final sample after series notebook drops | **303** | 4 closed funds marked Drop later |

Instrument mix in **Funds final (303):** Open-End Fund 232, ETF 68, Equity ETF 3.  
Wrapper field: mutual fund 232, ETF 71.

### Steps, changes, and reasoning

#### 1. Load and normalize

- Read the **Funds** sheet; normalize column names to snake_case with prefix `ds.`.
- Write sheet `Funds` of `v2-funds-normalized.xlsx`.
- **Decision:** selection = rows with a non-empty asset-class `fund_type` (not the Active/Passive label).

#### 2. Identifier QA (ISIN / CUSIP)

- Flag duplicate and missing ISINs/CUSIPs among selected funds.
- **Enrichment:** for missing CUSIP + US ISIN, derive the 9-character CUSIP from the ISIN and confirm with OpenFIGI (`ID_CUSIP` vs `ID_ISIN`). Fill only when both lookups return the same listing.
- Work is done on `selected_funds_modified`; the original selection is left unchanged.

#### 3. OpenFIGI enrichment

- Lookup each ISIN (`ID_ISIN`); also check CUSIP consistency.
- Adds `openfigi_market_id`, `openfigi_name`, `isin_found`, `name_matches`, `cusip_matches` (exported as `openfigi.*`).
- Name matching allows OpenFIGI short forms (`LRG`, `INST`, …); a different economic word (e.g. Core vs Growth) does **not** match.
- Unmatched funds cannot get a market ticker and therefore cannot join EDGAR via ticker.

#### 4. EDGAR enrichment (+ manual corrections)

- Resolve OpenFIGI ticker → SEC fund reference → CIK / series / class.
- Adds `edgar_*` / `edgartools_*` fields.
- **Decision — keep all unmatched cases in the sample**, with three documented correction buckets:
  1. **Match by name** — ticker cell blank in SEC file; match sheet name to series + class (special cases: Invesco Main Street All Cap Y vs OpenFIGI A; HAWG ticker collision).
  2. **Closed** — series left the current SEC file after merger/liquidation; keep for survivorship-aware history; identifiers stay empty.
  3. **Cannot match** — UITs (e.g. SPY, Voya Corporate Leaders Trust) have no open-end series/class row; stay without N-CEN classification.

Completed workbook still lists **9** rows on `No matching EDGAR` / `No EDGAR share class` (includes closed Fifth Third funds, FMALX, SPY, Voya UIT, etc.).

#### 5. Same series / N-PORT / primary share class

- Detect multiple selected classes sharing CIK + series; confirm classes on latest N-PORT (`nport_same_series`).
- **Primary class rule (first that decides):**
  1. Largest AUM (blank AUM ignored, not zero).
  2. Else EDGAR class-name preference order (series name / non-Advisor → Investor/Ordinary → Gabelli AAA → Class A non-529 → Admiral → Institutional/I → Y → other).
  3. Else smallest `edgartools_class_id`.
- **Decision:** one portfolio → one row. Dropped classes written to `Dropped share classes` (292 rows).

#### 6. Active vs passive classification (`fund_management_style`)

First source that decides wins:

1. **Latest N-CEN** for the series  
   - `indexFundInfo` = Index Fund → **Passive**  
   - Target Date / Fund of Funds / Interval (no indexFundInfo) → **Other**  
   - Other types including ETF wrapper without indexFundInfo → **Active**  
   - N/A or series absent → next source  
2. **Jev** on prospectus text (497K objective, else 485BPOS/APOS sections)  
   - Passive = mandate to track/match/approximate an index  
   - Active = manager selects securities (benchmark named only for comparison ≠ passive)  
   - Confidence **&lt; 0.60** → **Unknown**  
3. No CIK/series or no prospectus text → **Unknown**

Explicitly **unused:** edgartools’ single `fundType` tag (drops `indexFundInfo`), portfolio turnover, and the word “Index” in the fund name.

**On Funds final (303):**

| Style | Count | Main source |
|-------|------:|-------------|
| Active | 194 | Jev 166, N-CEN 28 |
| Passive | 27 | N-CEN Index Fund 24; Jev 3 |
| Other | 15 | N-CEN Fund of Funds 6; Jev Other 9 |
| Unknown | 67 | No series/prospectus 53; low Jev confidence ≈14 |

Sheet `Fund type mismatch`: **91** rows where Lipper/sheet Active–Passive label ≠ classified style (mostly sheet Active vs classified Unknown/Other).

#### 7–8. Daily total-return match and keep/drop

- Match Datastream `D-Timeseries` columns on ISIN; confirm name via sheet → OpenFIGI → EDGAR.
- **Keep** if a daily TR series exists (even if the name check fails — those go to `No matching D-TIMESERIES NAME`, 8 funds).
- **Drop** if no daily TR (7 funds).
- Column `timeseries.keep_or_drop` recorded on Funds.

#### 9–10. Final fund set and filtered timeseries

- Write `Funds final` (column order: identifiers → OpenFIGI → sheet fields → timeseries flags → style → EDGAR).
- Filter raw `D-Timeseries` to remaining ISINs + index + risk-free rate → sheet `D-Timeseries final` (label rows preserved).

### Decisions (notebook 1)

1. Select on asset-class `fund_type`, not on Active/Passive.
2. Trust OpenFIGI confirmation before filling CUSIPs.
3. Keep closed / UIT / unmatchable EDGAR cases in the selected set.
4. Collapse to one primary share class per series (AUM, then name hierarchy).
5. Prefer N-CEN `indexFundInfo`, then Jev; ignore turnover and name heuristics.
6. Keep funds with a TR series even when the Datastream name is imperfect.

### Open questions (notebook 1)

1. **Four-way thesis taxonomy is not yet closed.** Datastream categories on the timeseries sheet are not the same as N-CEN/Jev style:
   - Timeseries labels (TR % columns): Active MF 200, Active ETF 68, Passive MF 30, Passive ETF 3, To Check MF 6.
   - Robust style × wrapper on Funds final: Active MF 149, Active ETF 45, Passive MF 25, Passive ETF 2, plus **Unknown** (MF 48 / ETF 19) and **Other** (MF 10 / ETF 5).
2. **Three funds labelled Active MF on the timeseries are Passive under N-CEN/Jev:** Cyber Hornet S&P 500, Transamerica Large Core ESG;A, Green Century Equity (Individual Investor). Which label is authoritative for the thesis tables?
3. **67 Unknown + 15 Other** — exclude, hand-label, or keep as a fifth/sixth group?
4. **Mismatch sheet (91)** — reconcile Lipper Active/Passive / `alix_fund_type` with `fund_management_style` before publishing classification counts.
5. **Benchmark coverage:** 247 funds on `.SPXTR`, 24 on `.INX`, 27 with no ticker, and a few other indices — regressions only map `.SPXTR` and `.INX`.
6. Name-gap TR matches (8 funds) — spot-check that the ISIN join did not attach the wrong series.

---

## Notebook 2 — `load-series-v2.py`

### Purpose

Audit and repair daily total-return / price series so they are usable for performance and S&P 500 regressions; align cumulative returns with Lipper when a distribution rebuild helps.

### Input snapshot (live run)

- File: `output-data/v2-funds-normalized.xlsx`, sheet `D-Timeseries final`
- **2,871** dates (2015-11-03 → 2026-11-03), **1,542** series columns, **314** ids
- Categories (ids): Active MF 200, Active ETF 68, Passive MF 30, To Check MF 6, Passive ETF 3, Index 6, risk-free 1

### Steps, changes, and reasoning

#### 4. Consistency checks (vs daily S&P 500 TR %)

Thresholds: spike ≥10%, reversal band 15%, scale factor 5× over 12 days, level jump ≥50%, far from index ≥5%, date gap &gt;45 days.

**Post-cleaning live results:** 307 TR series checked; **40** flagged; **0** gaps; **6** spikes; **1** residual level-jump flag; **3** scale shifts; **39** with ≥1 day far from index (**30** only for that reason; **21** with a single such day).

#### 5. Market holidays

- Holiday = S&P 500 TR level unchanged vs prior close.
- Carry fund level forward, set return to 0, recompute next session.
- Live re-run: **105** holidays detected; **0** corrections left (already applied).

#### 6. Rescale level breaks (corporate actions)

Hand-coded rules for double-scaled splits, reverse splits, master-portfolio rebases, TR-only rebases; leave pure distribution NAV drops untouched.

Live re-run: **3** breaks still detected across 10 funds; **0** new rescales; **14** series already on corrected scale; **2** price series kept as distributions.

#### 6b. Rebuild TR from distributions (button — pressed)

- Rebuild daily TR% from price + cash distributions (Yahoo, else FMP); align ex-dates within 4 sessions.
- Index-like funds without distributions: December-miss heuristic (set that day’s TR to S&P).
- **Lipper gate (as of 2026-09-30):** adopt rebuild if \|10y gap\| ≤ 0.5 pp, or 10y improves, or 10y unchanged and 5y improves.

**Live result after pressing the button:** **307** evaluated → **186 adopted**, **121 kept** Datastream TR.

#### 7. Hand repairs of distribution-day TR

- Forward-rescale TR so the bad day equals S&P TR (listed Goldman / Natixis / SEI / Schwab / etc. dates), or one-day American Growth fix.
- Leave spikes where price and TR agree (true NAV moves).

**Live:** **10** distribution days repaired on **6** series (**14,946** cells); **7** spikes left unchanged.

#### 8. Blank frozen tails

- Flat TR **and** price for ≥5 sessions while the S&P moves → blank after last real print (avoids fake 0% returns).
- Live re-run: **0** left to blank (already cleaned). Noted freeze: Sequoia / related ISINs in Oct 2026.

#### 9. Risk-free rate

- Fill empty Datastream `US T-Bill 3M` from frozen FRED `DTB3` (annualised bank discount %).
- Freeze: `cache/fred-dtb3/DTB3.csv` (download date in `manifest.json`).

#### 10. Drop four closed funds (auto-write)

| ISIN | Fund | Reason |
|------|------|--------|
| US31678R6760 | Fifth Third Equity Index;A | Liquidated 27 Jul 2012; flat print in sample |
| US31678R6273 | Fifth Third Structured Large Cap Plus;A | Same; Datastream name stale |
| US3167865654 | Fifth Third Dividend Growth;A | Same liquidation |
| US31617F8178 | Fidelity Advisor Series G&I (FMALX) | Reorg Sep 2018 into US31617F8335 (kept) |

Blank all their series columns; set `timeseries.keep_or_drop = Drop`; remove from `Funds with daily TR` and `Funds final`. Live re-run was idempotent (already dropped).

#### 11. Persist

- Button **Replace the sheet again** rewrites `D-Timeseries final` (idempotent if already repaired). Removes `D-Timeseries raw` if present.

### Decisions (notebook 2)

1. Prefer **total return** for the study; price remains the published NAV (drops on distributions).
2. Adopt rebuilt TR only when it moves closer to Lipper (10y-first gate).
3. Treat unexplained distribution-day TR errors by setting that day to S&P (claimed negligible over ~2,800 days).
4. Remove four non-usable closed/reorganized series rather than treating a constant print as a freeze cut.
5. Keep Principal Value ETF usable from **2019** (flat NAV earlier); Johnson Enhanced Return goes to cash before Nov 2026 liquidation.

### Open questions (notebook 2)

1. **Residual flags after cleaning** — still ~40 series with “far from index” / a few spikes/scale flags. Confirm they are genuine active risk, not data errors.
2. **3 level breaks still detected** — need corporate-action rules or accept as-is?
3. **To Check MF (6 ids)** still appear as columns (including the four dropped funds’ blanked series, plus US8603241022 and US3608755795). Remove blanked columns entirely?
4. Rebuild adopt/keep decisions (186 / 121) — spot-check large Lipper gaps that stayed on Datastream TR.
5. Unverified distribution dollar amounts (Goldman, Natixis, SEI, Schwab) — acceptable for thesis robustness, or replace with exact payouts?

---

## Notebook 3 — `compare-lipper-regressions.py`

### Purpose

Validate cleaned daily TR by compounding to calendar months, regressing on the Lipper reference benchmark, and comparing alpha, beta, R², tracking error, total return, and Sharpe with Lipper’s precomputed columns.

### Method (as coded)

- Daily `… TR %` only; month return = product within calendar month.
- Windows end **30 Sep 2026** (Lipper “last month end”).
- Horizons: 3y = 36, 5y = 60, 10y = 120 months.
- Benchmark map: `.SPXTR` → `S&P 500 TR %`; `.INX` → `S&P 500 C Price %`.
- OLS of fund month return on benchmark (no risk-free subtraction for α/β).
- Sharpe: annualized mean/std of monthly returns; excess over 3M T-bill when enough months present.
- **Regression “match”** if Lipper β present and \|Δα\| ≤ 0.05 pp/mo, \|Δβ\| ≤ 0.05, \|ΔR²\| ≤ 0.05, \|ΔTE\| ≤ 0.5 pp.
- **Total return “close”:** \|Δ\| ≤ **1.0** pp vs Lipper `{N} Year Performance`.
- **Alpha “close”:** \|Δα\| ≤ **0.05** pp/month.

### Quantitative results (cleaned sheet)

| Check | Result |
|-------|--------|
| Fund × horizon rows | 909 (303 × 3) |
| Status OK | 813; **benchmark_not_on_sheet** 96 (non-`.SPXTR`/`.INX` or missing ticker) |
| Lipper match rate 3y / 5y / 10y | **53.4%** / **45.7%** / **56.9%** (among horizons with Lipper β) |
| Funds matching **all** horizons | **7 / 235** |
| TR within 1 pp (3y / 5y / 10y) | **94.8%** / **95.1%** / **93.8%** |
| Median \|TR gap\| (pp) | 0.004 / 0.004 / 0.013 |
| Alpha within 0.05 pp/mo | **62.9%** / **54.7%** / **60.7%** |

Largest 10y TR gap: **John Hancock US Sector Rotation;NAV (−30.5 pp)**. Other notables: AB Select US Equity (+4.3), Nationwide BNY Mellon Dynamic Core (+3.4), SPDR Portfolio S&P 500 (−3.2), plus smaller index-ETF residuals (IVV, SPY family).

Largest 3y α gaps often coincide with large β gaps (e.g. Catalyst Insider Buying, Janus Henderson Contrarian, PRIMECAP Odyssey Aggressive Growth) — consistent with the notebook’s reading that Lipper risk stats sometimes disagree with an S&P TR OLS even when cumulative performance matches.

### Decisions (notebook 3)

1. Treat **total return alignment with Lipper** as the primary series-quality gate (~94–95% within 1 pp).
2. Treat **α/β/R²/TE match** as secondary; when Lipper diverges sharply, prefer local OLS (and Yahoo risk stats as a cross-check).
3. Do not require risk-free subtraction for the Lipper α comparison (matches Lipper’s reported α definition in this pipeline).

### Open questions (notebook 3)

1. Why do so few funds match Lipper on **all** of α/β/R²/TE while TR matches so well? Document as a known Lipper vs local OLS discrepancy, or change the benchmark / estimation details?
2. **96** fund-horizons with unmapped benchmarks — drop from regression sample, or extend the benchmark map?
3. Outliers with large TR gaps after rebuild (esp. John Hancock Sector Rotation) — exclude, investigate distributions, or keep with a footnote?
4. Sharpe vs Lipper Sharpe — definitions may differ; do not treat as a hard validation metric without alignment.
5. Confirm index TR vs Lipper “implied index” (performance − relative performance) still matches within 0.01 pp after the latest rebuild.

---

## Cross-cutting status for the thesis

### What is solid

- Identifier enrichment (OpenFIGI + EDGAR) with documented exceptions.
- One primary share class per series.
- Daily TR coverage for 303 funds after dropping unusable closed series.
- Series cleaning: holidays, splits/rebases, distribution rebuild (186 adopted), frozen tails, ^IRX.
- Cumulative returns closely match Lipper for the large majority of funds.

### What still blocks a clean 4-category design

| Issue | Why it matters |
|-------|----------------|
| 67 Unknown + 15 Other | Cannot assign Active/Passive without a further rule |
| Datastream category ≠ N-CEN/Jev style | Three “Active MF” timeseries labels are Passive under the robust classifier |
| Passive ETF cell is tiny (2–3 funds) | Statistical power for that arm is weak |
| `To Check MF` leftovers | Classification and column hygiene unfinished |
| Lipper Active/Passive / `alix_fund_type` disagree with `fund_management_style` | Need an authoritative definition for the thesis tables |

### Suggested validation checklist

1. Decide authoritative Active/Passive source (recommend: N-CEN → Jev; override Datastream category when they conflict).
2. Hand-review Unknowns with usable prospectuses; set a rule for permanent Unknowns (exclude vs “unclassified” appendix).
3. Decide fate of Other (FoF / target-date / interval): exclude from the four arms or analyse separately.
4. Reconcile the three Active-labelled / Passive-classified funds in writing.
5. Investigate John Hancock Sector Rotation 10y TR gap and remaining level-break flags.
6. Fix or document non-`.SPXTR`/`.INX` benchmarks before quoting regression match rates as sample-wide.
7. Freeze `v2-funds-normalized.xlsx` (and optionally the formatted v3 workbook) once classification rules are signed off — avoid re-running `load-funds-v2` without a backup (step 1 overwrites the workbook).

---

## Artefacts and sheets

| Path / sheet | Role |
|--------------|------|
| `input-data/CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx` | Raw Datastream/Lipper extract |
| `output-data/v2-funds-normalized.xlsx` → `Funds` | Full enriched cross-section |
| → `Funds final` | Analysis sample (303) |
| → `D-Timeseries final` | Cleaned daily panel |
| → `Dropped share classes`, `Fund type mismatch`, `No matching *` | Audit trails |
| `output-data/v2-funds-normalized.backup-before-rerun.xlsx` | Safety copy taken before this review |
| `cache/cache-*-openfigi*.json`, `cache-edgar-*.json`, `cache-fund-management-style.json`, `yahoo-distributions.json`, `yahoo-risk-stats.json` | API / classifier caches |

---

*Generated during interactive review of the three marimo notebooks (Nov 2026).*
