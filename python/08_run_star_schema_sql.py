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
    / "05_build_star_schema.sql"
)


def run_sql(database_file=DATABASE_FILE, sql_file=SQL_FILE):
    sql_file = require_file(sql_file, "SQL file")
    sql = sql_file.read_text(encoding="utf-8")

    with duckdb_transaction(database_file) as connection:
        print("Building star schema...")
        connection.execute(sql)
        results = connection.execute(
            """
            SELECT metric, metric_value
            FROM quality.star_schema_summary
            """
        ).fetchall()

    print()
    print("Star-schema quality summary:")
    print("-" * 60)

    for metric, value in results:
        print(f"{metric}: {value:,}")

    print()
    print("Star schema completed successfully.")


if __name__ == "__main__":
    run_sql()
