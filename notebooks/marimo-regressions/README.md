# Daily regressions vs Lipper

`compare-lipper-regressions.py` compounds each fund’s daily total return to calendar months, regresses the fund on its Lipper benchmark over 3, 5, and 10 years, and compares alpha, beta, R², and tracking error with the Lipper columns on the funds sheet. The comparison runs as soon as the notebook opens.

## Launch

Run the commands from the repository root: the `code` directory that contains `pyproject.toml` and `helpers/`. The notebook looks upward from the working directory for `helpers/` and `output-data/`.

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

marimo prints a local URL and opens it in the browser. The first load reads three workbooks and fits the regressions, so the page stays busy until that cell finishes.

## Before you open it

These three files must already be in `output-data/`:

- `v2-funds-final.xlsx` — written by `notebooks/marimo-funds-check/load-funds-v2.py`
- `v2-d-timeseries-final.xlsx` — written by the same notebook
- `v2-d-timeseries-corrected.xlsx` — written by the save button in `notebooks/marimo-series-check/load-series-v2.py`

The notebook reads those files and does not write a new workbook.
