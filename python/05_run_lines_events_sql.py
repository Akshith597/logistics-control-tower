"""Stage shipment lines and deduplicated carrier tracking events."""

from pathlib import Path

from pipeline_config import PROJECT_ROOT
from pipeline_utils import duckdb_transaction, require_file

DATABASE_FILE = PROJECT_ROOT / "database" / "logistics.duckdb"
SQL_FILE = PROJECT_ROOT / "sql" / "02_stage_lines_events.sql"


def run_sql(
    database_file: Path = DATABASE_FILE,
    sql_file: Path = SQL_FILE,
) -> None:
    sql_file = require_file(sql_file, "SQL file")
    sql = sql_file.read_text(encoding="utf-8")

    with duckdb_transaction(database_file) as connection:
        print("Staging shipment lines and tracking events...")
        connection.execute(sql)
        results = connection.execute(
            """
            SELECT metric, metric_value
            FROM quality.line_event_summary
            """
        ).fetchall()

    print()
    print("Line and event quality summary:")
    print("-" * 60)

    for metric, value in results:
        print(f"{metric}: {value:,}")

    print()
    print("Line and event staging completed successfully.")


if __name__ == "__main__":
    run_sql()
