# Airflow image with the project's own Python environment.
# Airflow only orchestrates: every task runs run_pipeline.py with the Python
# of /opt/mti-venv, so dbt and the data libraries never conflict with
# Airflow's own dependencies.
FROM apache/airflow:2.10.5-python3.12

USER root
COPY requirements.txt /tmp/mti-requirements.txt
RUN python -m venv /opt/mti-venv \
    && /opt/mti-venv/bin/pip install --no-cache-dir -r /tmp/mti-requirements.txt \
    && chown -R airflow:root /opt/mti-venv
USER airflow
