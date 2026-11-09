# Load and analyze funds (V2)

`load-funds-v2.py` loads the Funds sheet, then walks the selected funds through OpenFIGI, EDGAR, share-class selection, active/passive classification, and the daily series. The sheet loads on open. Each later step that calls an API or writes an Excel file waits for its button.

## Launch

Run the commands from the repository root: the `code` directory that contains `pyproject.toml` and `helpers/`. The notebook looks upward from the working directory for `helpers/`, the input workbook, and `.env`.

Install the project environment once:

```bash
uv sync
```

Open the notebook in the editor:

```bash
uv run marimo edit notebooks/marimo-funds-check/load-funds-v2.py
```

Open it as an app, without the editor:

```bash
uv run marimo run notebooks/marimo-funds-check/load-funds-v2.py
```

marimo prints a local URL and opens it in the browser.

## Before you open it

The Funds sheet must be at:

`input-data/CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx`

Put these variables in a `.env` file in the repository root. EDGAR loads that file when a step calls the SEC. TypeSafe reads its key from the environment.

- `SEC_USER_AGENT` — a contact string such as `Name (email@domain.com)`. EDGAR refuses requests without it when the ticker cache is missing or a filing is downloaded.
- `TYPESAFE_API_KEY` — used when the active/passive step asks Jev about a series that is not already in `cache/`.

OpenFIGI, EDGAR, and Jev answers already stored under `cache/` are reused. Buttons write workbooks under `output-data/`, including `v2-funds-final.xlsx` and `v2-d-timeseries-final.xlsx`.
