from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline_config import POWERBI_EXPORTS, PROJECT_ROOT
from pipeline_utils import require_file

DATABASE_FILE = PROJECT_ROOT / "database" / "logistics.duckdb"
OUTPUT_DIR = PROJECT_ROOT / "data" / "powerbi"
EXPORTS = POWERBI_EXPORTS


def sql_path(path):
    """Return a safely quoted path for a DuckDB SQL string literal."""
    return path.resolve().as_posix().replace("'", "''")


def export_powerbi_files(
    database_file=DATABASE_FILE,
    output_dir=OUTPUT_DIR,
    exports=EXPORTS,
):
    import duckdb

    database_file = require_file(database_file, "Database")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_rows = []

    print(f"Exporting Power BI datasets to:\n{output_dir}\n")

    with TemporaryDirectory(prefix=".powerbi-", dir=output_dir) as temp_dir:
        staging_dir = Path(temp_dir)
        staged_outputs = []
        connection = duckdb.connect(str(database_file), read_only=True)

        try:
            for source_name, file_name in exports:
                output_file = output_dir / file_name
                temporary_file = staging_dir / file_name

                source_count = connection.execute(
                    f"SELECT COUNT(*) FROM {source_name}"
                ).fetchone()[0]
                source_columns = tuple(
                    row[0]
                    for row in connection.execute(
                        f"DESCRIBE SELECT * FROM {source_name}"
                    ).fetchall()
                )

                connection.execute(
                    f"""
                    COPY (SELECT * FROM {source_name})
                    TO '{sql_path(temporary_file)}'
                    (FORMAT PARQUET, COMPRESSION ZSTD)
                    """
                )

                export_count = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM READ_PARQUET('{sql_path(temporary_file)}')
                    """
                ).fetchone()[0]
                export_columns = tuple(
                    row[0]
                    for row in connection.execute(
                        "DESCRIBE SELECT * FROM READ_PARQUET("
                        f"'{sql_path(temporary_file)}')"
                    ).fetchall()
                )

                if export_count != source_count:
                    raise RuntimeError(
                        f"Row-count mismatch for {source_name}: "
                        f"source={source_count:,}, export={export_count:,}"
                    )
                if export_columns != source_columns:
                    raise RuntimeError(
                        f"Column-order mismatch for {source_name}."
                    )

                staged_outputs.append((temporary_file, output_file))
                validation_rows.append(
                    (
                        source_name,
                        file_name,
                        source_count,
                        temporary_file.stat().st_size,
                    )
                )
        finally:
            connection.close()

        for temporary_file, output_file in staged_outputs:
            temporary_file.replace(output_file)

    print("Power BI export validation:")
    print("-" * 92)
    print(f"{'DuckDB source':34} {'Rows':>12} {'Size (MB)':>12}  File")
    print("-" * 92)

    for source_name, file_name, row_count, file_size in validation_rows:
        print(
            f"{source_name:34} {row_count:12,} "
            f"{file_size / (1024 * 1024):12.2f}  {file_name}"
        )

    print("-" * 92)
    print(f"Validated files: {len(validation_rows)}")
    print("Power BI Parquet exports completed successfully.")


if __name__ == "__main__":
    export_powerbi_files()
