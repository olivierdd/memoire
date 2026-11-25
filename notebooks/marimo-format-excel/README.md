# Format funds workbook (marimo)

`format-funds-excel.py` reads a cleaned pipeline export from `output-data/`, adds analysis tabs and formatting, and saves a sibling workbook (default `v2-funds-normalized-formatted.xlsx`). The input file is left unchanged.

Prerequisite: `output-data/v2-funds-normalized-cleaned.xlsx` (from `notebooks/marimo-series-check/load-series-v2.py`).

## Launch

From the repository root:

```bash
uv sync
uv run marimo edit notebooks/marimo-format-excel/format-funds-excel.py
```

Run as an app:

```bash
uv run marimo run notebooks/marimo-format-excel/format-funds-excel.py --headless
```

CLI (no UI):

```bash
uv run python helpers/format_excel/format_workbook.py \
  output-data/v2-funds-normalized-cleaned.xlsx \
  output-data/v2-funds-normalized-formatted.xlsx
```