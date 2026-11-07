"""Monthly refresh of the Morocco Trade Intelligence pipeline.

One Airflow task per pipeline step: extract -> bronze -> dbt -> segment ->
export -> report. Each task runs run_pipeline.py in the project's own virtual
environment, so every step can also be run by hand with the same command.
Only the extraction is retried: it is the only step that depends on an
external service (the UN Comtrade API).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator

PROJECT_DIR = os.environ.get("MTI_PROJECT_DIR", "/opt/mti")
PYTHON = os.environ.get("MTI_PYTHON", "/opt/mti-venv/bin/python")


def pipeline_step(step: str, **kwargs) -> BashOperator:
    command = (
        f"cd {PROJECT_DIR} && {PYTHON} run_pipeline.py --steps {step}"
        " --years {{ params.years }}"
        " {{ '--offline' if params.offline else '' }}"
    )
    return BashOperator(task_id=step, bash_command=command, **kwargs)


with DAG(
    dag_id="morocco_trade_intelligence",
    description="UN Comtrade -> bronze -> dbt (DuckDB) -> segmentation -> exports",
    schedule="17 4 7 * *",  # 7th of each month, 04:17 UTC
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "khaoula", "retries": 0},
    params={
        "years": Param("2019-2025", type="string", description="Years to load, e.g. 2019-2025"),
        "offline": Param(False, type="boolean", description="Synthetic API answers (tests only)"),
    },
    tags=["comtrade", "dbt", "duckdb"],
    doc_md=__doc__,
) as dag:
    extract = pipeline_step("extract", retries=3, retry_delay=timedelta(minutes=10))
    bronze = pipeline_step("bronze")
    dbt_build = pipeline_step("dbt")
    segment = pipeline_step("segment")
    export = pipeline_step("export")
    report = pipeline_step("report")

    extract >> bronze >> dbt_build >> segment >> export >> report
