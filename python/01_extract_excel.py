from datetime import datetime
import gc
import numbers
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import time

import pandas as pd

from pipeline_config import PROJECT_ROOT, SHEET_TABLE_PAIRS
from pipeline_utils import atomic_csv

INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "Logistical_Data.xlsx"
OUTPUT_FOLDER = PROJECT_ROOT / "data" / "processed"
REPORT_FOLDER = PROJECT_ROOT / "reports"


def to_snake_case(value):
    """Convert a column name into lowercase snake_case."""
    value = str(value).strip()
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    return value.strip("_").lower()


def normalize_columns(columns):
    """Normalize headers and reject blanks or collisions before extraction."""
    normalized = [to_snake_case(column) for column in columns]
    blank_columns = [
        str(original)
        for original, column in zip(columns, normalized, strict=True)
        if not column
    ]
    duplicate_columns = sorted({
        column
        for column in normalized
        if normalized.count(column) > 1
    })

    if blank_columns:
        raise ValueError(
            "Column names cannot normalize to an empty value: "
            + ", ".join(blank_columns)
        )
    if duplicate_columns:
        raise ValueError(
            "Column names collide after snake_case normalization: "
            + ", ".join(duplicate_columns)
        )

    return normalized


def should_be_text(column):
    """Identify columns that should remain text."""
    text_patterns = [
        "_id",
        "_code",
        "_number",
        "_postal",
        "_state",
        "_country",
        "_email",
        "_name",
        "_status",
        "_type",
        "_mode",
        "_currency",
        "_description",
        "_reason",
        "_notes",
        "_subject",
        "_comment",
        "_address",
    ]

    exact_text_columns = {
        "column1",
        "sku",
        "scac",
        "channel",
        "severity",
        "source",
        "source_system",
        "row_hash",
        "customer_po",
    }

    return (
        column in exact_text_columns
        or any(pattern in column for pattern in text_patterns)
    )


def preserve_text_columns(dataframe):
    """Prevent business identifiers from becoming numeric values."""
    def text_value(value):
        if pd.isna(value):
            return pd.NA
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, numbers.Integral):
            return str(value)
        if isinstance(value, numbers.Real) and float(value).is_integer():
            return str(int(value))
        return str(value)

    for column in dataframe.columns:
        if should_be_text(column):
            dataframe[column] = (
                dataframe[column]
                .map(text_value)
                .astype("string")
            )

    return dataframe


def extract_workbook(
    input_file=INPUT_FILE,
    output_folder=OUTPUT_FOLDER,
    report_folder=REPORT_FOLDER,
):
    input_file = Path(input_file).resolve()
    output_folder = Path(output_folder).resolve()
    report_folder = Path(report_folder).resolve()

    if not input_file.is_file():
        raise FileNotFoundError(
            f"Source workbook was not found:\n{input_file}\n"
            "For a self-contained demo, run:\n"
            "python python/00_generate_demo_data.py"
        )

    output_folder.mkdir(parents=True, exist_ok=True)
    report_folder.mkdir(parents=True, exist_ok=True)

    manifest = []
    pipeline_start = time.time()

    print("=" * 60)
    print("LOGISTICS DATA EXTRACTION")
    print("=" * 60)
    print(f"Source: {input_file}")
    print(f"Started: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print()

    # ExcelFile opens the large workbook once instead of reopening
    # it separately for every sheet.
    with TemporaryDirectory(
        prefix=".extract-",
        dir=output_folder.parent,
    ) as temporary_directory:
        staging_folder = Path(temporary_directory)
        staged_outputs = []

        with pd.ExcelFile(input_file, engine="openpyxl") as workbook:
            available_sheets = set(workbook.sheet_names)
            required_sheets = {
                sheet_name for sheet_name, _ in SHEET_TABLE_PAIRS
            }
            missing_sheets = sorted(required_sheets - available_sheets)

            if missing_sheets:
                raise ValueError(
                    "Workbook is missing required sheets: "
                    + ", ".join(missing_sheets)
                )

            for sheet_name, table_name in SHEET_TABLE_PAIRS:
                sheet_start = time.time()
                print(f"Extracting {sheet_name}...")

                dataframe = pd.read_excel(
                    workbook,
                    sheet_name=sheet_name,
                )
                dataframe.columns = normalize_columns(dataframe.columns)
                dataframe = preserve_text_columns(dataframe)

                output_name = f"{table_name}.parquet"
                staged_path = staging_folder / output_name
                final_path = output_folder / output_name
                dataframe.to_parquet(
                    staged_path,
                    index=False,
                    compression="snappy",
                )
                staged_outputs.append((staged_path, final_path))

                elapsed = round(time.time() - sheet_start, 2)
                manifest.append({
                    "sheet_name": sheet_name,
                    "status": "Success",
                    "rows": len(dataframe),
                    "columns": len(dataframe.columns),
                    "output_file": output_name,
                    "output_bytes": staged_path.stat().st_size,
                })

                print(
                    f"  Completed: {len(dataframe):,} rows, "
                    f"{len(dataframe.columns)} columns, "
                    f"{elapsed:,.2f} seconds"
                )

                del dataframe
                gc.collect()

        for staged_path, final_path in staged_outputs:
            staged_path.replace(final_path)

    manifest_dataframe = pd.DataFrame(manifest)

    manifest_path = report_folder / "extraction_manifest.csv"
    atomic_csv(manifest_dataframe, manifest_path)

    total_elapsed = round(time.time() - pipeline_start, 2)

    print()
    print("=" * 60)
    print("EXTRACTION COMPLETED")
    print("=" * 60)
    print(f"Tables processed: {len(manifest_dataframe)}")
    print(
        f"Total rows: "
        f"{manifest_dataframe['rows'].sum():,}"
    )
    print(f"Duration: {total_elapsed:,.2f} seconds")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    extract_workbook()
