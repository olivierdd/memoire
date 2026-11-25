# Marimo regressions

## Daily consolidation regressions

`consolidate-daily-regressions.py` runs **daily** OLS of each fund on the benchmark over the Consolidation analysis window (default: 30 Sep 2016 – 30 Sep 2026), shows one row per fund, then **Consolidated statistics by group** (Active/Passive, MF/ETF). Same formulas as the Consolidation tab in the formatted reference workbook.

```bash
uv run marimo edit notebooks/marimo-regressions/consolidate-daily-regressions.py
uv run marimo run notebooks/marimo-regressions/consolidate-daily-regressions.py
```

Pick a workbook from `output-data/` (default `v2-funds-normalized-cleaned.xlsx`), adjust analysis-period overrides if needed, click **Run regressions**, then scroll the per-fund and consolidated tables.

## Daily regressions vs Lipper

`compare-lipper-regressions.py` compounds each fund’s daily total return to calendar months, regresses the fund on its Lipper benchmark over 3, 5, and 10 years, and compares alpha, beta, R², and tracking error with the Lipper columns on the funds sheet. The comparison runs as soon as the notebook opens.

## Launch

Run the commands from the repository root: the directory that contains `pyproject.toml` and `helpers/`. The notebook looks upward from the working directory for `helpers/` and `output-data/`.

Install the project environment once:

```bash
uv sync
```

Open the notebook in the editor:

```bash
uv run marimo edit notebooks/marimo-regressions/compare-lipper-regressions.py
```

Open it as an app, without the editor:

```bash
uv run marimo run notebooks/marimo-regressions/compare-lipper-regressions.py
```

marimo prints a local URL and opens it in the browser. The first load reads the cleaned workbook and fits the regressions, so the page stays busy until that cell finishes.

## Before you open it

This file must already exist:

`output-data/v2-funds-normalized-cleaned.xlsx`

Build it by:

1. Writing `output-data/v2-funds-normalized.xlsx` with step 8 of `notebooks/marimo-funds-check/load-funds-v2.py`
2. Running the gated pipeline in `notebooks/marimo-series-check/load-series-v2.py` through **step 11** (export writes the cleaned sibling; the input workbook is left unchanged)

The notebook reads `Funds final` and `D-Timeseries final` from the cleaned workbook and does not write a new file.

## Total return vs Lipper

Fund daily total return should match Lipper horizon **performance** when distributions are reinvested on the published NAV. Step **6** in `load-series-v2.py` rebuilds `TR %` from Datastream **price** plus Yahoo/FMP cash distributions, then keeps the series when the Lipper gate prefers the rebuild. Sharpe is still computed locally and may differ from Lipper’s definition.
