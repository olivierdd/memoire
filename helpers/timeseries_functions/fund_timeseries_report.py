"""Fill the fund timeseries PowerPoint template from a saved check folder.

The template (``assets/fund_timeseries_report_template.pptx``) is edited in
PowerPoint. Any text in it may contain ``{token}`` placeholders whose values come
from ``report_values``; type each token in one go so it stays in a single run.
A paragraph holding a list token (``{quality_checks}``) is repeated once per item.
Shapes named ``chart_returns`` and ``chart_regression`` are replaced by the charts,
at the same position and size.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import PercentFormatter
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Emu

from helpers.timeseries_functions.compute_fund_to_index_regression import (
    FIT_COLOR,
    FUND_COLOR,
    INDEX_COLOR,
)
from helpers.timeseries_functions.timeseries_check_overview import FILE_NOTES

REPORT_FILENAME = "outputs/fund-timeseries-report.pptx"
TEMPLATE_PATH = Path(__file__).parent / "assets" / "fund_timeseries_report_template.pptx"
CHART_SHAPES = ("chart_returns", "chart_regression")
NO_LLM = "No LLM evaluation is saved for this check."

_TOKEN = re.compile(r"\{([a-z0-9_]+)\}")
_FIT_TOKENS = {
    "fit_r_squared": "R²",
    "fit_r_squared_adj": "Adjusted R²",
    "fit_correlation": "Correlation",
    "fit_n_months": "Number of months",
    "fit_residual_se": "Residual standard error",
    "fit_alpha_annualized": "Alpha, annualized (× 12)",
    "fit_excess_annualized": "Annualized excess return",
    "fit_residual_volatility": "Annualized residual volatility",
    "fit_information_ratio": "Information ratio",
    "fit_f_statistic": "F statistic",
    "fit_f_pvalue": "Prob (F)",
}
_LLM_SCORES = (
    ("price_timeseries_reliable", "reliability"),
    ("tracks_sp500_tr", "tracks index"),
    ("active_management", "active"),
    ("regression_quality", "regression quality"),
)


@dataclass(frozen=True)
class FundTimeseriesReportData:
    check_dir: Path
    fund_static: dict
    parameters: dict
    comparison_summary: dict
    regression: dict
    regression_fit: dict[str, str]
    regression_sample: pd.DataFrame
    consistency_report: str
    worst_mismatch: dict | None
    llm_evaluation: dict | None


def load_report_data(check_dir: Path) -> FundTimeseriesReportData:
    """Read the saved check artifacts the report uses."""
    check_dir = Path(check_dir)
    outputs = check_dir / "outputs"
    fit = pd.read_csv(outputs / "regression-fit.csv", index_col=0)["Value"]
    worst_path = outputs / "worst-mismatch-summary.json"
    llm_path = outputs / "llm-evaluation-openai.json"
    return FundTimeseriesReportData(
        check_dir=check_dir,
        fund_static=_read_json(check_dir / "inputs/fund-static.json"),
        parameters=_read_json(check_dir / "inputs/parameters.json"),
        comparison_summary=_read_json(outputs / "source-comparison-summary.json"),
        regression=_read_json(outputs / "regression.json"),
        regression_fit={str(label): str(value) for label, value in fit.items()},
        regression_sample=pd.read_csv(
            outputs / "regression-sample.csv", parse_dates=["Date"]
        ),
        consistency_report=(outputs / "consistency-report.txt").read_text(encoding="utf-8"),
        worst_mismatch=_read_json(worst_path) if worst_path.is_file() else None,
        llm_evaluation=_read_json(llm_path) if llm_path.is_file() else None,
    )


def report_values(
    data: FundTimeseriesReportData, generated_at: datetime
) -> dict[str, str | list[str]]:
    """Value of every ``{token}`` the template may use."""
    static = data.fund_static
    params = data.parameters
    summary = data.comparison_summary
    regression = data.regression
    stats = regression["statistics"]
    llm = data.llm_evaluation if data.llm_evaluation and data.llm_evaluation.get("ok") else None
    scores = (llm or {}).get("scores") or {}
    basis = (llm or {}).get("score_basis") or {}
    active = scores.get("active_management")

    values: dict[str, str | list[str]] = {
        "fund_name": str(static["name"]),
        "isin": str(static["isin"]),
        "market_identifier": static.get("market_identifier") or "no ticker",
        "fund_wrapper": static.get("fund_wrapper") or "unknown vehicle",
        "management": static.get("fund_type") or "unknown",
        "master_timeseries": str(params["master_timeseries"]),
        "comparison_timeseries": str(params["comparison_timeseries"]),
        "index_column": str(params["index_column"]),
        "sample_start": str(regression["start"]),
        "sample_end": str(regression["end"]),
        "matched_months": str(summary["perfect_matches"] + summary["acceptable_matches"]),
        "n_months": str(summary["n_months"]),
        "mismatches": str(summary["mismatches"]),
        "quality_checks": _quality_checks(
            data.consistency_report, str(params["master_timeseries"])
        ),
        "worst_mismatch": (
            data.worst_mismatch["conclusion"]
            if data.worst_mismatch
            else "No worst-mismatch drill-down was run for this check."
        ),
        "equation": str(regression["equation"]),
        "beta": f"{stats['beta']:.3f}",
        "r_squared": f"{stats['r_squared']:.3f}",
        "llm_scores": " · ".join(
            f"{label} {scores[key]:.2f}"
            for key, label in _LLM_SCORES
            if isinstance(scores.get(key), (int, float))
        )
        or "not available",
        "llm_active": f"{active:.2f}" if isinstance(active, (int, float)) else "n/a",
        "llm_active_basis": basis.get("active_management") or NO_LLM,
        "llm_timeseries_reading": (llm or {}).get("timeseries_interpretation") or NO_LLM,
        "llm_regression_reading": (llm or {}).get("regression_interpretation") or NO_LLM,
        "generated_at": f"{generated_at:%Y-%m-%d %H:%M %Z}",
    }
    for token, label in _FIT_TOKENS.items():
        values[token] = data.regression_fit[label]
    return values


def write_fund_timeseries_report(
    check_dir: Path,
    *,
    output_path: Path | None = None,
    template: Path = TEMPLATE_PATH,
) -> Path:
    """Fill the template and write ``outputs/fund-timeseries-report.pptx``."""
    check_dir = Path(check_dir)
    data = load_report_data(check_dir)
    values = report_values(data, datetime.now().astimezone())
    deck = Presentation(str(template))

    charts_found = set()
    for slide in deck.slides:
        for shape in list(slide.shapes):
            if shape.name in CHART_SHAPES:
                _replace_with_chart(slide, shape, data)
                charts_found.add(shape.name)
            else:
                _fill_shape(shape, values)
    missing = set(CHART_SHAPES) - charts_found
    if missing:
        raise KeyError(f"Template has no shape named {', '.join(sorted(missing))}")

    dest = Path(output_path) if output_path else check_dir / REPORT_FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    deck.save(str(dest))
    if dest.resolve() == (check_dir / REPORT_FILENAME).resolve():
        merge_report_into_manifest(check_dir, REPORT_FILENAME)
    return dest


def merge_report_into_manifest(check_dir: Path, relative_path: str) -> None:
    """Append the report entry to ``manifest.json`` when present."""
    manifest_path = Path(check_dir) / "manifest.json"
    if not manifest_path.is_file():
        return
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = document.setdefault("files", [])
    if relative_path not in [item["path"] for item in files]:
        files.append({"path": relative_path, "description": FILE_NOTES[relative_path]})
    manifest_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _fill_shape(shape, values: dict) -> None:
    if shape.has_text_frame:
        _fill_text_frame(shape.text_frame, values)
    elif getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            for cell in row.cells:
                _fill_text_frame(cell.text_frame, values)
    elif hasattr(shape, "shapes"):
        for child in shape.shapes:
            _fill_shape(child, values)


def _fill_text_frame(text_frame, values: dict) -> None:
    for paragraph in list(text_frame.paragraphs):
        element = paragraph._p
        tokens = _TOKEN.findall(paragraph.text)
        lists = [token for token in tokens if isinstance(values.get(token), list)]
        if len(lists) > 1:
            raise ValueError(f"One list token per paragraph: {paragraph.text!r}")
        if not lists:
            _substitute(element, values)
            continue
        for item in values[lists[0]]:
            clone = copy.deepcopy(element)
            element.addprevious(clone)
            _substitute(clone, {**values, lists[0]: item})
        element.getparent().remove(element)


def _substitute(paragraph_element, values: dict) -> None:
    def replace(match: re.Match) -> str:
        token = match.group(1)
        if token not in values:
            raise KeyError(f"Template token {{{token}}} has no value")
        return str(values[token])

    texts = list(paragraph_element.iter(qn("a:t")))
    for text in texts:
        if text.text:
            text.text = _TOKEN.sub(replace, text.text)
    leftover = _TOKEN.search("".join(text.text or "" for text in texts))
    if leftover:
        raise ValueError(
            f"Token {leftover.group(0)} is split across text runs; retype it in the template"
        )


def _replace_with_chart(slide, placeholder, data: FundTimeseriesReportData) -> None:
    size = (Emu(placeholder.width).inches, Emu(placeholder.height).inches)
    render = _returns_png if placeholder.name == "chart_returns" else _regression_png
    picture = slide.shapes.add_picture(
        BytesIO(render(data, size)),
        placeholder.left,
        placeholder.top,
        placeholder.width,
        placeholder.height,
    )
    picture.name = placeholder.name
    placeholder._element.addprevious(picture._element)
    placeholder._element.getparent().remove(placeholder._element)


def _returns_png(data: FundTimeseriesReportData, size: tuple[float, float]) -> bytes:
    params = data.parameters
    sample = data.regression_sample
    fig, ax = _figure(size)
    ax.axhline(0, color="#E4E4E4", linewidth=0.8)
    ax.plot(
        sample["Date"],
        sample[params["index_column"]],
        color=INDEX_COLOR,
        linestyle=(0, (5, 3)),
        linewidth=0.9,
        label=params["index_column"],
    )
    ax.plot(
        sample["Date"],
        sample[params["master_column"]],
        color=FUND_COLOR,
        linewidth=1.0,
        label=params["master_timeseries"],
    )
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_title("Monthly total return", fontsize=8, color=FUND_COLOR, loc="left")
    ax.legend(
        loc="lower right",
        bbox_to_anchor=(1.0, 1.0),
        fontsize=6.5,
        frameon=False,
        ncols=2,
        borderaxespad=0.2,
    )
    return _png(fig)


def _regression_png(data: FundTimeseriesReportData, size: tuple[float, float]) -> bytes:
    params = data.parameters
    stats = data.regression["statistics"]
    sample = data.regression_sample
    x = sample[params["index_column"]]
    fig, ax = _figure(size)
    ax.scatter(
        x, sample[params["master_column"]], s=7, alpha=0.7, color=FUND_COLOR, linewidths=0
    )
    ends = [x.min(), x.max()]
    ax.plot(
        ends,
        [stats["alpha"] + stats["beta"] * end for end in ends],
        color=FIT_COLOR,
        linewidth=1.3,
    )
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlabel(params["index_column"], fontsize=7)
    ax.set_ylabel(params["master_timeseries"], fontsize=7)
    ax.set_title(
        f"Fitted line · R² = {stats['r_squared']:.3f}",
        fontsize=8,
        color=FUND_COLOR,
        loc="left",
    )
    return _png(fig)


def _figure(size: tuple[float, float]):
    fig, ax = plt.subplots(figsize=size, dpi=220, layout="constrained")
    ax.tick_params(labelsize=6.5, colors="#555555", length=2)
    ax.grid(True, color="#EEEEEE", linewidth=0.5)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#CCCCCC")
    return fig, ax


def _png(fig) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", facecolor="white")
    plt.close(fig)
    return buffer.getvalue()


def _quality_checks(report: str, master_timeseries: str) -> list[str]:
    """Master-series lines of the consistency report, without ISO dates."""
    lines: list[str] = []
    in_master = False
    for line in report.splitlines():
        if line and not line[0].isspace():
            in_master = line.strip() == master_timeseries
            continue
        if in_master and line.strip():
            text = re.sub(r"\b\d{4}-\d{2}-\d{2}\s+", "", line.strip())
            lines.append(re.sub(r"\s{2,}", " · ", text))
    return lines or ["No checks recorded"]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
