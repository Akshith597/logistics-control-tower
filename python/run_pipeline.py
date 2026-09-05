"""Run the complete logistics analytics pipeline in a reproducible order."""

import argparse
import os
import subprocess
import sys
import time

from pipeline_config import PROJECT_ROOT

PIPELINE_STEPS = (
    ("extract", "01_extract_excel.py"),
    ("profile", "02_profile_data.py"),
    ("load", "03_load_duckdb.py"),
    ("staging", "04_run_staging_sql.py"),
    ("lines-events", "05_run_lines_events_sql.py"),
    ("wms-invoices", "06_run_wms_invoices_sql.py"),
    ("customer-impact", "07_run_claims_customer_sql.py"),
    ("star-schema", "08_run_star_schema_sql.py"),
    ("kpi-views", "09_run_kpi_views_sql.py"),
    ("export", "10_export_powerbi_parquet.py"),
    ("validate", "validate_pipeline.py"),
    ("insights", "11_generate_business_insights.py"),
)


def select_steps(start_at="extract", stop_after="insights"):
    """Return an inclusive, validated slice of pipeline steps."""
    step_names = tuple(name for name, _ in PIPELINE_STEPS)
    start_index = step_names.index(start_at)
    stop_index = step_names.index(stop_after)

    if start_index > stop_index:
        raise ValueError(
            f"Start step '{start_at}' comes after stop step '{stop_after}'."
        )

    return PIPELINE_STEPS[start_index : stop_index + 1]


def run_pipeline(
    start_at="extract",
    stop_after="insights",
    *,
    generate_demo_data=False,
    force_demo_data=False,
):
    """Execute each selected script with the current Python interpreter."""
    if force_demo_data and not generate_demo_data:
        raise ValueError("force_demo_data requires generate_demo_data")
    if generate_demo_data and start_at != "extract":
        raise ValueError(
            "generate_demo_data requires start_at='extract'"
        )

    selected_steps = select_steps(start_at, stop_after)
    environment = os.environ.copy()
    environment.setdefault("PYTHONHASHSEED", "0")
    pipeline_start = time.perf_counter()

    if generate_demo_data:
        generator = PROJECT_ROOT / "python" / "00_generate_demo_data.py"
        command = [sys.executable, str(generator)]
        if force_demo_data:
            command.append("--force")
        subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
        )

    for position, (step_name, script_name) in enumerate(selected_steps, 1):
        script_path = PROJECT_ROOT / "python" / script_name
        print()
        print("=" * 72)
        print(
            f"PIPELINE STEP {position}/{len(selected_steps)}: "
            f"{step_name.upper()}"
        )
        print("=" * 72)
        sys.stdout.flush()

        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            env=environment,
            check=True,
        )

    elapsed = time.perf_counter() - pipeline_start
    print()
    print(
        f"Pipeline completed: {len(selected_steps)} step(s) "
        f"in {elapsed:,.1f} seconds."
    )


def parse_args(argv=None):
    step_names = tuple(name for name, _ in PIPELINE_STEPS)
    parser = argparse.ArgumentParser(
        description="Run the logistics control-tower data pipeline."
    )
    parser.add_argument(
        "--start-at",
        choices=step_names,
        default=step_names[0],
        help="First pipeline step to run (default: extract).",
    )
    parser.add_argument(
        "--stop-after",
        choices=step_names,
        default=step_names[-1],
        help="Last pipeline step to run (default: insights).",
    )
    parser.add_argument(
        "--generate-demo-data",
        action="store_true",
        help=(
            "Generate the deterministic synthetic source workbook before "
            "running the selected steps."
        ),
    )
    parser.add_argument(
        "--force-demo-data",
        action="store_true",
        help=(
            "Allow --generate-demo-data to replace an existing source "
            "workbook."
        ),
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.force_demo_data and not args.generate_demo_data:
        raise SystemExit(
            "--force-demo-data requires --generate-demo-data."
        )
    try:
        run_pipeline(
            args.start_at,
            args.stop_after,
            generate_demo_data=args.generate_demo_data,
            force_demo_data=args.force_demo_data,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
