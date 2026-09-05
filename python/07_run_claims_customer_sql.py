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
    / "04_stage_claims_customer.sql"
)


def run_sql(database_file=DATABASE_FILE, sql_file=SQL_FILE):
    sql_file = require_file(sql_file, "SQL file")
    sql = sql_file.read_text(encoding="utf-8")

    with duckdb_transaction(database_file) as connection:
        print(
            "Staging claims, CRM tickets "
            "and CSAT responses..."
        )
        connection.execute(sql)
        results = connection.execute(
            """
            SELECT metric, metric_value
            FROM quality.customer_impact_summary
            """
        ).fetchall()

    print()
    print("Customer-impact quality summary:")
    print("-" * 60)

    for metric, value in results:
        print(f"{metric}: {value:,}")

    print()
    print(
        "Claims and customer-impact staging "
        "completed successfully."
    )


if __name__ == "__main__":
    run_sql()
