"""Pipeline report: a JSON summary of what each run fetched, tested and exported."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def summarize_dbt(run_results: Path) -> dict:
    """Count dbt results by status and list tests that warned or failed."""
    if not run_results.exists():
        return {"available": False}
    results = json.loads(run_results.read_text(encoding="utf-8"))["results"]
    statuses = Counter(item["status"] for item in results)
    issues = [
        {"node": item["unique_id"], "status": item["status"], "failures": item.get("failures")}
        for item in results
        if item["status"] in {"warn", "fail", "error"}
    ]
    tests = [item for item in results if item["unique_id"].startswith("test.")]
    return {
        "available": True,
        "nodes": len(results),
        "tests": len(tests),
        "status_counts": dict(statuses),
        "issues": issues,
    }


def write_report(path: Path, **sections) -> dict:
    report = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **sections}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
