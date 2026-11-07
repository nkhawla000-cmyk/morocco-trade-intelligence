import json

import pytest

from mti.bronze import BRONZE_FILE, build_bronze
from mti.comtrade import ComtradeClient, ComtradeError
from mti.config import build_request_plan
from mti.extract import run_extraction
from mti.fake_api import FakeComtradeSession, FakeResponse

YEARS = [2023, 2024]


def offline_client(session=None):
    return ComtradeClient(session=session or FakeComtradeSession(), pause_seconds=0, sleep=lambda s: None)


def test_extraction_writes_one_file_per_request(tmp_path):
    plan = build_request_plan(YEARS)
    summaries = run_extraction(plan, tmp_path / "raw", offline_client())
    files = list((tmp_path / "raw").glob("*/*.json"))
    assert len(files) == len(plan) == len(summaries)
    envelope = json.loads(files[0].read_text(encoding="utf-8"))
    assert envelope["record_count"] == len(envelope["data"])


def test_bronze_rows_match_raw_records_and_carry_lineage(tmp_path):
    summaries = run_extraction(build_request_plan(YEARS), tmp_path / "raw", offline_client())
    rows = build_bronze(tmp_path / "raw", tmp_path / "bronze")
    assert rows == sum(line["records"] for line in summaries)
    first = json.loads((tmp_path / "bronze" / BRONZE_FILE).read_text(encoding="utf-8").splitlines()[0])
    assert {"_dataset", "_request_id", "_fetched_at", "_source_file"} <= set(first)
    assert isinstance(first["reporterCode"], int) and isinstance(first["cmdCode"], str)


def test_bronze_is_idempotent(tmp_path):
    run_extraction(build_request_plan(YEARS), tmp_path / "raw", offline_client())
    build_bronze(tmp_path / "raw", tmp_path / "bronze")
    first = (tmp_path / "bronze" / BRONZE_FILE).read_text(encoding="utf-8")
    build_bronze(tmp_path / "raw", tmp_path / "bronze")
    assert (tmp_path / "bronze" / BRONZE_FILE).read_text(encoding="utf-8") == first


class FailingSession(FakeComtradeSession):
    """Answers normally, then fails with a client error on the given call."""

    def __init__(self, fail_on_call):
        super().__init__()
        self.fail_on_call = fail_on_call

    def get(self, url, params, timeout=0):
        if len(self.calls) + 1 == self.fail_on_call:
            self.calls.append(dict(params))
            return FakeResponse({}, status_code=400)
        return super().get(url, params, timeout)


def test_failed_run_keeps_previous_snapshot(tmp_path):
    plan = build_request_plan(YEARS)
    run_extraction(plan, tmp_path / "raw", offline_client())
    before = sorted(p.name for p in (tmp_path / "raw").glob("*/*.json"))
    with pytest.raises(ComtradeError):
        run_extraction(plan, tmp_path / "raw", offline_client(FailingSession(fail_on_call=3)))
    after = sorted(p.name for p in (tmp_path / "raw").glob("*/*.json"))
    assert after == before
