# Load daily series (V2)

`load-series-v2.py` loads `output-data/v2-d-timeseries-final.xlsx`, lists every series, plots one series at a time, and checks the daily total-return columns. Opening the notebook leaves the corrected workbook in place. The button at the end writes `output-data/v2-d-timeseries-corrected.xlsx`.

## Launch

Run the commands from the repository root: the `code` directory that contains `pyproject.toml` and `helpers/`. The notebook looks upward from the working directory for `helpers/` and `output-data/`.

Install the project environment once:

```bash
uv sync
```

Open the notebook in the editor:

```bash
uv run marimo edit notebooks/marimo-series-check/load-series-v2.py
```

Open it as an app, without the editor:

```bash
uv run marimo run notebooks/marimo-series-check/load-series-v2.py
```

marimo prints a local URL and opens it in the browser.

## Before you open it

The daily sheet must already exist:

`output-data/v2-d-timeseries-final.xlsx`

That file is written by the last step of `notebooks/marimo-funds-check/load-funds-v2.py`. This notebook reads it and does not modify it. Use **Save the corrected workbook** when you want a new `output-data/v2-d-timeseries-corrected.xlsx`. If that file is already a valid workbook, the button label changes to **Write the corrected workbook again**.
