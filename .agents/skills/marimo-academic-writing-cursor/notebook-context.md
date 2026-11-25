# Notebook context

## Research question
Master's thesis in Finance comparing passive and active US funds (mutual funds and ETFs) benchmarked against the S&P 500. Passive funds aim to track the benchmark with minimal tracking error; active funds aim to beat it. Performance is measured from daily total returns and regressed on the S&P 500 total return.

## Data and sources
- Primary: LSEG Datastream / Lipper daily panel, accessed via Université libre de Bruxelles (ULB). Input workbook `output-data/v2-funds-normalized.xlsx`, sheet `D-Timeseries final`.
- Secondary: Yahoo Finance (persistent level breaks; missing distributions for TR rebuilds) and FRED `DTB3` (US T-bill rate when Datastream is empty; frozen under `cache/fred-dtb3/`).
- Sample: ~292 funds (active / passive, mutual funds / ETFs), 2015-11-03 to 2026-11-03. After §8, identifiers whose Lipper benchmark is not S&P 500 TR (currently PHDG / `US46090A7054`, VEQTOR / Alternatives) are removed from the working panel and from `Funds final` in the cleaned workbook.

## Key definitions and symbols
- $r_{i,t}$: daily simple return of series $i$ on day $t$ (decimals).
- $m_t$: daily S&P 500 total return (`S&P 500 TR %`, Lipper `.SPXTR`) — market benchmark for quality control and regressions.
- Total return (TR): return with distributions reinvested. Price: return excluding distributions.

## Notebook structure
Data-quality pipeline in 11 steps, each with Documentation, Result and Decision:
1 Load & Yahoo replacement · 2 Holiday padding · 3 Gaps · 4 Scale shift (optional, off by default) · 5 Level jump · 6 Lipper 3Y/5Y/10Y consistency · 7 Spikes & distribution days · 8 Far from index (plus thesis sample drops) · 9 Frozen tails · 10 US T-bill fill · 11 Export (only disk write).
- Result = diagnostic only, never modifies data.
- Decision = curated, documented corrections actually applied (including sample drops in §8).

## Vocabulary
- Use: "series", "identifiers", "persistent level shift / break", "spike", "retained" / "rescaled" / "unadjusted".
- Avoid: "columns" (for series), "ids", "sticky", "for good".

## Conventions
- Benchmark: S&P 500 TR (`.SPXTR`) only; S&P 500 Composite series are reference only.
- Sections numbered §N.x per step; tables numbered Table N.x.
- Each step opens with "Sample at entry" and closes with "Sample at exit".
- Citation style: author–year. Language of the notebook text: English.

## Known pitfalls specific to this project
- yfinance `Close` with `auto_adjust=False` is split-adjusted, not unadjusted.
- Yahoo adjusted levels change with the download date: record the extraction date.
- Step 10 fills `US T-Bill 3M` from frozen FRED `DTB3` (H.15 bank discount rate, annualised %). Sharpe converts the month-end print as $(1+y_m/100)^{1/12}-1$. Alpha/beta OLS use total monthly returns (no rf subtraction).
- The Yahoo replacement overwrote the fund category of seven funds (shown as `Yahoo Price` / `Yahoo TR`); the category should stay the fund type, with the source in a separate field.
- Funds end on 2026-10-30 while the benchmark runs to 2026-11-03.
