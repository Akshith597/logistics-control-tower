"""Validate the materialized database and Power BI export contracts."""

import csv
from pathlib import Path

from pipeline_config import (
    POWERBI_EXPORTS,
    PROCESSED_TABLES,
    PROJECT_ROOT,
    REPORT_DIR,
)
from pipeline_utils import file_sha256, require_file, require_named_files

DATABASE_FILE = PROJECT_ROOT / "database" / "logistics.duckdb"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
POWERBI_DIR = PROJECT_ROOT / "data" / "powerbi"
VALIDATION_SQL_FILE = PROJECT_ROOT / "sql" / "07_validate_model.sql"

DIMENSION_KEYS = {
    "dim_date": ("date_key", "ship_date"),
    "dim_customer": ("customer_key", "customer_key"),
    "dim_carrier": ("carrier_key", "carrier_key"),
    "dim_warehouse": ("warehouse_key", "warehouse_key"),
    "dim_service": ("service_key", "service_key"),
    "dim_lane": ("lane_key", "lane_key"),
}


def sql_path(path):
    return Path(path).resolve().as_posix().replace("'", "''")


def sql_validation_checks(rows):
    """Convert validation-query rows into named pass/fail conditions."""
    checks = [(
        "model validation SQL returned checks",
        bool(rows),
        "sql/07_validate_model.sql returned no rows",
    )]
    checks.extend(
        (
            f"SQL [{severity}] {test_name}",
            validation_status == "PASS" and failure_count == 0,
            (
                f"status={validation_status}, "
                f"failure_count={failure_count}"
            ),
        )
        for test_name, severity, failure_count, validation_status in rows
    )
    return checks


def validate_pipeline(
    database_file=DATABASE_FILE,
    processed_dir=PROCESSED_DIR,
    powerbi_dir=POWERBI_DIR,
    report_dir=REPORT_DIR,
    validation_sql_file=VALIDATION_SQL_FILE,
):
    """Run cross-layer checks and raise once with every observed failure."""
    import duckdb

    database_file = require_file(database_file, "Database")
    processed_paths = require_named_files(
        processed_dir,
        PROCESSED_TABLES,
        suffix=".parquet",
    )
    export_paths = {
        source_name: require_file(
            Path(powerbi_dir) / file_name,
            "Power BI export",
        )
        for source_name, file_name in POWERBI_EXPORTS
    }

    required_reports = (
        "extraction_manifest.csv",
        "table_profile.csv",
        "column_profile.csv",
        "duplicate_keys.csv",
        "data_quality_issues.csv",
    )
    report_paths = require_named_files(report_dir, required_reports)
    validation_sql_file = require_file(
        validation_sql_file,
        "Model validation SQL",
    )
    validation_sql = validation_sql_file.read_text(encoding="utf-8")
    failures = []
    passed = []

    def check(name, condition, detail=""):
        if condition:
            passed.append(name)
        else:
            failures.append(f"{name}: {detail or 'condition was false'}")

    connection = duckdb.connect(str(database_file), read_only=True)
    try:
        for parquet_path in processed_paths:
            table_name = parquet_path.stem
            parquet_count = connection.execute(
                f"SELECT COUNT(*) FROM read_parquet('{sql_path(parquet_path)}')"
            ).fetchone()[0]
            raw_count = connection.execute(
                f"SELECT COUNT(*) FROM raw.{table_name}"
            ).fetchone()[0]
            metadata = connection.execute(
                """
                SELECT
                    source_file,
                    row_count,
                    column_count,
                    source_bytes,
                    source_sha256
                FROM quality.raw_table_counts
                WHERE table_name = ?
                """,
                [table_name],
            ).fetchone()
            parquet_column_count = len(
                connection.execute(
                    "DESCRIBE SELECT * FROM read_parquet("
                    f"'{sql_path(parquet_path)}')"
                ).fetchall()
            )
            check(
                f"raw.{table_name} row count",
                raw_count == parquet_count,
                f"database={raw_count:,}, parquet={parquet_count:,}",
            )
            expected_metadata = (
                parquet_path.name,
                parquet_count,
                parquet_column_count,
                parquet_path.stat().st_size,
                file_sha256(parquet_path),
            )
            check(
                f"raw.{table_name} source lineage",
                metadata == expected_metadata,
                "load metadata does not match the current Parquet file",
            )

        fact_count = connection.execute(
            "SELECT COUNT(*) FROM mart.fact_shipment"
        ).fetchone()[0]
        fact_unique_count = connection.execute(
            "SELECT COUNT(DISTINCT shipment_key) FROM mart.fact_shipment"
        ).fetchone()[0]
        fact_null_keys = connection.execute(
            """
            SELECT COUNT(*)
            FROM mart.fact_shipment
            WHERE shipment_key IS NULL
            """
        ).fetchone()[0]
        check(
            "fact_shipment primary key",
            fact_count == fact_unique_count and fact_null_keys == 0,
            (
                f"rows={fact_count:,}, unique={fact_unique_count:,}, "
                f"null={fact_null_keys:,}"
            ),
        )

        for dimension_name, (
            key_column,
            fact_key_column,
        ) in DIMENSION_KEYS.items():
            row_count, unique_count, null_count = connection.execute(
                f"""
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT {key_column}),
                    COUNT(*) FILTER (WHERE {key_column} IS NULL)
                FROM mart.{dimension_name}
                """
            ).fetchone()
            check(
                f"{dimension_name} primary key",
                row_count == unique_count and null_count == 0,
                (
                    f"rows={row_count:,}, unique={unique_count:,}, "
                    f"null={null_count:,}"
                ),
            )

            # A missing shipment date is a governed data-quality condition,
            # not an orphaned dimension key. Other model relationships use
            # explicit UNKNOWN members and therefore remain non-nullable.
            nullable_fact_key_filter = (
                f"AND fact.{fact_key_column} IS NOT NULL"
                if dimension_name == "dim_date"
                else ""
            )
            missing_foreign_keys = connection.execute(
                f"""
                SELECT COUNT(*)
                FROM mart.fact_shipment AS fact
                LEFT JOIN mart.{dimension_name} AS dimension
                  ON fact.{fact_key_column} = dimension.{key_column}
                WHERE dimension.{key_column} IS NULL
                  {nullable_fact_key_filter}
                """
            ).fetchone()[0]
            check(
                f"fact_shipment to {dimension_name}",
                missing_foreign_keys == 0,
                f"unmatched foreign keys={missing_foreign_keys:,}",
            )

        executive_total = connection.execute(
            "SELECT total_shipments FROM mart.vw_executive_kpis"
        ).fetchone()[0]
        monthly_total = connection.execute(
            "SELECT SUM(total_shipments) FROM mart.vw_monthly_performance"
        ).fetchone()[0]
        check(
            "KPI shipment reconciliation",
            executive_total == fact_count == monthly_total,
            (
                f"fact={fact_count:,}, executive={executive_total:,}, "
                f"monthly={monthly_total:,}"
            ),
        )

        sql_validation_rows = connection.execute(validation_sql).fetchall()
        for validation_check in sql_validation_checks(sql_validation_rows):
            check(*validation_check)

        for source_name, export_path in export_paths.items():
            source_count = connection.execute(
                f"SELECT COUNT(*) FROM {source_name}"
            ).fetchone()[0]
            export_count = connection.execute(
                f"SELECT COUNT(*) FROM read_parquet('{sql_path(export_path)}')"
            ).fetchone()[0]
            source_columns = tuple(
                row[0]
                for row in connection.execute(
                    f"DESCRIBE SELECT * FROM {source_name}"
                ).fetchall()
            )
            export_columns = tuple(
                row[0]
                for row in connection.execute(
                    "DESCRIBE SELECT * FROM read_parquet("
                    f"'{sql_path(export_path)}')"
                ).fetchall()
            )
            check(
                f"{export_path.name} contract",
                source_count == export_count
                and source_columns == export_columns,
                (
                    f"source rows={source_count:,}, export rows={export_count:,}, "
                    f"schema match={source_columns == export_columns}"
                ),
            )
    finally:
        connection.close()

    for report_path in report_paths:
        with report_path.open("r", encoding="utf-8-sig", newline="") as file:
            header = next(csv.reader(file), [])
        check(
            f"{report_path.name} header",
            bool(header),
            "report has no header row",
        )

    if failures:
        formatted_failures = "\n".join(
            f"  - {failure}" for failure in failures
        )
        raise RuntimeError(
            "Pipeline validation failed:\n" + formatted_failures
        )

    print("=" * 68)
    print("PIPELINE VALIDATION PASSED")
    print("=" * 68)
    print(f"Checks passed: {len(passed)}")
    print(f"Raw tables: {len(processed_paths)}")
    print(f"Power BI exports: {len(export_paths)}")
    print(f"Fact shipments: {fact_count:,}")
    return passed


if __name__ == "__main__":
    validate_pipeline()
