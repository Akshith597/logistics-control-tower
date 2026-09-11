"""Stage warehouse activity and reconcile invoices to shipments."""

from pathlib import Path

from pipeline_config import PROJECT_ROOT
from pipeline_utils import duckdb_transaction, require_file

DATABASE_FILE = (
    PROJECT_ROOT
    / "database"
    / "logistics.duckdb"
)

SQL_FILE = (
    PROJECT_ROOT
    / "sql"
    / "03_stage_wms_invoices.sql"
)


def run_sql(
    database_file: Path = DATABASE_FILE,
    sql_file: Path = SQL_FILE,
) -> None:
    sql_file = require_file(sql_file, "SQL file")
    sql = sql_file.read_text(encoding="utf-8")

    with duckdb_transaction(database_file) as connection:
        print("Staging WMS and invoice data...")
        connection.execute(sql)
        results = connection.execute(
            """
            SELECT metric, metric_value
            FROM quality.wms_invoice_summary
            """
        ).fetchall()

    print()
    print("WMS and invoice quality summary:")
    print("-" * 60)

    for metric, value in results:
        print(f"{metric}: {value:,}")

    print()
    print(
        "WMS and invoice staging "
        "completed successfully."
    )


if __name__ == "__main__":
    run_sql()
