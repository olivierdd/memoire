"""Fetch US S&P 500 ETFs from Trackinsight into the vehicle template.

The screen keeps listed passive funds on the plain S&P 500 Index, plus listed
active funds whose objective mentions the S&P 500, then US, non-UCITS, USD,
unhedged, capitalizing or distributing share classes.

Rows are written onto a copy of 97-template/sp500-vehicles.template.xlsx.
Instructions on that workbook decide which column receives each value.
"""

from __future__ import annotations

import math
import re
import shutil
from copy import copy
from datetime import date, datetime
from pathlib import Path

import polars as pl
from openpyxl import load_workbook
from openpyxl.styles import Protection
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.cell_range import CellRange

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT.parent / "97-template" / "sp500-vehicles.template.xlsx"
OUTPUT = ROOT / "output-data" / "sp500-vehicles.xlsx"
CCY = "usd"
FIRST_DATA_ROW = 4
LAST_FORMATTED_ROW = 63

ACTIVE_OBJECTIVE = (
    r"(?i)(benchmark|outperform|relative to).{0,80}s&p\s*500"
    r"|s&p\s*500.{0,40}(benchmark|total return|net return|index)"
)
_NAME_SUFFIX = re.compile(r"\s+-\s+[A-Z]{3}$")

# Lists sheet columns whose dropdowns this extract may extend (Instructions R14).
_LIST_COLUMNS = {
    "trackinsight_replication": "AB",
    "trackinsight_currency": "AF",
    "currency_master": "AF",
}
# R08. These facts have no Trackinsight column yet. Insert one after the last source column.
_SOURCE_COLUMNS = (
    ("fmp_symbol", "trackinsight_ticker", "Ticker on Trackinsight."),
    ("name_lipper", "trackinsight_name", "Fund name on Trackinsight."),
    ("instrument_type", "trackinsight_vehicle", "Vehicle from Trackinsight. This extract stores etf."),
)
_MASTER_LISTS = (
    ("Master: Research, FMP", "Trackinsight"),
    ("Master: Research, Lipper", "Trackinsight"),
)
# Master-source cell, then the Trackinsight column that supplies it (R13).
# The master cell itself stays a formula (R04, R09).
_MASTER_SOURCES = (
    ("ticker_master_source", "trackinsight_ticker"),
    ("name_master_source", "trackinsight_name"),
    ("vehicle_master_source", "trackinsight_vehicle"),
    ("benchmark_master_source", "trackinsight_benchmark"),
    ("isin_master_source", "trackinsight_isin"),
    ("provider_master_source", "trackinsight_provider"),
    ("currency_master_source", "trackinsight_currency"),
    ("exchange_master_source", "trackinsight_exchange"),
    ("assets_master_source", "trackinsight_net_assets"),
    ("inception_master_source", "trackinsight_inception"),
    ("description_master_source", "trackinsight_description"),
    ("expense_ratio_master_source", "trackinsight_expense_ratio"),
    ("yield_master_source", "trackinsight_yield"),
    ("ytd_return_master_source", "trackinsight_ytd_return"),
    ("trailing_3m_master_source", "trackinsight_trailing_3m_return"),
)
# R08. Rebuild these formulas so the new Trackinsight column is one of the choices.
_IDENTITY_FORMULAS = {
    "ticker_master": (
        "ticker_master_source",
        (("Research", "ticker", False), ("FMP", "fmp_symbol", False), ("Trackinsight", "trackinsight_ticker", False)),
    ),
    "name_master": (
        "name_master_source",
        (("Research", "fund_name", False), ("Lipper", "name_lipper", False), ("Trackinsight", "trackinsight_name", False)),
    ),
    "vehicle_master": (
        "vehicle_master_source",
        (("Research", "wrapper", False), ("Lipper", "instrument_type", True), ("Trackinsight", "trackinsight_vehicle", False)),
    ),
}


def select_sp500(shares: pl.DataFrame) -> pl.DataFrame:
    """Listed US USD unhedged share classes tied to the S&P 500 screen."""
    shares = shares.with_columns(
        [
            pl.col(column).cast(pl.List(pl.Utf8), strict=False)
            for column in ("class_leverage", "class_inverse_leverage", "class_strategy")
        ]
    )
    not_levered = (
        _list_empty("class_leverage")
        & _list_empty("class_inverse_leverage")
        & _list_excludes("class_strategy", "Leveraged")
        & _list_excludes("class_strategy", "Inverse")
    )
    passive = shares.filter(
        (~pl.col("actively_managed"))
        & pl.col("listed")
        & (pl.col("generic_index") == "S&P 500 Index")
        & not_levered
    ).with_columns(pl.lit("passive").alias("mgmt_style"))
    active = shares.filter(
        pl.col("actively_managed")
        & pl.col("listed")
        & pl.col("investment_objective").str.contains(ACTIVE_OBJECTIVE)
    ).with_columns(pl.lit("active").alias("mgmt_style"))
    chosen = pl.concat([passive, active], how="diagonal_relaxed")
    return (
        chosen.filter(
            (pl.col("jurisdiction") == "United States")
            & (~pl.col("ucits"))
            & (pl.col("currency") == "USD")
            & (~pl.col("currency_hedged"))
            & pl.col("dividend_policy").is_in(["Capitalization", "Distribution"])
        )
        .with_columns(
            pl.when(pl.col("mgmt_style") == "passive").then(0).otherwise(1).alias("_order")
        )
        .sort(["_order", "share_label"])
        .drop("_order")
    )


def build_fund_rows(selected, reports) -> list[dict]:
    """One template row per share class, with masters chosen by Instructions R13."""
    by_id = {}
    for report in _records(reports):
        by_id.setdefault(int(report["share_id"]), report)
    used: dict[str, int] = {}
    rows = []
    for share in _records(selected):
        share_id = int(share["share_id"])
        ticker = _unique_ticker(share.get("main_ticker"), share_id, used)
        rows.append(_fund_row(share, by_id.get(share_id, {}), ticker))
    _assign_primary(rows)
    return rows


def write_workbook(path: Path, rows: list[dict], template: Path = TEMPLATE) -> None:
    """Copy the template and write Funds from row 4. Instructions and Guide stay as they are."""
    if not template.exists():
        raise FileNotFoundError(template)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(template, path)
    book = load_workbook(path)
    funds = book["Funds"]
    funds.protection.sheet = False
    _add_source_columns(book)
    _extend_identity_formulas(funds)
    columns = _field_columns(funds)
    _make_room(funds, len(rows))
    _append_codes(book, rows)
    for offset, row in enumerate(rows):
        excel_row = FIRST_DATA_ROW + offset
        for key, value in row.items():
            if _blank(value):
                continue
            column = columns.get(key)
            if column is None:
                # DB-only enrichments (e.g. trackinsight_mgmt_style) are kept on
                # the row dict for ingest but are not Excel template fields.
                continue
            funds.cell(excel_row, column).value = value
    funds.protection.sheet = True
    book.save(path)


def _configure_env() -> None:
    """Load repo ``.env`` and default the Trackinsight cache directory."""
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT.parent / ".env", override=True)
    os.environ.setdefault("TRACK_API_STORAGE", str(ROOT / ".cache"))


def fetch():
    """Download the screened share classes and their latest USD reports."""
    import trackinsight_data_python as api

    _configure_env()
    shares = api.getShares()
    if shares is None or shares.height == 0:
        raise RuntimeError("Trackinsight returned no shares")
    selected = select_sp500(shares)
    if selected.height == 0:
        raise RuntimeError("No ETFs matched the S&P 500 screen")
    ids = [int(value) for value in selected["share_id"].to_list()]
    print(f"fetching reports for {len(ids)} share classes", flush=True)
    reports = api.getReports(ccy=CCY, ids=ids)
    return selected, reports


def main() -> None:
    print("loading Trackinsight shares", flush=True)
    selected, reports = fetch()
    rows = build_fund_rows(selected, reports)
    write_workbook(OUTPUT, rows)
    print(f"wrote {OUTPUT} ({len(rows)} funds)", flush=True)


def _fund_row(share: dict, report: dict, ticker: str) -> dict:
    label = _first(report, "fund_label") or share.get("share_label") or ""
    name = _NAME_SUFFIX.sub("", str(label)).strip() or ticker
    objective = _first(report, "investment_objective") or share.get("investment_objective")
    row = {
        "in_trackinsight": 1,
        "trackinsight_ticker": ticker,
        "trackinsight_name": name,
        "trackinsight_vehicle": "etf",
        "trackinsight_share_id": int(share["share_id"]),
    }
    # Screen already tags mgmt_style; persist it so DB / UI can tell active ETFs apart.
    mgmt = share.get("mgmt_style")
    if mgmt in {"active", "passive"}:
        row["trackinsight_mgmt_style"] = mgmt
    if share.get("actively_managed") is not None:
        row["trackinsight_actively_managed"] = (
            "Y" if bool(share.get("actively_managed")) else "N"
        )
    _put(row, "trackinsight_description", objective)
    _put(row, "trackinsight_isin", report.get("isin"))
    if share.get("fund_id") is not None:
        row["trackinsight_fund_id"] = int(share["fund_id"])
    _put(row, "trackinsight_provider", _first(report, "provider") or share.get("provider"))
    _put(row, "trackinsight_currency", _first(report, "currency") or share.get("currency"))
    _put(row, "trackinsight_exchange", report.get("listing_place"))
    _put(row, "trackinsight_benchmark", _first(report, "benchmark") or share.get("benchmark"))
    _put(row, "trackinsight_generic_index", _first(report, "generic_index") or share.get("generic_index"))
    _put(row, "trackinsight_replication", report.get("replication_model"))
    _put(row, "trackinsight_net_assets", _num(_first(report, "1d_last_usd_aum", "ytd_last_usd_aum")))
    _put(row, "trackinsight_expense_ratio", _num(_first(report, "expense_ratio") or share.get("expense_ratio")))
    _put(row, "trackinsight_inception", _as_date(report.get("inception_date")))
    _put(row, "trackinsight_yield", _num(_first(report, "1ytd_dividend_yield", "ytd_dividend_yield")))
    _put(row, "trackinsight_ytd_return", _num(report.get("ytd_net_return")))
    _put(row, "trackinsight_trailing_3m_return", _num(report.get("3mtd_net_return")))
    _put(row, "trackinsight_3y_annualized_return", _num(report.get("3y_annualized_net_return")))
    _put(row, "trackinsight_ytd_excess_return", _num(report.get("ytd_net_excess_return")))
    _put(row, "trackinsight_tracking_error_1y", _num(report.get("1ytd_annualized_net_tracking_error")))
    _apply_masters(row)
    return {key: value for key, value in row.items() if not _blank(value)}


def _apply_masters(row: dict) -> None:
    """R13. Set the master-source role. The master cell is a formula and is not written."""
    for source, origin in _MASTER_SOURCES:
        if not _blank(row.get(origin)):
            row[source] = "Trackinsight"


def _assign_primary(rows: list[dict]) -> None:
    """R07. One primary share class in each series."""
    groups: dict[tuple, list[int]] = {}
    for index, row in enumerate(rows):
        edgar = row.get("edgar_series_id")
        name = row.get("name_master") or row.get("trackinsight_name")
        vehicle = row.get("vehicle_master") or row.get("trackinsight_vehicle")
        if not _blank(edgar):
            key = ("edgar", edgar)
        elif _blank(name) and _blank(vehicle):
            key = ("row", index)
        else:
            key = ("name", name, vehicle)
        groups.setdefault(key, []).append(index)
    for indexes in groups.values():
        chosen = _primary_index(rows, indexes)
        for index in indexes:
            rows[index]["primary_share_class"] = 1 if index == chosen else 0


def _primary_index(rows: list[dict], indexes: list[int]) -> int:
    active = [index for index in indexes if _is_active(rows[index])]
    pool = active or indexes

    def sort_key(index: int):
        row = rows[index]
        if not _blank(row.get("expense_ratio_master")):
            return (0, float(row["expense_ratio_master"]), index)
        if not _blank(row.get("expense_ratio_lipper")):
            return (1, float(row["expense_ratio_lipper"]), index)
        if not _blank(row.get("trackinsight_expense_ratio")):
            return (2, float(row["trackinsight_expense_ratio"]) * 100, index)
        if not _blank(row.get("yahoo_expense_ratio")):
            return (3, float(row["yahoo_expense_ratio"]) * 100, index)
        return (4, index)

    if not active:
        return min(indexes)
    return min(pool, key=sort_key)


def _is_active(row: dict) -> bool:
    if row.get("status") == "active":
        return True
    if _blank(row.get("status")) and row.get("active_flag") in ("true", "Act", True):
        return True
    return False


def _add_source_columns(book) -> None:
    """R08. Insert the missing Trackinsight source columns and record them on Fields."""
    funds = book["Funds"]
    for after_key, field_key, detail in _SOURCE_COLUMNS:
        after = _field_columns(funds)[after_key]
        _insert_column(funds, after + 1, field_key)
    _refresh_field_letters(book)
    _append_field_rows(book)
    lists = book["Lists"]
    for title, value in _MASTER_LISTS:
        _append_list_value(lists, _list_column(lists, title), value)


def _extend_identity_formulas(funds) -> None:
    """R08. Point ticker, name, and vehicle masters at the new Trackinsight column."""
    columns = _field_columns(funds)
    for row in range(FIRST_DATA_ROW, LAST_FORMATTED_ROW + 1):
        for master, (source_key, branches) in _IDENTITY_FORMULAS.items():
            cell = funds.cell(row, columns[master])
            cell.value = _master_formula(columns, source_key, branches, row)
            cell.protection = Protection(locked=True)


def _master_formula(columns: dict[str, int], source_key: str, branches, row: int) -> str:
    source = f"{get_column_letter(columns[source_key])}{row}"
    expr = '""'
    for role, key, mapped in reversed(branches):
        ref = f"{get_column_letter(columns[key])}{row}"
        value = (
            f'IF({ref}="Open-End Fund","mutual_fund",IF({ref}="Equity ETF","etf",{ref}))'
            if mapped
            else ref
        )
        expr = f'IF({source}="{role}",IF({ref}="", "", {value}),{expr})'
    return f'=IF({source}="", "", {expr})'


def _insert_column(funds, idx: int, field_key: str) -> None:
    merges = [CellRange(str(item)) for item in funds.merged_cells.ranges]
    for item in list(funds.merged_cells.ranges):
        funds.unmerge_cells(str(item))
    validations = [(item, str(item.sqref)) for item in funds.data_validations.dataValidation]
    dimensions = {
        column_index_from_string(letter): dimension
        for letter, dimension in funds.column_dimensions.items()
        if letter.isalpha()
    }
    funds.insert_cols(idx)
    _shift_dimensions(funds, dimensions, idx)
    _copy_column_style(funds, idx - 1, idx)
    funds.cell(3, idx).value = f"Trackinsight\n{field_key}"
    _shift_merges(funds, merges, idx)
    _shift_validations(validations, idx)
    _shift_sheet_formulas(funds, idx)


def _shift_dimensions(funds, dimensions, idx: int) -> None:
    snapshot = {
        column: (dim.width, dim.outlineLevel, dim.hidden)
        for column, dim in dimensions.items()
    }
    for letter in list(funds.column_dimensions.keys()):
        if letter.isalpha():
            del funds.column_dimensions[letter]
    for column, (width, level, hidden) in snapshot.items():
        moved = column + 1 if column >= idx else column
        _write_dimension(funds, moved, width, level, hidden)
    previous = snapshot.get(idx - 1, (18, 2, False))
    _write_dimension(funds, idx, previous[0], 2, previous[2])


def _write_dimension(funds, column: int, width, level, hidden) -> None:
    dimension = funds.column_dimensions[get_column_letter(column)]
    dimension.width = width
    dimension.outlineLevel = level
    dimension.hidden = hidden


def _copy_column_style(funds, source: int, target: int) -> None:
    for row in range(1, LAST_FORMATTED_ROW + 1):
        origin = funds.cell(row, source)
        dest = funds.cell(row, target)
        dest.number_format = origin.number_format
        if origin.has_style:
            dest.font = copy(origin.font)
            dest.fill = copy(origin.fill)
            dest.border = copy(origin.border)
            dest.alignment = copy(origin.alignment)
            dest.protection = copy(origin.protection)


def _shift_merges(funds, merges, idx: int) -> None:
    for item in merges:
        min_col, max_col = _shift_bounds(item.min_col, item.max_col, idx)
        if item.max_col == idx - 1 and item.max_row <= 2:
            max_col = idx
        funds.merge_cells(
            start_row=item.min_row,
            start_column=min_col,
            end_row=item.max_row,
            end_column=max_col,
        )


def _shift_validations(validations, idx: int) -> None:
    for item, sqref in validations:
        shifted = []
        for part in str(sqref).split():
            bounds = CellRange(part)
            min_col, max_col = _shift_bounds(bounds.min_col, bounds.max_col, idx)
            shifted.append(_range_ref(min_col, bounds.min_row, max_col, bounds.max_row))
        item.sqref = " ".join(shifted)


def _shift_sheet_formulas(funds, idx: int) -> None:
    """insert_cols moves cells but leaves the column letters inside formulas unchanged."""
    for row in funds.iter_rows(min_row=1, max_row=funds.max_row, max_col=funds.max_column):
        for cell in row:
            shifted = _shift_formula_columns(cell.value, idx)
            if shifted:
                cell.value = shifted


def _shift_formula_columns(formula, idx: int) -> str | None:
    if not isinstance(formula, str) or not formula.startswith("="):
        return None

    def repl(match):
        column = column_index_from_string(match.group(2))
        letter = get_column_letter(column + 1) if column >= idx else match.group(2)
        return f"{match.group(1)}{letter}{match.group(3)}{match.group(4)}"

    return re.sub(r"(\$?)([A-Z]{1,3})(\$?)(\d+)", repl, formula)


def _shift_bounds(min_col: int, max_col: int, idx: int) -> tuple[int, int]:
    if max_col < idx:
        return min_col, max_col
    if min_col >= idx:
        return min_col + 1, max_col + 1
    return min_col, max_col + 1


def _range_ref(min_col: int, min_row: int, max_col: int, max_row: int) -> str:
    start = f"{get_column_letter(min_col)}{min_row}"
    end = f"{get_column_letter(max_col)}{max_row}"
    return start if start == end else f"{start}:{end}"


def _refresh_field_letters(book) -> None:
    letters = {
        key: get_column_letter(column) for key, column in _field_columns(book["Funds"]).items()
    }
    fields = book["Fields"]
    for row in range(4, fields.max_row + 1):
        key = fields.cell(row, 7).value
        if key in letters:
            fields.cell(row, 1).value = letters[key]


def _append_field_rows(book) -> None:
    fields = book["Fields"]
    letters = {
        key: get_column_letter(column) for key, column in _field_columns(book["Funds"]).items()
    }
    pattern = _fields_row(fields, "trackinsight_provider")
    for _after_key, field_key, detail in _SOURCE_COLUMNS:
        if _fields_row(fields, field_key):
            continue
        row = fields.max_row + 1
        for column in range(1, 13):
            origin = fields.cell(pattern, column)
            dest = fields.cell(row, column)
            if origin.has_style:
                dest.font = copy(origin.font)
                dest.fill = copy(origin.fill)
                dest.border = copy(origin.border)
                dest.alignment = copy(origin.alignment)
            dest.number_format = origin.number_format
        group = {"trackinsight_ticker": "Ticker", "trackinsight_name": "Name", "trackinsight_vehicle": "Vehicle"}
        values = {
            1: letters[field_key],
            2: 2,
            3: "Identity",
            4: group[field_key],
            5: "Trackinsight",
            6: "Trackinsight",
            7: field_key,
            8: field_key,
            9: "—",
            10: "Text",
            11: "@",
            12: detail,
        }
        for column, value in values.items():
            fields.cell(row, column).value = value


def _fields_row(fields, key: str) -> int | None:
    for row in range(4, fields.max_row + 1):
        if fields.cell(row, 7).value == key:
            return row
    return None


def _list_column(lists, title: str) -> int:
    for column in range(1, lists.max_column + 1):
        if lists.cell(5, column).value == title:
            return column
    raise KeyError(title)


def _append_list_value(lists, column: int, value: str) -> None:
    existing = _list_values(lists, column)
    if value in existing:
        return
    lists.cell(6 + len(existing), column).value = value


def _field_columns(funds) -> dict[str, int]:
    columns = {}
    for column in range(1, funds.max_column + 1):
        value = funds.cell(3, column).value
        if not value:
            continue
        key = str(value).split("\n")[-1].strip()
        if key:
            columns[key] = column
    return columns


def _make_room(funds, count: int) -> None:
    capacity = LAST_FORMATTED_ROW - FIRST_DATA_ROW + 1
    extra = count - capacity
    if extra <= 0:
        return
    funds.insert_rows(LAST_FORMATTED_ROW, extra)
    # The row that was at LAST_FORMATTED_ROW moves down with its old row numbers still in the formulas.
    for row in range(LAST_FORMATTED_ROW, LAST_FORMATTED_ROW + extra + 1):
        _copy_row_format(funds, FIRST_DATA_ROW, row)


def _copy_row_format(funds, source: int, target: int) -> None:
    for column in range(1, funds.max_column + 1):
        origin = funds.cell(source, column)
        dest = funds.cell(target, column)
        dest.number_format = origin.number_format
        shifted = _shift_formula(origin.value, source, target)
        if shifted:
            dest.value = shifted
        if origin.has_style:
            dest.font = copy(origin.font)
            dest.fill = copy(origin.fill)
            dest.border = copy(origin.border)
            dest.alignment = copy(origin.alignment)
            dest.protection = copy(origin.protection)


def _shift_formula(formula, source: int, target: int) -> str | None:
    if not isinstance(formula, str) or not formula.startswith("="):
        return None

    def repl(match):
        row = int(match.group(2))
        if row == source:
            return f"{match.group(1)}{target}"
        return match.group(0)

    return re.sub(r"(\$?[A-Z]{1,3})(\d+)", repl, formula)


def _append_codes(book, rows: list[dict]) -> None:
    lists = book["Lists"]
    for key, letter in _LIST_COLUMNS.items():
        column = column_index_from_string(letter)
        existing = _list_values(lists, column)
        row = 6 + len(existing)
        for value in _unique([item.get(key) for item in rows]):
            text = str(value)
            if text in existing:
                continue
            lists.cell(row, column).value = text
            existing.append(text)
            row += 1


def _list_values(lists, column: int) -> list[str]:
    values = []
    row = 6
    while not _blank(lists.cell(row, column).value):
        values.append(str(lists.cell(row, column).value))
        row += 1
    return values


def _unique(values) -> list:
    seen = []
    for value in values:
        if _blank(value) or value in seen:
            continue
        seen.append(value)
    return seen


def _put(row: dict, key: str, value) -> None:
    if not _blank(value):
        row[key] = value


def _blank(value) -> bool:
    return value is None or value == "" or (isinstance(value, float) and math.isnan(value))


def _list_empty(column: str) -> pl.Expr:
    values = pl.col(column)
    return values.is_null() | (values.list.len() == 0)


def _list_excludes(column: str, label: str) -> pl.Expr:
    return ~(pl.col(column).list.contains(label).fill_null(False))


def _records(value) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, pl.DataFrame):
        return [] if value.height == 0 else value.to_dicts()
    return list(value)


def _num(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    if len(text) == 10 and text[4] == "-":
        return date.fromisoformat(text)
    return None


def _unique_ticker(ticker, share_id: int, used: dict[str, int]) -> str:
    base = str(ticker or "").strip() or f"share_{share_id}"
    seen = used.get(base, 0)
    used[base] = seen + 1
    return base if seen == 0 else f"{base}_{share_id}"


def _first(report: dict, *keys):
    for key in keys:
        if report.get(key) not in (None, ""):
            return report.get(key)
    return None


if __name__ == "__main__":
    main()
