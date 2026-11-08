"""Run timeseries checks, LLM evaluation, reports, and a combined deck for many funds."""

from __future__ import annotations

import io
import os
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn

from helpers.timeseries_functions.compare_regression_to_consolidation import (
    compare_regression_to_consolidation,
)
from helpers.timeseries_functions.compare_regression_to_lipper_funds import (
    compare_regression_to_lipper_funds,
)
from helpers.timeseries_functions.compare_timeseries_sources import (
    compare_timeseries_sources,
)
from helpers.timeseries_functions.compute_fund_to_index_regression import (
    compute_fund_to_index_regression,
)
from helpers.timeseries_functions.diagnose_worst_mismatch import (
    diagnose_worst_mismatch,
)
from helpers.timeseries_functions.fund_llm_dossier import build_dossier_from_run
from helpers.timeseries_functions.fund_llm_providers import (
    DEFAULT_GENERATIVE_MODELS,
    call_openai,
    provider_result_as_json,
)
from helpers.timeseries_functions.fund_timeseries_report import (
    REPORT_FILENAME,
    write_fund_timeseries_report,
)
from helpers.timeseries_functions.load_fund_all_timeseries import (
    INDEX_COLUMN,
    load_fund_all_timeseries,
)
from helpers.timeseries_functions.load_lipper_timeseries import META_LABELS
from helpers.timeseries_functions.save_timeseries_check import (
    find_project_root,
    save_timeseries_check,
)

ALL_FUNDS_REPORT = "all-funds-report.pptx"
_GROUP_TAGS = frozenset({"nvGrpSpPr", "grpSpPr"})
_CHECK_MARKERS = (
    "manifest.json",
    "inputs/fund-timeseries.csv",
    "outputs/regression.json",
)


@dataclass(frozen=True)
class BatchCheckConfig:
    """Same defaults as ``check-fund-timeseries.ipynb``."""

    master_timeseries: str = "Lipper"
    comparison_timeseries: str = "Yahoo"
    match_tolerance: float = 1e-4
    spike_return: float = 0.10
    reversal_band: float = 0.15
    scale_factor: float = 5.0
    scale_window: int = 12
    level_jump: float = 0.50
    index_gap: float = 0.05
    date_gap_days: int = 45
    date_resolution_sessions: int = 6
    workbook_relative: Path = Path("input-data-alix") / "clean"
    workbook_filename: str = "CLEAN_RECOLTE DONNEES-EXCEL.xlsx"
    openfigi_cache: Path = Path("cache") / "cache-isin-openfigi.json"
    sp500_cache: Path = Path("cache") / "cache-sp500-tr-indices.json"
    openai_model: str = DEFAULT_GENERATIVE_MODELS["openai"]


def funds_with_timeseries(
    timeseries_df: pd.DataFrame, funds: pd.DataFrame
) -> pd.DataFrame:
    """Funds whose Timeseries column has at least one numeric Lipper return."""
    rows = timeseries_df.loc[~timeseries_df["id"].isin(META_LABELS)]
    eligible: list[str] = []
    for isin in funds["ISIN"]:
        if isin not in timeseries_df.columns:
            continue
        if pd.to_numeric(rows[isin], errors="coerce").notna().any():
            eligible.append(str(isin))
    return funds.loc[funds["ISIN"].isin(eligible)].reset_index(drop=True)


def fund_check_dir(isin: str, *, checks_root: Path | None = None) -> Path:
    root = checks_root or (find_project_root() / "output-data" / "timeseries-checks")
    return root / isin


def saved_fund_outputs(
    isin: str,
    *,
    require_llm: bool = True,
    require_report: bool = True,
    checks_root: Path | None = None,
) -> tuple[Path, Path | None] | None:
    """Return ``(check_dir, report_path)`` when a prior run left outputs on disk."""
    check_dir = fund_check_dir(isin, checks_root=checks_root)
    report_path = check_dir / REPORT_FILENAME
    required = [check_dir / relative for relative in _CHECK_MARKERS]
    if require_llm:
        required.append(check_dir / "outputs/llm-evaluation-openai.json")
    if not all(path.is_file() for path in required):
        return None
    if require_report and not report_path.is_file():
        return None
    if require_report:
        return check_dir, report_path
    return check_dir, report_path if report_path.is_file() else None


def run_fund_check(
    isin: str,
    *,
    timeseries_df: pd.DataFrame,
    funds: pd.DataFrame,
    config: BatchCheckConfig | None = None,
    run_llm: bool = True,
    openai_api_key: str | None = None,
) -> Path:
    """Full check for one ISIN; returns the saved check folder."""
    config = config or BatchCheckConfig()
    selected = funds.loc[funds["ISIN"].eq(isin)]
    if selected.empty:
        raise KeyError(f"{isin} is not in the fund list")
    selected = selected.iloc[0]

    with redirect_stdout(io.StringIO()):
        fund_timeseries, _, load_ctx = load_fund_all_timeseries(
            timeseries_df,
            funds,
            isin,
            config.sp500_cache,
            match_tolerance=config.match_tolerance,
            max_shift_sessions=config.date_resolution_sessions,
        )
        compared, master_column, comparison_column, gap, mismatch = (
            compare_timeseries_sources(
                fund_timeseries,
                isin,
                selected,
                master_timeseries=config.master_timeseries,
                comparison_timeseries=config.comparison_timeseries,
                match_tolerance=config.match_tolerance,
                yahoo_level=load_ctx.yahoo_level,
                close=load_ctx.close,
                distribution=load_ctx.distribution,
            )
        )
        regression_result = compute_fund_to_index_regression(
            fund_timeseries,
            INDEX_COLUMN,
            master_column,
            fund_name=str(selected["Name"]),
            master_timeseries=config.master_timeseries,
            quiet=True,
        )
        lipper_regression_comparison = compare_regression_to_lipper_funds(
            regression_result,
            fund_timeseries,
            INDEX_COLUMN,
            master_column,
            isin,
            config.workbook_relative,
            config.workbook_filename,
            fund_name=str(selected["Name"]),
            master_timeseries=config.master_timeseries,
        )
        consolidation_regression_comparison = compare_regression_to_consolidation(
            regression_result,
            fund_timeseries,
            INDEX_COLUMN,
            master_column,
            isin,
            config.workbook_relative,
            config.workbook_filename,
            fund_name=str(selected["Name"]),
            master_timeseries=config.master_timeseries,
        )
        date_check = diagnose_worst_mismatch(
            fund_timeseries,
            compared,
            gap,
            mismatch,
            master_column,
            comparison_column,
            selected,
            isin,
            master_timeseries=config.master_timeseries,
            comparison_timeseries=config.comparison_timeseries,
            match_tolerance=config.match_tolerance,
            yahoo_level=load_ctx.yahoo_level,
        )

    openai_llm_evaluation = None
    if run_llm:
        key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is not set in the environment or .env")
        dossier = build_dossier_from_run(
            selected_fund=isin,
            selected=selected,
            fund_timeseries=fund_timeseries,
            index_column=INDEX_COLUMN,
            master_column=master_column,
            comparison_column=comparison_column,
            master_timeseries=config.master_timeseries,
            comparison_timeseries=config.comparison_timeseries,
            match_tolerance=config.match_tolerance,
            compared=compared,
            gap=gap,
            mismatch=mismatch,
            regression_result=regression_result,
            lipper_regression_comparison=lipper_regression_comparison,
            consolidation_regression_comparison=consolidation_regression_comparison,
            date_check=date_check,
            spike_return=config.spike_return,
            reversal_band=config.reversal_band,
            scale_factor=config.scale_factor,
            scale_window=config.scale_window,
            level_jump=config.level_jump,
            index_gap=config.index_gap,
            date_gap_days=config.date_gap_days,
            workbook_relative=config.workbook_relative,
            workbook_filename=config.workbook_filename,
            shifted_months=load_ctx.shifted_months,
        )
        result = call_openai(dossier, api_key=key, model=config.openai_model)
        if not result.ok:
            raise RuntimeError(result.error or "OpenAI evaluation failed")
        openai_llm_evaluation = provider_result_as_json(result)

    return save_timeseries_check(
        selected_fund=isin,
        selected=selected,
        fund_timeseries=fund_timeseries,
        index_column=INDEX_COLUMN,
        master_timeseries=config.master_timeseries,
        comparison_timeseries=config.comparison_timeseries,
        match_tolerance=config.match_tolerance,
        date_resolution={
            "match_tolerance": config.match_tolerance,
            "max_shift_sessions": config.date_resolution_sessions,
        },
        shifted_months=load_ctx.shifted_months,
        compared=compared,
        master_column=master_column,
        comparison_column=comparison_column,
        gap=gap,
        mismatch=mismatch,
        regression_result=regression_result,
        lipper_regression_comparison=lipper_regression_comparison,
        consolidation_regression_comparison=consolidation_regression_comparison,
        date_check=date_check,
        spike_return=config.spike_return,
        reversal_band=config.reversal_band,
        scale_factor=config.scale_factor,
        scale_window=config.scale_window,
        level_jump=config.level_jump,
        index_gap=config.index_gap,
        date_gap_days=config.date_gap_days,
        workbook_relative=config.workbook_relative,
        workbook_filename=config.workbook_filename,
        openai_llm_evaluation=openai_llm_evaluation,
    )


def run_fund_batch(
    fund_isins: list[str],
    *,
    timeseries_df: pd.DataFrame,
    funds: pd.DataFrame,
    config: BatchCheckConfig | None = None,
    run_llm: bool = True,
    write_powerpoint: bool = True,
    reuse_cached_outputs: bool = True,
    checks_root: Path | None = None,
    progress: Callable[[str], None] | None = print,
) -> pd.DataFrame:
    """Check, evaluate, and report each ISIN; failures are recorded and skipped."""
    config = config or BatchCheckConfig()
    checks_root = checks_root or (find_project_root() / "output-data" / "timeseries-checks")

    if run_llm and not os.environ.get("OPENAI_API_KEY"):
        needs_key = not reuse_cached_outputs or any(
            saved_fund_outputs(
                isin,
                require_llm=True,
                require_report=write_powerpoint,
                checks_root=checks_root,
            )
            is None
            for isin in fund_isins
        )
        if needs_key:
            raise ValueError("OPENAI_API_KEY is not set in the environment or .env")

    records: list[dict] = []
    for index, isin in enumerate(fund_isins, start=1):
        name = funds.loc[funds["ISIN"].eq(isin), "Name"]
        fund_name = str(name.iloc[0]) if not name.empty else ""
        if progress:
            progress(f"[{index}/{len(fund_isins)}] {isin} {fund_name}")
        try:
            reused = False
            if reuse_cached_outputs:
                cached = saved_fund_outputs(
                    isin,
                    require_llm=run_llm,
                    require_report=write_powerpoint,
                    checks_root=checks_root,
                )
                if cached is not None:
                    check_dir, report_path = cached
                    reused = True
                else:
                    check_dir = run_fund_check(
                        isin,
                        timeseries_df=timeseries_df,
                        funds=funds,
                        config=config,
                        run_llm=run_llm,
                    )
                    report_path = (
                        write_fund_timeseries_report(check_dir)
                        if write_powerpoint
                        else None
                    )
            else:
                check_dir = run_fund_check(
                    isin,
                    timeseries_df=timeseries_df,
                    funds=funds,
                    config=config,
                    run_llm=run_llm,
                )
                report_path = (
                    write_fund_timeseries_report(check_dir) if write_powerpoint else None
                )

            records.append(
                {
                    "isin": isin,
                    "name": fund_name,
                    "ok": True,
                    "reused": reused,
                    "error": None,
                    "check_dir": str(check_dir),
                    "report_path": str(report_path) if report_path else None,
                }
            )
            if progress and reused:
                progress(f"    reused saved check and report")
        except Exception as exc:  # noqa: BLE001 — batch continues on failure
            records.append(
                {
                    "isin": isin,
                    "name": fund_name,
                    "ok": False,
                    "reused": False,
                    "error": str(exc),
                    "check_dir": None,
                    "report_path": None,
                }
            )
    return pd.DataFrame(records)


def combine_fund_reports(
    report_paths: list[Path | str],
    dest: Path | str,
) -> Path:
    """One slide per fund report, preserving images."""
    paths = [Path(path) for path in report_paths]
    if not paths:
        raise ValueError("report_paths is empty")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    combined = Presentation(str(paths[0]))
    _keep_first_slide_only(combined)
    for path in paths[1:]:
        source = Presentation(str(path))
        if not source.slides:
            raise ValueError(f"No slides in {path}")
        _append_slide(combined, source.slides[0])

    combined.save(str(dest))
    return dest


def default_all_funds_report_path(*, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    return root / "output-data" / "timeseries-checks" / ALL_FUNDS_REPORT


def _keep_first_slide_only(presentation: Presentation) -> None:
    while len(presentation.slides) > 1:
        r_id = presentation.slides._sldIdLst[1].rId
        presentation.part.drop_rel(r_id)
        del presentation.slides._sldIdLst[1]


def _append_slide(dest_presentation: Presentation, src_slide) -> None:
    dest_slide = dest_presentation.slides.add_slide(dest_presentation.slide_layouts[6])
    sp_tree = dest_slide.shapes._spTree
    for child in list(sp_tree):
        if child.tag.split("}")[-1] not in _GROUP_TAGS:
            sp_tree.remove(child)

    relmap = _image_relmap(src_slide.part, dest_slide.part)
    for element in src_slide.shapes._spTree:
        tag = element.tag.split("}")[-1]
        if tag in _GROUP_TAGS:
            continue
        clone = deepcopy(element)
        for blip in clone.iter(qn("a:blip")):
            old = blip.get(qn("r:embed"))
            if old in relmap:
                blip.set(qn("r:embed"), relmap[old])
        sp_tree.append(clone)


def _image_relmap(src_part, dest_part) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for r_id, rel in src_part.rels.items():
        if rel.reltype != RT.IMAGE:
            continue
        _, new_r_id = dest_part.get_or_add_image_part(io.BytesIO(rel.target_part.blob))
        mapping[r_id] = new_r_id
    return mapping
