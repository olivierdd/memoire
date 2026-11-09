# Fund analysis notebooks

Marimo notebooks that load a fund workbook, match identifiers, check the daily series, and compare compounded daily returns with Lipper regressions.

Run every command from this directory, the one that contains `pyproject.toml` and `helpers/`.

## Setup

The project uses Python 3.13, recorded in `.python-version`. [uv](https://docs.astral.sh/uv/) installs that interpreter and the locked dependencies.

```bash
uv python install
uv sync
```

Create a `.env` file here before the funds notebook calls the SEC or classifies a series that is not already cached:

```bash
SEC_USER_AGENT=Name (email@domain.com)
TYPESAFE_API_KEY=
```

`SEC_USER_AGENT` is the contact string EDGAR requires. `TYPESAFE_API_KEY` is used when the active/passive step asks Jev about a series that is not already in `cache/`.

## Data that stays on your machine

`input-data/` and `output-data/` are not in the repository. `cache/` is: OpenFIGI, EDGAR, and Jev answers already stored there are reused.

Place the source workbook at:

`input-data/CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx`

The notebooks create `output-data/` when they write a workbook.

## Notebooks

Open a notebook in the editor with `uv run marimo edit`, or as an app with `uv run marimo run`. marimo prints a local URL and opens it in the browser.

Run them in this order. Each later notebook reads workbooks written by the one before it.

1. **Load and analyze funds.** `notebooks/marimo-funds-check/load-funds-v2.py` loads the Funds sheet, then walks the selected funds through OpenFIGI, EDGAR, share-class selection, active/passive classification, and the daily series. The sheet loads on open. Each later step waits for its button. It writes `output-data/v2-funds-final.xlsx` and `output-data/v2-d-timeseries-final.xlsx`. Details are in `notebooks/marimo-funds-check/README.md`.

2. **Check the daily series.** `notebooks/marimo-series-check/load-series-v2.py` reads `output-data/v2-d-timeseries-final.xlsx`, lists every series, plots one series at a time, and checks the daily total-return columns. Opening it leaves the source file unchanged. **Save the corrected workbook** writes `output-data/v2-d-timeseries-corrected.xlsx`. Details are in `notebooks/marimo-series-check/README.md`.

3. **Compare regressions with Lipper.** `notebooks/marimo-regressions/compare-lipper-regressions.py` compounds each fund’s daily total return to calendar months, regresses the fund on its Lipper benchmark over 3, 5, and 10 years, and compares alpha, beta, R², and tracking error with the Lipper columns. The comparison runs as soon as the notebook opens, and the first load can take a while. It needs these three files in `output-data/` and does not write a new workbook:

- `v2-funds-final.xlsx`
- `v2-d-timeseries-final.xlsx`
- `v2-d-timeseries-corrected.xlsx`

Details are in `notebooks/marimo-regressions/README.md`.

## Tests

```bash
uv run python -m unittest discover -s tests
```

## Layout

- `notebooks/` — the three marimo notebooks and their notes
- `helpers/` — fund and timeseries functions used by the notebooks
- `tests/` — tests for those functions
- `cache/` — saved API answers, included in the repository
- `input-data/` — the source workbook, not included
- `output-data/` — workbooks written by the notebooks, not included
