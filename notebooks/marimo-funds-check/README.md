# Load and analyze funds (V2)

`load-funds-v2.py` loads the Funds sheet, then walks the selected funds through OpenFIGI, EDGAR, share-class selection, active/passive classification, and the daily series. The sheet loads on open. Each later step that calls an API waits for its button. Intermediate steps keep workbook sheets in memory; `output-data/v2-funds-normalized.xlsx` is written once at the final step.

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
uv run marimo run notebooks/marimo-funds-check/load-funds-v2.py --headless
```

marimo prints a local URL. Open that link in the browser (Command-click it in the terminal).

## Extra steps for Alix

1. Make sure you have a **terminal** open at the bottom of VS Code / Cursor (not an Output window).
2. Start by pulling from origin (ask Claude Code, or run `git pull origin master` from the repository root).
3. Launch the marimo notebook with `--headless`:

```bash
uv run marimo run notebooks/marimo-funds-check/load-funds-v2.py --headless
```

4. In the terminal, **Command-click** the local URL that marimo prints to open it in the browser.
5. When you are done, go back to the terminal and press **Ctrl-C** to stop the notebook.

## Before you open it

The Funds sheet must be at:

`input-data/CLEAN_RECOLTE DONNEES-EXCEL-V2.xlsx`

Put these variables in a `.env` file in the repository root. EDGAR loads that file when a step calls the SEC. TypeSafe reads its key from the environment.

- `SEC_USER_AGENT` — a contact string such as `Name (email@domain.com)`. EDGAR refuses requests without it when the ticker cache is missing or a filing is downloaded.
- `TYPESAFE_API_KEY` — used when the active/passive step asks Jev about a series that is not already in `cache/`.

OpenFIGI, EDGAR, and Jev answers already stored under `cache/` are reused. Step 8 writes the accumulated sheets once to `output-data/v2-funds-normalized.xlsx` (including `Funds final` and `D-Timeseries final`).
