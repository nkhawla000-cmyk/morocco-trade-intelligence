"""Extraction step: call the API and keep each answer as a raw JSON file.

The run is all-or-nothing: files are written to a temporary folder that
replaces the previous raw snapshot only when every request has succeeded.
A failed run therefore never leaves a half-updated dataset behind.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .comtrade import ComtradeClient
from .config import ComtradeRequest

log = logging.getLogger(__name__)


def run_extraction(
    plan: list[ComtradeRequest], raw_dir: Path, client: ComtradeClient
) -> list[dict]:
    """Fetch every request of the plan and return one summary line per request."""
    raw_dir = Path(raw_dir)
    staging_dir = raw_dir.with_name(raw_dir.name + "_incoming")
    shutil.rmtree(staging_dir, ignore_errors=True)
    summaries = []
    for number, request in enumerate(plan, start=1):
        records = client.fetch(request)
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        envelope = {
            "request_id": request.request_id,
            "dataset": request.dataset,
            "year": request.year,
            "url": client.base_url,
            "params": request.params(),
            "fetched_at": fetched_at,
            "record_count": len(records),
            "data": records,
        }
        path = staging_dir / request.dataset / f"{request.request_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        summaries.append(
            {
                "request_id": request.request_id,
                "dataset": request.dataset,
                "year": request.year,
                "records": len(records),
            }
        )
        log.info("[%d/%d] %s: %d records", number, len(plan), request.request_id, len(records))
    shutil.rmtree(raw_dir, ignore_errors=True)
    staging_dir.rename(raw_dir)
    return summaries
