"""Run the Morocco Trade Intelligence pipeline.

Steps: extract (UN Comtrade API) -> bronze (typed JSON Lines) -> dbt build
(models + data tests) -> export (Parquet/CSV) -> report.

Examples:
    python run_pipeline.py                  # real data, years 2019-2025
    python run_pipeline.py --years 2022-2024
    python run_pipeline.py --offline        # synthetic API answers, no network
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from mti import __version__  # noqa: E402
from mti.bronze import build_bronze  # noqa: E402
from mti.comtrade import ComtradeClient  # noqa: E402
from mti.config import DEFAULT_YEARS, build_request_plan  # noqa: E402
from mti.export import export_marts  # noqa: E402
from mti.extract import run_extraction  # noqa: E402
from mti.fake_api import FakeComtradeSession  # noqa: E402
from mti.report import summarize_dbt, write_report  # noqa: E402

log = logging.getLogger("mti")
DBT_DIR = ROOT / "dbt"


def parse_years(text: str | None) -> list[int]:
    if not text:
        return DEFAULT_YEARS
    if "-" in text:
        start, end = (int(part) for part in text.split("-"))
        return list(range(start, end + 1))
    return [int(part) for part in text.split(",")]


def run_dbt(data_dir: Path) -> int:
    env = {**os.environ, "MTI_DATA_DIR": str(data_dir)}
    command = ["dbt", "build", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    log.info("running: %s", " ".join(command))
    try:
        return subprocess.run(command, env=env, cwd=ROOT).returncode
    except FileNotFoundError:
        log.error("dbt is not installed: run 'pip install -r requirements.txt' first")
        return 127


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="use synthetic API answers (tests only)")
    parser.add_argument("--years", help="e.g. 2019-2025 or 2023,2024")
    parser.add_argument("--data-dir", type=Path, help="output folder (default: data/, or build/offline/)")
    parser.add_argument("--skip-extract", action="store_true", help="reuse the existing raw files")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    data_dir = (args.data_dir or (ROOT / "build" / "offline" if args.offline else ROOT / "data")).resolve()
    years = parse_years(args.years)
    mode = "offline (synthetic data)" if args.offline else "online (UN Comtrade)"
    log.info("Morocco Trade Intelligence %s | mode: %s | years: %s", __version__, mode, years)

    extraction = None
    if not args.skip_extract:
        if args.offline:
            client = ComtradeClient(session=FakeComtradeSession(), pause_seconds=0)
        else:
            client = ComtradeClient()
        extraction = run_extraction(build_request_plan(years), data_dir / "raw", client)

    bronze_rows = build_bronze(data_dir / "raw", data_dir / "bronze")
    log.info("bronze: %d rows", bronze_rows)

    (data_dir / "warehouse").mkdir(parents=True, exist_ok=True)
    dbt_code = run_dbt(data_dir)
    candidates = [DBT_DIR / "target" / "run_results.json", ROOT / "target" / "run_results.json"]
    run_results = next((path for path in candidates if path.exists()), candidates[0])
    dbt_summary = summarize_dbt(run_results)

    exports = None
    if dbt_code == 0:
        exports = export_marts(data_dir / "warehouse" / "mti.duckdb", data_dir / "marts")

    extraction_summary = None
    if extraction is not None:
        by_dataset: dict[str, int] = {}
        for line in extraction:
            by_dataset[line["dataset"]] = by_dataset.get(line["dataset"], 0) + line["records"]
        extraction_summary = {
            "requests": len(extraction),
            "records_by_dataset": by_dataset,
            "empty_requests": [line["request_id"] for line in extraction if line["records"] == 0],
        }

    report = write_report(
        data_dir / "pipeline_report.json",
        version=__version__,
        mode=mode,
        years=years,
        status="success" if dbt_code == 0 else "failed",
        extraction=extraction_summary,
        bronze_rows=bronze_rows,
        dbt=dbt_summary,
        exports=exports,
    )
    log.info("status: %s | dbt: %s", report["status"], dbt_summary.get("status_counts"))
    return 0 if dbt_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
