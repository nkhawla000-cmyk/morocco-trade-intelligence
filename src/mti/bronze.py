"""Bronze step: flatten the raw JSON answers into one typed JSON Lines file.

Only the fields used downstream are kept, each with a fixed type, so that
DuckDB reads the same schema whatever the content of a given run. Lineage
columns (prefixed with "_") record where every row comes from.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

# API field -> type applied in the bronze file.
SCHEMA: dict[str, Callable[[Any], Any]] = {
    "typeCode": str,
    "freqCode": str,
    "refYear": int,
    "period": str,
    "reporterCode": int,
    "reporterISO": str,
    "reporterDesc": str,
    "flowCode": str,
    "flowDesc": str,
    "partnerCode": int,
    "partnerISO": str,
    "partnerDesc": str,
    "partner2Code": int,
    "customsCode": str,
    "motCode": int,
    "classificationCode": str,
    "cmdCode": str,
    "cmdDesc": str,
    "aggrLevel": int,
    "isLeaf": bool,
    "qtyUnitAbbr": str,
    "qty": float,
    "netWgt": float,
    "cifvalue": float,
    "fobvalue": float,
    "primaryValue": float,
    "isReported": bool,
    "isAggregate": bool,
}

BRONZE_FILE = "comtrade_records.jsonl"


def _cast(value: Any, kind: Callable[[Any], Any]) -> Any:
    if value is None or value == "":
        return None
    if kind is bool:
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1"}
        return bool(value)
    return kind(value)


def flatten_record(record: dict, envelope: dict, source_file: str) -> dict:
    row = {field: _cast(record.get(field), kind) for field, kind in SCHEMA.items()}
    row["_dataset"] = envelope["dataset"]
    row["_request_id"] = envelope["request_id"]
    row["_fetched_at"] = envelope["fetched_at"]
    row["_source_file"] = source_file
    return row


def build_bronze(raw_dir: Path, bronze_dir: Path) -> int:
    """Rewrite the bronze file from every raw answer; return the row count."""
    raw_dir, bronze_dir = Path(raw_dir), Path(bronze_dir)
    files = sorted(raw_dir.glob("*/*.json"))
    if not files:
        raise FileNotFoundError(f"no raw files found in {raw_dir}")
    bronze_dir.mkdir(parents=True, exist_ok=True)
    target = bronze_dir / BRONZE_FILE
    temporary = target.with_suffix(".tmp")
    rows = 0
    with temporary.open("w", encoding="utf-8") as out:
        for path in files:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            source_file = path.relative_to(raw_dir).as_posix()
            for record in envelope["data"]:
                out.write(json.dumps(flatten_record(record, envelope, source_file), ensure_ascii=False))
                out.write("\n")
                rows += 1
    temporary.replace(target)
    return rows
