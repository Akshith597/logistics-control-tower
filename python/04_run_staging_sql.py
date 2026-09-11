"""Create the DuckDB staging layer from the raw tables."""

from pathlib import Path

from pipeline_config import PROJECT_ROOT
from pipeline_utils import duckdb_transaction, require_file

DATABASE_FILE = PROJECT_ROOT / "database" / "logistics.duckdb"
SQL_FILE = PROJECT_ROOT / "sql" / "01_create_staging.sql"


def run_sql(
    database_file: Path = DATABASE_FILE,
    sql_file: Path = SQL_FILE,
) -> None:
    sql_file = require_file(sql_file, "SQL file")
    sql = sql_file.read_text(encoding="utf-8")

    with duckdb_transaction(database_file) as connection:
        print("Running staging SQL...")
        connection.execute(sql)

        results = connection.execute(
            """
            SELECT table_name, row_count
            FROM quality.staging_table_counts
            ORDER BY table_name
            """
        ).fetchall()

        shipment_summary = connection.execute(
            """
            SELECT
                COUNT(*) AS total_shipment_rows,
                COUNT(*) FILTER (
                    WHERE final_live_shipment_flag = TRUE
                ) AS final_live_shipments,
                COUNT(*) FILTER (
                    WHERE official_kpi_eligible_flag = TRUE
                ) AS official_kpi_shipments,
                COUNT(*) FILTER (
                    WHERE final_on_time_flag IS NULL
                ) AS missing_on_time_result
            FROM staging.stg_shipments
            """
        ).fetchone()

    print()
    print("Staging tables created:")
    for table_name, row_count in results:
        print(f"  {table_name}: {row_count:,} rows")

    print()
    print("Shipment staging summary:")
    print(f"  Total rows: {shipment_summary[0]:,}")
    print(f"  Final live: {shipment_summary[1]:,}")
    print(f"  KPI eligible: {shipment_summary[2]:,}")
    print(f"  Missing on-time result: {shipment_summary[3]:,}")

    print()
    print("Staging SQL completed successfully.")


if __name__ == "__main__":
    run_sql()
