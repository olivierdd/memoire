import json
import unittest
from datetime import datetime
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from helpers.timeseries_functions.compute_fund_to_index_regression import (
    compute_fund_to_index_regression,
)
from helpers.timeseries_functions.save_timeseries_check import (
    _checks_dir,
    find_project_root,
    save_timeseries_check,
)
from helpers.timeseries_functions.timeseries_check_bundle import (
    comparison_summary,
    json_ready,
    source_comparison_frame,
)

ISIN = "US0000000001"
INDEX = "S&P 500 TR"
MASTER = f"{ISIN} (Lipper)"
COMPARISON = f"{ISIN} (Yahoo)"
TOLERANCE = 1e-4


def _returns() -> tuple[list[float], list[float], list[float]]:
    index = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02, 0.0, 0.012]
    lipper = index.copy()
    lipper[1] = index[1] + 0.00005
    lipper[5] = 0.08
    yahoo = index.copy()
    return index, lipper, yahoo


def _fund_frame() -> pd.DataFrame:
    dates = pd.to_datetime(
        [
            "2010-01-01",
            "2010-02-01",
            "2010-03-01",
            "2010-04-01",
            "2010-05-01",
            "2010-06-01",
            "2010-07-01",
            "2010-08-01",
        ]
    )
    index, lipper, yahoo = _returns()
    return pd.DataFrame(
        {
            "Period": dates.strftime("%b %Y"),
            "Date": dates,
            "Time": "Close",
            MASTER: lipper,
            COMPARISON: yahoo,
            f"{ISIN} (FinanceDatabase)": yahoo,
            INDEX: index,
        }
    )


def _gap_and_mismatch(compared: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    master = compared[MASTER]
    other = compared[COMPARISON]
    gap = (master - other).abs()
    both_missing = master.isna() & other.isna()
    one_missing = master.isna() ^ other.isna()
    perfect = both_missing | gap.eq(0)
    acceptable = ~perfect & ~one_missing & gap.le(TOLERANCE)
    return gap, ~(perfect | acceptable)


def _date_check() -> pd.DataFrame:
    start = pd.DataFrame(
        {
            "Level": [10.0, 10.1],
            "return": [0.01, 0.02],
            "gap": [0.05, 0.001],
            "recorded": [True, False],
        },
        index=pd.to_datetime(["2010-06-01", "2010-06-02"]),
    )
    end = pd.DataFrame(
        {
            "Level": [10.2, 10.3],
            "return": [0.03, 0.08],
            "gap": [0.04, 0.00005],
            "recorded": [True, False],
        },
        index=pd.to_datetime(["2010-07-01", "2010-07-02"]),
    )
    return pd.concat(
        {"start date": start, "observation date": end},
        names=["varied", "Date"],
    )


def _save(
    folder: Path,
    *,
    date_check: pd.DataFrame | None,
    openai_llm_evaluation: dict | None = None,
) -> Path:
    fund = _fund_frame()
    compared = fund[["Period", "Date", MASTER, COMPARISON]].copy()
    gap, mismatch = _gap_and_mismatch(compared)
    regression = compute_fund_to_index_regression(
        fund,
        INDEX,
        MASTER,
        fund_name="Example Fund",
        master_timeseries="Lipper",
        quiet=True,
    )
    lipper = pd.DataFrame(
        {
            "Horizon": ["All available"],
            "Months": [8],
            "Metric": ["Beta"],
            "Notebook": ["1.000"],
            "Lipper Funds": [""],
            "Delta (notebook − Lipper)": [""],
        }
    )
    consolidation = pd.DataFrame(
        {
            "Window": ["2010-01-01 to 2010-08-01"],
            "Months": [8],
            "Metric": ["Beta"],
            "Notebook": ["1.000"],
            "Consolidation": ["1.000"],
            "Delta (notebook − Consolidation)": ["0.000"],
        }
    )
    selected = pd.Series(
        {
            "ISIN": ISIN,
            "Name": "Example Fund",
            "market_identifier": "EXMPX",
            "fund_wrapper": "mutual fund",
            "fund_type": "Active",
        }
    )
    with redirect_stdout(StringIO()):
        return save_timeseries_check(
            selected_fund=ISIN,
            selected=selected,
            fund_timeseries=fund,
            index_column=INDEX,
            master_timeseries="Lipper",
            comparison_timeseries="Yahoo",
            match_tolerance=TOLERANCE,
            compared=compared,
            master_column=MASTER,
            comparison_column=COMPARISON,
            gap=gap,
            mismatch=mismatch,
            regression_result=regression,
            lipper_regression_comparison=lipper,
            consolidation_regression_comparison=consolidation,
            date_check=date_check,
            spike_return=0.10,
            reversal_band=0.15,
            scale_factor=5,
            scale_window=12,
            level_jump=0.50,
            index_gap=0.05,
            date_gap_days=45,
            output_dir=folder,
            openai_llm_evaluation=openai_llm_evaluation,
        )


class SaveTimeseriesCheckTest(unittest.TestCase):
    def test_json_ready_serializes_excel_inception_datetime(self) -> None:
        self.assertEqual(
            json_ready(datetime(1998, 3, 15, 0, 0, 0)),
            "1998-03-15",
        )

    def test_project_root_and_default_folder(self) -> None:
        root = find_project_root()
        self.assertTrue((root / "pyproject.toml").is_file())
        self.assertEqual(
            _checks_dir(None),
            root / "output-data" / "timeseries-checks",
        )

    def test_saves_inputs_and_outputs_for_one_isin(self) -> None:
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            (parent / "keep.txt").write_text("leave this\n", encoding="utf-8")
            saved = _save(parent, date_check=_date_check())
            stale = saved / "outputs" / "stale.txt"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_text("old\n", encoding="utf-8")
            saved = _save(parent, date_check=_date_check())

            self.assertEqual(saved.name, ISIN)
            kept = (parent / "keep.txt").read_text(encoding="utf-8")
            self.assertEqual(kept, "leave this\n")
            self.assertFalse(stale.exists())

            expected = {
                "manifest.json",
                "overview.md",
                "inputs/fund-static.json",
                "inputs/parameters.json",
                "inputs/fund-timeseries.csv",
                "outputs/source-comparison.csv",
                "outputs/source-comparison-summary.json",
                "outputs/consistency-report.txt",
                "outputs/quality-summary.json",
                "outputs/regression.json",
                "outputs/regression-coefficients.csv",
                "outputs/regression-fit.csv",
                "outputs/regression-sample.csv",
                "outputs/lipper-regression-comparison.csv",
                "outputs/consolidation-regression-comparison.csv",
                "outputs/worst-mismatch.csv",
                "outputs/worst-mismatch-summary.json",
                "outputs/charts.html",
            }
            written = {
                path.relative_to(saved).as_posix()
                for path in saved.rglob("*")
                if path.is_file()
            }
            self.assertEqual(written, expected)

            fund = json.loads((saved / "inputs" / "fund-static.json").read_text())
            self.assertEqual(fund["isin"], ISIN)
            self.assertEqual(fund["name"], "Example Fund")
            self.assertEqual(fund["market_identifier"], "EXMPX")
            self.assertEqual(fund["fund_wrapper"], "mutual fund")
            self.assertEqual(fund["fund_type"], "Active")

            parameters = json.loads((saved / "inputs" / "parameters.json").read_text())
            self.assertEqual(parameters["master_timeseries"], "Lipper")
            self.assertEqual(parameters["scale_window"], 12)
            self.assertAlmostEqual(parameters["match_tolerance"], TOLERANCE)

            timeseries = (saved / "inputs" / "fund-timeseries.csv").read_text()
            self.assertIn(f"{ISIN} (FinanceDatabase)", timeseries)
            self.assertIn("2010-06-01", timeseries)

            summary = json.loads(
                (saved / "outputs" / "source-comparison-summary.json").read_text()
            )
            self.assertEqual(summary["n_months"], 8)
            self.assertEqual(summary["perfect_matches"], 6)
            self.assertEqual(summary["acceptable_matches"], 1)
            self.assertEqual(summary["mismatches"], 1)
            self.assertEqual(summary["one_side_missing"], 0)

            comparison = pd.read_csv(saved / "outputs" / "source-comparison.csv")
            june = comparison.loc[comparison["Period"].eq("Jun 2010")].iloc[0]
            february = comparison.loc[comparison["Period"].eq("Feb 2010")].iloc[0]
            january = comparison.loc[comparison["Period"].eq("Jan 2010")].iloc[0]
            self.assertEqual(june["match"], "mismatch")
            self.assertAlmostEqual(june["gap_bp"], 600.0, places=6)
            self.assertEqual(february["match"], "acceptable")
            self.assertAlmostEqual(february["gap_bp"], 0.5, places=6)
            self.assertEqual(january["match"], "perfect")
            self.assertEqual(january["gap"], 0.0)

            report = (saved / "outputs" / "consistency-report.txt").read_text()
            self.assertIn("Lipper", report)
            self.assertIn("Yahoo", report)
            self.assertIn("2010-06-01", report)

            regression = json.loads((saved / "outputs" / "regression.json").read_text())
            self.assertIn("Lipper", regression["equation"])
            self.assertIn(INDEX, regression["equation"])
            self.assertEqual(regression["statistics"]["n_months"], 8)
            self.assertEqual(regression["start"], "2010-01-01")
            self.assertEqual(regression["end"], "2010-08-01")

            lipper = pd.read_csv(saved / "outputs" / "lipper-regression-comparison.csv")
            self.assertEqual(list(lipper["Metric"]), ["Beta"])

            drilldown = json.loads(
                (saved / "outputs" / "worst-mismatch-summary.json").read_text()
            )
            self.assertTrue(drilldown["date_mismatch"])
            self.assertEqual(drilldown["best_date"], "2010-07-02")
            self.assertEqual(drilldown["best_role"], "observation date")
            self.assertIn("date mismatch", drilldown["conclusion"])

            overview = (saved / "overview.md").read_text()
            self.assertIn("Example Fund (US0000000001)", overview)
            self.assertIn("Mismatches: 1 of 8", overview)
            self.assertIn("date mismatch", overview)

            manifest = json.loads((saved / "manifest.json").read_text())
            self.assertEqual(
                [item["path"] for item in manifest["files"]],
                [
                    "manifest.json",
                    "overview.md",
                    "inputs/fund-static.json",
                    "inputs/parameters.json",
                    "inputs/fund-timeseries.csv",
                    "outputs/source-comparison.csv",
                    "outputs/source-comparison-summary.json",
                    "outputs/consistency-report.txt",
                    "outputs/quality-summary.json",
                    "outputs/regression.json",
                    "outputs/regression-coefficients.csv",
                    "outputs/regression-fit.csv",
                    "outputs/regression-sample.csv",
                    "outputs/lipper-regression-comparison.csv",
                    "outputs/consolidation-regression-comparison.csv",
                    "outputs/worst-mismatch.csv",
                    "outputs/worst-mismatch-summary.json",
                    "outputs/charts.html",
                ],
            )
            self.assertTrue(all(item["description"] for item in manifest["files"]))
            chart = (saved / "outputs" / "charts.html").read_text()
            self.assertIn("<html", chart.lower())
            self.assertIn("vega", chart.lower())

    def test_includes_openai_llm_evaluation_when_provided(self) -> None:
        payload = {
            "provider": "openai",
            "model": "gpt-5.4",
            "ok": True,
            "error": None,
            "scores": {"price_timeseries_reliable": 0.9},
            "score_basis": None,
            "timeseries_interpretation": "ok",
            "regression_interpretation": "ok",
        }
        with TemporaryDirectory() as tmp:
            saved = _save(Path(tmp), date_check=None, openai_llm_evaluation=payload)
            path = saved / "outputs" / "llm-evaluation-openai.json"
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text()), payload)
            manifest = json.loads((saved / "manifest.json").read_text())
            paths = [item["path"] for item in manifest["files"]]
            self.assertIn("outputs/llm-evaluation-openai.json", paths)

    def test_omits_worst_mismatch_when_the_drilldown_is_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            saved = _save(Path(tmp), date_check=None)
            self.assertFalse((saved / "outputs" / "worst-mismatch.csv").exists())
            self.assertFalse(
                (saved / "outputs" / "worst-mismatch-summary.json").exists()
            )
            overview = (saved / "overview.md").read_text()
            self.assertIn("This run has no worst-mismatch table.", overview)
            manifest = json.loads((saved / "manifest.json").read_text())
            paths = [item["path"] for item in manifest["files"]]
            self.assertNotIn("outputs/worst-mismatch.csv", paths)

    def test_rejects_a_bad_isin_and_an_inconsistent_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            with self.assertRaises(ValueError):
                save_timeseries_check(
                    **{**_kwargs(parent), "selected_fund": "../US0000000001"}
                )
            self.assertEqual(list(parent.iterdir()), [])

            kwargs = _kwargs(parent)
            kwargs["mismatch"] = pd.Series(False, index=kwargs["compared"].index)
            with self.assertRaises(ValueError):
                save_timeseries_check(**kwargs)
            self.assertEqual(list(parent.iterdir()), [])

    def test_refuses_to_replace_a_symlink(self) -> None:
        with TemporaryDirectory() as tmp:
            parent = Path(tmp)
            elsewhere = parent / "elsewhere"
            elsewhere.mkdir()
            (parent / ISIN).symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaises(ValueError):
                _save(parent, date_check=None)
            self.assertTrue(elsewhere.is_dir())
            self.assertEqual(list(elsewhere.iterdir()), [])

    def test_missing_returns_follow_the_notebook_match_rules(self) -> None:
        compared = pd.DataFrame(
            {
                "Period": ["Jan 2010", "Feb 2010", "Mar 2010"],
                "Date": pd.to_datetime(["2010-01-01", "2010-02-01", "2010-03-01"]),
                MASTER: [0.01, None, None],
                COMPARISON: [0.01, 0.02, None],
            }
        )
        gap, mismatch = _gap_and_mismatch(compared)
        frame = source_comparison_frame(
            compared, MASTER, COMPARISON, gap, mismatch, TOLERANCE
        )
        self.assertEqual(list(frame["match"]), ["perfect", "mismatch", "perfect"])
        summary = comparison_summary(
            frame,
            master_timeseries="Lipper",
            comparison_timeseries="Yahoo",
            master_column=MASTER,
            comparison_column=COMPARISON,
            match_tolerance=TOLERANCE,
        )
        self.assertEqual(summary["perfect_matches"], 2)
        self.assertEqual(summary["mismatches"], 1)
        self.assertEqual(summary["one_side_missing"], 1)


def _kwargs(folder: Path) -> dict:
    fund = _fund_frame()
    compared = fund[["Period", "Date", MASTER, COMPARISON]].copy()
    gap, mismatch = _gap_and_mismatch(compared)
    regression = compute_fund_to_index_regression(
        fund,
        INDEX,
        MASTER,
        fund_name="Example Fund",
        master_timeseries="Lipper",
        quiet=True,
    )
    return {
        "selected_fund": ISIN,
        "selected": pd.Series(
            {
                "ISIN": ISIN,
                "Name": "Example Fund",
                "market_identifier": "EXMPX",
                "fund_wrapper": "mutual fund",
                "fund_type": "Active",
            }
        ),
        "fund_timeseries": fund,
        "index_column": INDEX,
        "master_timeseries": "Lipper",
        "comparison_timeseries": "Yahoo",
        "match_tolerance": TOLERANCE,
        "compared": compared,
        "master_column": MASTER,
        "comparison_column": COMPARISON,
        "gap": gap,
        "mismatch": mismatch,
        "regression_result": regression,
        "lipper_regression_comparison": pd.DataFrame({"Metric": ["Beta"]}),
        "consolidation_regression_comparison": pd.DataFrame({"Metric": ["Beta"]}),
        "date_check": None,
        "spike_return": 0.10,
        "reversal_band": 0.15,
        "scale_factor": 5,
        "scale_window": 12,
        "level_jump": 0.50,
        "index_gap": 0.05,
        "date_gap_days": 45,
        "output_dir": folder,
    }


if __name__ == "__main__":
    unittest.main()
