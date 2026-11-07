"""Export step: write the dbt tables used for reporting (Power BI, GitHub)."""

from __future__ import annotations

from pathlib import Path

# Star schema in Parquet (compact, typed); analytical marts in CSV (readable on GitHub).
EXPORTS = {
    "fct_trade": "parquet",
    "dim_country": "parquet",
    "dim_product": "parquet",
    "dim_flow": "parquet",
    "dim_year": "parquet",
    "mart_trade_overview": "csv",
    "mart_partner_shares": "csv",
    "mart_chapter_structure": "csv",
    "mart_concentration": "csv",
    "mart_mirror_gaps": "csv",
}


def export_marts(database: Path, out_dir: Path) -> dict[str, int]:
    """Copy each table to a file and return the row count per table."""
    import duckdb  # installed with dbt-duckdb

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    with duckdb.connect(str(database), read_only=True) as con:
        for table, file_format in EXPORTS.items():
            path = (out_dir / f"{table}.{file_format}").as_posix()
            options = "(FORMAT PARQUET)" if file_format == "parquet" else "(HEADER, DELIMITER ',')"
            con.execute(f"COPY (SELECT * FROM main.{table} ORDER BY ALL) TO '{path}' {options}")
            counts[table] = con.execute(f"SELECT count(*) FROM main.{table}").fetchone()[0]
    return counts
