# Load daily series (V2)

`load-series-v2.py` loads sheet `D-Timeseries final` from
`output-data/v2-funds-normalized.xlsx`, checks and repairs daily total-return /
price series through a **gated step pipeline**, and writes the cleaned panel to a
**separate** workbook `output-data/v2-funds-normalized-cleaned.xlsx` (input left
unchanged).

**Step 1** loads on open. **Steps 2–11** wait for a **Run step** button: Result and
Decision stay empty until the button is pressed, and the next step stays disabled
until the previous step finishes. Each step has three collapsible panels
(Documentation, Result, Decision), collapsed by default.

Steps **2–8** blank exchange holidays, score gaps, and re-run consistency
flags on the evolving in-memory panel; **Decision** panels apply holiday NA and
level-break rescale, and distribution-day repairs where documented. **Excel write
happens only at step 11.** Earlier steps keep corrections in memory.

## Launch

Run commands from the repository root (the directory with `pyproject.toml` and
`helpers/`).

```bash
uv sync
```

Editor:

```bash
uv run marimo edit notebooks/marimo-series-check/load-series-v2.py
```

App (headless server; open the printed URL):

```bash
uv run marimo run notebooks/marimo-series-check/load-series-v2.py --headless
```

In the terminal, Command-click the local URL. When finished, press Ctrl-C to stop.

## Before you open it

The normalized workbook must already exist:

`output-data/v2-funds-normalized.xlsx`

That file is written by step 8 of `notebooks/marimo-funds-check/load-funds-v2.py`.
This notebook reads `D-Timeseries final` and, at **step 11**, writes the cleaned
panel to `output-data/v2-funds-normalized-cleaned.xlsx` without overwriting the
input.

## Pipeline steps

1. Load daily series (auto); replace Yahoo Price+TR for seven Lipper level-jump funds
2. Holiday calendar — NA on levels and % for exchange closures
3. Gap — score remaining calendar holes on the post-holiday panel; diagnostic Decision
4. Scale shift — optional (off by default at notebook top); when on, re-check; policy-only Decision
5. Level jump — re-check; Decision rescales level breaks (Yahoo-replaced ISINs skipped)
6. Consistency with Lipper 3-, 5- and 10-year total returns
7. Spike — re-check; Decision repairs distribution-day TR
8. Far from index — re-check; residual-risk Decision; drop non-`.SPXTR` sample (PHDG)
9. Blank frozen tails
10. Fill US T-Bill 3M (FRED `DTB3`)
11. Export cleaned workbook
12. Conclusion
