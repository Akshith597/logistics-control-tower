import re

from pipeline_config import PROCESSED_TABLES, PROJECT_ROOT
from pipeline_utils import (
    duckdb_transaction,
    file_sha256,
    require_named_files,
)

PARQUET_FOLDER = PROJECT_ROOT / "data" / "processed"
DATABASE_FOLDER = PROJECT_ROOT / "database"
DATABASE_FILE = DATABASE_FOLDER / "logistics.duckdb"


def valid_table_name(value):
    """Allow only safe SQL table names."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise ValueError(f"Invalid table name: {value}")

    return value


def load_database(
    parquet_folder=PARQUET_FOLDER,
    database_file=DATABASE_FILE,
    table_names=PROCESSED_TABLES,
):
    parquet_files = require_named_files(
        parquet_folder,
        table_names,
        suffix=".parquet",
    )

    print("=" * 60)
    print("LOADING LOGISTICS SQL DATABASE")
    print("=" * 60)
    print(f"Database: {database_file}")
    print()

    with duckdb_transaction(database_file, must_exist=False) as connection:
        for schema_name in ("raw", "staging", "mart", "quality"):
            connection.execute(
                f"CREATE SCHEMA IF NOT EXISTS {schema_name}"
            )

        load_results = []

        for parquet_file in parquet_files:
            table_name = valid_table_name(parquet_file.stem)
            parquet_path = (
                str(parquet_file)
                .replace("\\", "/")
                .replace("'", "''")
            )
            print(f"Loading raw.{table_name}...")

            connection.execute(
                f"""
                CREATE OR REPLACE TABLE raw.{table_name} AS
                SELECT *
                FROM read_parquet('{parquet_path}')
                """
            )

            row_count = connection.execute(
                f"SELECT COUNT(*) FROM raw.{table_name}"
            ).fetchone()[0]
            column_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'raw'
                  AND table_name = ?
                """,
                [table_name],
            ).fetchone()[0]

            load_results.append((
                table_name,
                parquet_file.name,
                row_count,
                column_count,
                parquet_file.stat().st_size,
                file_sha256(parquet_file),
            ))
            print(
                f"  Completed: {row_count:,} rows, "
                f"{column_count} columns"
            )

        connection.execute(
            """
            CREATE OR REPLACE TABLE quality.raw_table_counts (
                table_name VARCHAR,
                source_file VARCHAR,
                row_count BIGINT,
                column_count INTEGER,
                source_bytes BIGINT,
                source_sha256 VARCHAR
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO quality.raw_table_counts
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            load_results,
        )

        total_rows = connection.execute(
            "SELECT SUM(row_count) FROM quality.raw_table_counts"
        ).fetchone()[0]
        results = connection.execute(
            """
            SELECT table_name, row_count, column_count
            FROM quality.raw_table_counts
            ORDER BY table_name
            """
        ).fetchall()

    print()
    print("Loaded tables:")
    for table_name, row_count, column_count in results:
        print(
            f"  raw.{table_name}: "
            f"{row_count:,} rows, "
            f"{column_count} columns"
        )

    print()
    print("=" * 60)
    print("DATABASE LOAD COMPLETED")
    print("=" * 60)
    print(f"Tables loaded: {len(load_results)}")
    print(f"Total rows: {total_rows:,}")
    print(f"Database saved to: {database_file}")


if __name__ == "__main__":
    load_database()
