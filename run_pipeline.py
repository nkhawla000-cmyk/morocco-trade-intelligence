"""Run the Morocco Trade Intelligence pipeline.

Steps, in order:
  extract  UN Comtrade API -> raw JSON files (all-or-nothing snapshot)
  bronze   raw JSON -> one typed JSON Lines file with lineage columns
  dbt      dbt build: staging, star schema, analytical marts and data tests
  segment  k-means segmentation of partner countries (scikit-learn)
  export   star schema to Parquet, analytical tables to CSV
  report   data/pipeline_report.json

Examples:
    python run_pipeline.py                     # every step, real data, 2019-2025
    python run_pipeline.py --years 2022-2024
    python run_pipeline.py --offline           # synthetic API answers, no network
    python run_pipeline.py --steps dbt,export  # selected steps (used by Airflow)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mti import __version__  # noqa: E402
from mti.bronze import BRONZE_FILE, build_bronze  # noqa: E402
from mti.comtrade import ComtradeClient  # noqa: E402
from mti.config import DEFAULT_YEARS, build_request_plan  # noqa: E402
from mti.export import export_marts  # noqa: E402
from mti.extract import run_extraction  # noqa: E402
from mti.fake_api import FakeComtradeSession  # noqa: E402
from mti.report import summarize_dbt, write_report  # noqa: E402

log = logging.getLogger("mti")
DBT_DIR = ROOT / "dbt"
STEPS = ["extract", "bronze", "dbt", "segment", "export", "report"]


class StepFailed(RuntimeError):
    pass


def parse_years(text: str | None) -> list[int]:
    if not text:
        return DEFAULT_YEARS
    if "-" in text:
        start, end = (int(part) for part in text.split("-"))
        return list(range(start, end + 1))
    return [int(part) for part in text.split(",")]


def dbt_executable() -> str:
    """dbt installed next to this Python (virtual environment), else on PATH."""
    candidate = Path(sys.executable).with_name("dbt")
    return str(candidate) if candidate.exists() else "dbt"


def run_results_path() -> Path:
    candidates = [DBT_DIR / "target" / "run_results.json", ROOT / "target" / "run_results.json"]
    return next((path for path in candidates if path.exists()), candidates[0])


def read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")


# --- steps -----------------------------------------------------------------

def step_extract(ctx: dict) -> None:
    client = ComtradeClient(session=FakeComtradeSession(), pause_seconds=0) if ctx["offline"] else ComtradeClient()
    lines = run_extraction(build_request_plan(ctx["years"]), ctx["data_dir"] / "raw", client)
    by_dataset: dict[str, int] = {}
    for line in lines:
        by_dataset[line["dataset"]] = by_dataset.get(line["dataset"], 0) + line["records"]
    write_json(
        ctx["data_dir"] / "state" / "extraction.json",
        {
            "requests": len(lines),
            "records_by_dataset": by_dataset,
            "empty_requests": [line["request_id"] for line in lines if line["records"] == 0],
        },
    )


def step_bronze(ctx: dict) -> None:
    rows = build_bronze(ctx["data_dir"] / "raw", ctx["data_dir"] / "bronze")
    log.info("bronze: %d rows", rows)


def step_dbt(ctx: dict) -> None:
    (ctx["data_dir"] / "warehouse").mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "MTI_DATA_DIR": str(ctx["data_dir"])}
    command = [dbt_executable(), "build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    log.info("running: %s", " ".join(command))
    try:
        code = subprocess.run(command, env=env, cwd=ROOT).returncode
    except FileNotFoundError as exc:
        raise StepFailed("dbt is not installed: run 'pip install -r requirements.txt'") from exc
    if code != 0:
        raise StepFailed(f"dbt build failed (exit code {code})")


def step_segment(ctx: dict) -> None:
    from mti.segmentation import run_segmentation

    summary = run_segmentation(ctx["data_dir"] / "warehouse" / "mti.duckdb")
    write_json(ctx["data_dir"] / "state" / "segmentation.json", summary)
    log.info("segmentation: %s", summary)


def step_export(ctx: dict) -> None:
    counts = export_marts(ctx["data_dir"] / "warehouse" / "mti.duckdb", ctx["data_dir"] / "marts")
    write_json(ctx["data_dir"] / "state" / "exports.json", counts)


def step_report(ctx: dict) -> None:
    data_dir = ctx["data_dir"]
    dbt_summary = summarize_dbt(run_results_path())
    dbt_ok = dbt_summary.get("available") and not any(
        issue["status"] in {"fail", "error"} for issue in dbt_summary.get("issues", [])
    )
    status = "success" if dbt_ok and not ctx["failed_steps"] else "failed"
    bronze_file = data_dir / "bronze" / BRONZE_FILE
    bronze_rows = sum(1 for _ in bronze_file.open(encoding="utf-8")) if bronze_file.exists() else None
    report = write_report(
        data_dir / "pipeline_report.json",
        version=__version__,
        mode="offline (synthetic data)" if ctx["offline"] else "online (UN Comtrade)",
        years=ctx["years"],
        status=status,
        failed_steps=ctx["failed_steps"],
        extraction=read_json(data_dir / "state" / "extraction.json"),
        bronze_rows=bronze_rows,
        dbt=dbt_summary,
        segmentation=read_json(data_dir / "state" / "segmentation.json"),
        exports=read_json(data_dir / "state" / "exports.json") if status == "success" else None,
    )
    log.info("status: %s | dbt: %s", report["status"], dbt_summary.get("status_counts"))


STEP_FUNCTIONS = {
    "extract": step_extract,
    "bronze": step_bronze,
    "dbt": step_dbt,
    "segment": step_segment,
    "export": step_export,
    "report": step_report,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="use synthetic API answers (tests only)")
    parser.add_argument("--years", help="e.g. 2019-2025 or 2023,2024")
    parser.add_argument("--data-dir", type=Path, help="output folder (default: data/, or build/offline/)")
    parser.add_argument("--steps", help=f"comma-separated subset of: {','.join(STEPS)}")
    parser.add_argument("--skip-extract", action="store_true", help="reuse the existing raw files")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_dir = (args.data_dir or (ROOT / "build" / "offline" if args.offline else ROOT / "data")).resolve()
    selected = args.steps.split(",") if args.steps else list(STEPS)
    unknown = set(selected) - set(STEPS)
    if unknown:
        parser.error(f"unknown step(s): {', '.join(sorted(unknown))}")
    if args.skip_extract and "extract" in selected:
        selected.remove("extract")
    ctx = {"offline": args.offline, "years": parse_years(args.years), "data_dir": data_dir, "failed_steps": []}
    log.info("Morocco Trade Intelligence %s | steps: %s | years: %s", __version__, ",".join(selected), ctx["years"])

    full_run = args.steps is None
    for name in [step for step in STEPS if step in selected]:
        if ctx["failed_steps"] and name != "report":
            log.warning("skipping %s after a failed step", name)
            continue
        try:
            STEP_FUNCTIONS[name](ctx)
        except Exception as exc:  # a full run still writes its report
            log.error("%s failed: %s", name, exc, exc_info=not isinstance(exc, StepFailed))
            ctx["failed_steps"].append(name)
            if not full_run:
                return 1
    return 1 if ctx["failed_steps"] else 0


if __name__ == "__main__":
    sys.exit(main())
