# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo>=0.25.2",
#     "openpyxl>=3.1.5",
#     "pandas>=3.0.6",
# ]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="full", app_title="Format funds workbook")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
# Format funds workbook

Pick a cleaned pipeline workbook from `output-data/`, apply analysis formatting,
add **Config**, **Fund Analysis**, **Consolidation**, and **Funds by AUM** from the
reference template, then save a new file (the input is never overwritten).
""")
    return


@app.cell
def _(mo):
    get_export, set_export = mo.state(None)

    return get_export, set_export


@app.cell
def _(mo):
    import pathlib
    import sys
    import textwrap

    from openpyxl import load_workbook

    def md(text: str):
        return mo.md(textwrap.dedent(text).strip())

    start = pathlib.Path.cwd().resolve()
    repo_root = None
    for directory in [start, *start.parents]:
        if (directory / "helpers" / "format_excel").is_dir():
            repo_root = directory
            root = str(directory)
            if root not in sys.path:
                sys.path.insert(0, root)
            break
    if repo_root is None:
        raise FileNotFoundError("Could not find helpers/format_excel/")

    from helpers.format_excel.constants import (
        DEFAULT_INPUT_FILENAME,
        DEFAULT_OUTPUT_FILENAME,
    )
    from helpers.format_excel.format_workbook import format_workbook

    def output_workbook_choices(root: pathlib.Path) -> list[str]:
        folder = root / "output-data"
        if not folder.is_dir():
            return []
        return sorted(path.name for path in folder.glob("*.xlsx"))

    def workbook_sheet_summary(path: pathlib.Path) -> list[dict[str, object]]:
        workbook = load_workbook(path, read_only=True)
        try:
            return [
                {
                    "sheet": name,
                    "rows": workbook[name].max_row,
                    "columns": workbook[name].max_column,
                }
                for name in workbook.sheetnames
            ]
        finally:
            workbook.close()

    return (
        DEFAULT_INPUT_FILENAME,
        DEFAULT_OUTPUT_FILENAME,
        format_workbook,
        md,
        output_workbook_choices,
        repo_root,
        workbook_sheet_summary,
    )


@app.cell
def _(
    DEFAULT_INPUT_FILENAME,
    DEFAULT_OUTPUT_FILENAME,
    md,
    mo,
    output_workbook_choices,
    repo_root,
):
    choices = output_workbook_choices(repo_root)
    default_input = (
        DEFAULT_INPUT_FILENAME
        if DEFAULT_INPUT_FILENAME in choices
        else (choices[0] if choices else "")
    )
    input_dropdown = mo.ui.dropdown(
        options=choices,
        value=default_input,
        label="Input workbook (output-data/)",
    )
    output_name = mo.ui.text(
        value=DEFAULT_OUTPUT_FILENAME,
        label="Output filename",
        full_width=True,
    )
    run_format = mo.ui.run_button(
        label="Format and export",
        kind="success",
        disabled=not choices,
    )
    mo.vstack(
        [
            md(
                """
                Default input: `v2-funds-normalized-cleaned.xlsx` from the series-check
                notebook. Output is written alongside it in `output-data/`.
                """
            ),
            input_dropdown,
            output_name,
            run_format,
        ]
    )
    return input_dropdown, output_name, run_format


@app.cell
def _(
    format_workbook,
    get_export,
    input_dropdown,
    output_name,
    repo_root,
    run_format,
    set_export,
    workbook_sheet_summary,
):
    input_path = repo_root / "output-data" / input_dropdown.value
    output_path = repo_root / "output-data" / output_name.value.strip()
    preview_rows = workbook_sheet_summary(input_path)

    if run_format.value:
        if input_path.resolve() == output_path.resolve():
            set_export({"error": "Output filename must differ from the input file."})
        else:
            result = format_workbook(input_path, output_path)
            set_export(
                {
                    "result": result,
                    "output_path": str(result.output_path),
                    "visible": [
                        name
                        for name, state in result.sheet_states.items()
                        if state == "visible"
                    ],
                    "formula_updates": result.formula_cells_updated,
                    "select_outcome_col": result.select_outcome_col,
                    "dts_dims": f"{result.dts_last_row} × {result.dts_last_col}",
                }
            )
    return input_path, output_path, preview_rows


@app.cell
def _(export_payload, md, mo, preview_rows):
    parts = [
        mo.ui.table(
            preview_rows,
            label="Input workbook sheets",
            pagination=len(preview_rows) > 15,
            page_size=15,
        )
    ]
    if export_payload is None:
        parts.append(md("Press **Format and export** to build the analysis workbook."))
    elif export_payload.get("error"):
        parts.append(md(f"**Error:** {export_payload['error']}"))
    else:
        updates = export_payload["formula_updates"]
        parts.append(
            md(
                f"""
                **Saved:** `{export_payload['output_path']}`

                - Visible tabs: {", ".join(export_payload["visible"])}
                - `select.outcome` on Funds: **{export_payload["select_outcome_col"]}**
                - D-Timeseries final: {export_payload["dts_dims"]}
                - Formula cells retargeted: {sum(updates.values()):,}
                """
            )
        )
    mo.vstack(parts)
    return


@app.cell
def _(get_export):
    export_payload = get_export()
    return (export_payload,)


if __name__ == "__main__":
    app.run()