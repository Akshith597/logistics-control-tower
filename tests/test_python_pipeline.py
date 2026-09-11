"""Regression tests for the reproducible Python data pipeline."""

from contextlib import redirect_stdout
import importlib.util
import io
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

try:
    import duckdb
except ImportError:
    duckdb = None


# pandas loads the Parquet engine lazily, and importing it registers pyarrow's
# pandas extension types as a side effect. Resolving the engine here pins that
# one-time registration to a predictable point at import, rather than leaving it
# to whichever test first touches Parquet.
pd.io.parquet.get_engine("auto")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_ROOT / "python"
sys.path.insert(0, str(PYTHON_DIR))


def load_script(file_name):
    module_name = "test_" + Path(file_name).stem.replace("-", "_")
    specification = importlib.util.spec_from_file_location(
        module_name,
        PYTHON_DIR / file_name,
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


demo = load_script("00_generate_demo_data.py")
extract = load_script("01_extract_excel.py")
profile = load_script("02_profile_data.py")
load_database = load_script("03_load_duckdb.py")
run_staging = load_script("04_run_staging_sql.py")
run_lines_events = load_script("05_run_lines_events_sql.py")
run_wms_invoices = load_script("06_run_wms_invoices_sql.py")
run_customer_impact = load_script("07_run_claims_customer_sql.py")
run_star_schema = load_script("08_run_star_schema_sql.py")
run_kpi_views = load_script("09_run_kpi_views_sql.py")
export_powerbi = load_script("10_export_powerbi_parquet.py")
insights = load_script("11_generate_business_insights.py")
validate = load_script("validate_pipeline.py")
runner = load_script("run_pipeline.py")

from pipeline_config import PROCESSED_TABLES, SHEET_TABLE_PAIRS  # noqa: E402
from pipeline_utils import (  # noqa: E402
    atomic_csv,
    duckdb_transaction,
    file_sha256,
)


class PipelineUnitTests(unittest.TestCase):
    def test_demo_data_is_deterministic_and_relationship_complete(self):
        first = demo.build_demo_tables(shipment_count=24, seed=101)
        second = demo.build_demo_tables(shipment_count=24, seed=101)

        self.assertEqual(set(first), set(PROCESSED_TABLES))
        for table_name in PROCESSED_TABLES:
            pd.testing.assert_frame_equal(first[table_name], second[table_name])

        shipment_ids = set(first["tms_shipments"]["tms_shipment_id"])
        for child_table in (
            "tms_shipment_lines",
            "carrier_tracking_events",
            "wms_outbound",
            "erp_invoices",
            "claims",
            "crm_tickets",
            "csat_survey_responses",
        ):
            child_ids = set(first[child_table]["tms_shipment_id"])
            self.assertTrue(child_ids <= shipment_ids)

    def test_demo_survey_scores_are_not_derived_from_delivery_status(self):
        tables = demo.build_demo_tables(shipment_count=1_200, seed=101)
        shipments = tables["tms_shipments"][
            [
                "tms_shipment_id",
                "on_time_flag",
            ]
        ]
        surveys = tables["csat_survey_responses"].merge(
            shipments,
            on="tms_shipment_id",
            how="left",
            validate="many_to_one",
        )

        self.assertEqual(set(surveys["on_time_flag"]), {True, False})
        for status in (True, False):
            status_scores = surveys.loc[
                surveys["on_time_flag"] == status,
                "csat_score_1_to_5",
            ]
            self.assertGreater(status_scores.nunique(), 1)
        self.assertFalse(
            surveys["comment"].isin({"Delivery was late.", "Great service."}).any()
        )

    def test_demo_data_rejects_too_few_shipments(self):
        with self.assertRaisesRegex(ValueError, "at least 24"):
            demo.build_demo_tables(shipment_count=23)

    def test_large_demo_stays_within_2024_and_2025(self):
        shipments = demo.build_demo_tables(shipment_count=7_200)["tms_shipments"]

        self.assertEqual(shipments["ship_create_date"].min().isoformat(), "2024-01-01")
        self.assertLessEqual(
            shipments["ship_create_date"].max().isoformat(),
            "2025-12-31",
        )

    def test_demo_claim_values_are_bounded(self):
        claims = demo.build_demo_tables(shipment_count=7_200)["claims"]

        self.assertGreater(len(claims), 0)
        self.assertLessEqual(claims["claim_amount_requested_usd"].max(), 340.75)

    def test_column_normalization_rejects_collisions(self):
        self.assertEqual(
            extract.normalize_columns(
                ["Shipment ID", "Ship Date", "lastUpdateTS", "TMSShipmentID"]
            ),
            ["shipment_id", "ship_date", "last_update_ts", "tms_shipment_id"],
        )
        with self.assertRaisesRegex(ValueError, "collide"):
            extract.normalize_columns(["Shipment ID", "Shipment-ID"])

    def test_identifier_conversion_does_not_corrupt_text_suffixes(self):
        dataframe = pd.DataFrame(
            {
                "customer_id": [123.0, "ABC.0", None],
                "legal_name": ["Version.0", "Other", None],
            }
        )
        result = extract.preserve_text_columns(dataframe)
        self.assertEqual(result["customer_id"].iloc[0], "123")
        self.assertEqual(result["customer_id"].iloc[1], "ABC.0")
        self.assertEqual(result["legal_name"].iloc[0], "Version.0")

    def test_identifier_normalization_treats_blanks_as_null(self):
        result = profile.normalize_identifier(
            pd.Series([" abc ", "  ", None], dtype="string")
        )
        self.assertEqual(result.iloc[0], "ABC")
        self.assertTrue(pd.isna(result.iloc[1]))
        self.assertTrue(pd.isna(result.iloc[2]))

    def test_profile_state_can_be_reused_in_process(self):
        profile.table_profiles.append({"table_name": "stale"})
        profile.quality_issues.append({"table_name": "stale"})
        profile.reset_profile_state()
        self.assertEqual(profile.table_profiles, [])
        self.assertEqual(profile.quality_issues, [])

    def test_table_name_validation(self):
        self.assertEqual(
            load_database.valid_table_name("valid_table_1"),
            "valid_table_1",
        )
        for invalid_name in ("RawTable", "1table", "bad-name", "x; DROP"):
            with self.assertRaises(ValueError):
                load_database.valid_table_name(invalid_name)

    @unittest.skipUnless(duckdb is not None, "DuckDB native module unavailable")
    def test_transaction_rolls_back_the_complete_step(self):
        with TemporaryDirectory() as temporary_directory:
            database_file = Path(temporary_directory) / "rollback.duckdb"
            with (
                self.assertRaisesRegex(RuntimeError, "test failure"),
                duckdb_transaction(
                    database_file,
                    must_exist=False,
                ) as connection,
            ):
                connection.execute("CREATE TABLE should_rollback (id INTEGER)")
                raise RuntimeError("test failure")

            connection = duckdb.connect(str(database_file), read_only=True)
            try:
                table_count = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_name = 'should_rollback'
                    """
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(table_count, 0)

    def test_empty_csv_keeps_a_stable_header(self):
        with TemporaryDirectory() as temporary_directory:
            output_file = Path(temporary_directory) / "empty.csv"
            atomic_csv(
                pd.DataFrame(),
                output_file,
                columns=("table_name", "issue_count"),
            )
            self.assertEqual(
                output_file.read_text(encoding="utf-8"),
                "table_name,issue_count\n",
            )

    def test_source_fingerprint_is_stable(self):
        with TemporaryDirectory() as temporary_directory:
            source_file = Path(temporary_directory) / "source.txt"
            source_file.write_text("logistics\n", encoding="utf-8")
            self.assertEqual(file_sha256(source_file), file_sha256(source_file))
            self.assertEqual(len(file_sha256(source_file)), 64)

    def test_runner_order_includes_validation_and_insights(self):
        self.assertEqual(runner.PIPELINE_STEPS[-2][0], "validate")
        self.assertEqual(runner.PIPELINE_STEPS[-1][0], "insights")
        selected = runner.select_steps("load", "kpi-views")
        self.assertEqual(selected[0][0], "load")
        self.assertEqual(selected[-1][0], "kpi-views")
        with self.assertRaises(ValueError):
            runner.select_steps("export", "extract")
        with self.assertRaisesRegex(ValueError, "start_at='extract'"):
            runner.run_pipeline(
                "load",
                "load",
                generate_demo_data=True,
            )

    def test_demo_runner_isolates_source_and_report_outputs(self):
        demo_environment = runner.pipeline_environment(True)
        self.assertEqual(
            Path(demo_environment["LOGISTICS_INPUT_FILE"]),
            runner.DEMO_INPUT_FILE.resolve(),
        )
        self.assertEqual(
            Path(demo_environment["LOGISTICS_REPORT_DIR"]),
            runner.DEMO_REPORT_DIR.resolve(),
        )

        production_environment = runner.pipeline_environment(False)
        self.assertNotIn("LOGISTICS_INPUT_FILE", production_environment)
        self.assertNotIn("LOGISTICS_REPORT_DIR", production_environment)

    def test_model_validation_sql_is_part_of_the_contract(self):
        self.assertTrue(validate.VALIDATION_SQL_FILE.is_file())
        validation_sql = validate.VALIDATION_SQL_FILE.read_text(encoding="utf-8")
        self.assertIn("validation_status", validation_sql)

    def test_model_validation_failures_are_not_treated_as_passes(self):
        checks = validate.sql_validation_checks(
            [
                ("healthy check", "CRITICAL", 0, "PASS"),
                ("broken check", "CRITICAL", 2, "FAIL"),
            ]
        )
        conditions = {name: condition for name, condition, _ in checks}
        self.assertTrue(conditions["SQL [CRITICAL] healthy check"])
        self.assertFalse(conditions["SQL [CRITICAL] broken check"])

    def test_insight_context_uses_exact_metric_denominators(self):
        fact = pd.DataFrame(
            {
                "official_kpi_eligible_flag": [True, True, True, False],
                "final_on_time_flag": [True, False, None, True],
                "otif_flag": [True, False, None, True],
                "shipment_fill_rate": [1.0, 0.5, None, 1.0],
                "survey_response_count": [1, 0, 0, 1],
                "ship_date": ["2025-01-01"] * 4,
                "shipment_status": ["DELIVERED"] * 4,
                "customer_key": ["C1", "C1", "C2", "C2"],
                "actual_delivery_date": ["2025-01-02", None, None, "2025-01-02"],
            }
        )
        context = insights.build_analysis_context(fact)
        self.assertEqual(context["otd_eligible_shipments"], 2)
        self.assertEqual(context["otif_eligible_shipments"], 2)
        self.assertEqual(context["fill_measured_shipments"], 2)
        self.assertEqual(context["full_fill_shipments"], 1)
        self.assertEqual(context["full_fill_rate"], 0.5)
        self.assertEqual(context["missing_otd_result_shipments"], 1)
        self.assertEqual(context["missing_otif_result_shipments"], 1)

    def test_delivery_impact_weights_valid_csat_by_response_count(self):
        fact = pd.DataFrame(
            {
                "official_kpi_eligible_flag": [True, True, True, True],
                "final_on_time_flag": [True, True, False, False],
                "survey_response_count": [1, 3, 2, 10],
                "valid_csat_response_count": [1, 2, 1, 0],
                "average_csat_score": [5.0, 3.0, 2.0, None],
                "complaint_flag": [False, False, True, True],
                "claim_flag": [False, False, True, False],
                "days_late": [0, 0, 2, 3],
                "shipment_key": ["S1", "S2", "S3", "S4"],
            }
        )
        impact = insights.build_delivery_impact(fact).set_index("delivery_status")
        self.assertEqual(impact.loc["On time", "csat_observations"], 3)
        self.assertAlmostEqual(impact.loc["On time", "average_csat"], 11 / 3)
        self.assertEqual(impact.loc["Late", "csat_observations"], 1)
        self.assertEqual(impact.loc["Late", "average_csat"], 2.0)

    def test_eligibility_counts_keep_otd_and_otif_denominators_separate(self):
        scorecard = pd.DataFrame({"carrier_key": ["C1", "C2"]})
        fact = pd.DataFrame(
            {
                "carrier_key": ["C1", "C1", "C1", "C1", "C2"],
                "official_kpi_eligible_flag": [True, True, False, True, True],
                "final_on_time_flag": [True, False, True, None, True],
                "otif_flag": [True, None, True, False, True],
            }
        )
        result = insights.add_eligibility_counts(
            scorecard,
            fact,
            "carrier_key",
        ).set_index("carrier_key")
        self.assertEqual(result.loc["C1", "otd_eligible_shipments"], 2)
        self.assertEqual(result.loc["C1", "on_time_shipments"], 1)
        self.assertEqual(result.loc["C1", "otif_eligible_shipments"], 2)
        self.assertEqual(result.loc["C1", "otif_shipments"], 1)

    def test_safe_ratio_handles_zero_denominator(self):
        self.assertTrue(math.isnan(insights.safe_ratio(1, 0)))
        self.assertEqual(insights.safe_ratio(3, 4), 0.75)


class PipelineIntegrationTests(unittest.TestCase):
    def test_demo_workbook_extracts_and_profiles(self):
        with TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            workbook = temporary_root / "raw" / "Logistical_Data.xlsx"
            processed_dir = temporary_root / "processed"
            report_dir = temporary_root / "reports"

            with redirect_stdout(io.StringIO()):
                demo.write_demo_workbook(
                    workbook,
                    shipment_count=24,
                    seed=101,
                )
                extract.extract_workbook(
                    workbook,
                    processed_dir,
                    report_dir,
                )
                profile.main(processed_dir, report_dir)

            with pd.ExcelFile(workbook, engine="openpyxl") as source:
                self.assertEqual(
                    tuple(source.sheet_names),
                    tuple(sheet for sheet, _ in SHEET_TABLE_PAIRS),
                )
            self.assertEqual(
                len(list(processed_dir.glob("*.parquet"))),
                len(SHEET_TABLE_PAIRS),
            )
            quality = pd.read_csv(report_dir / "data_quality_issues.csv")
            self.assertTrue((quality["status"] == "Pass").all())

    @unittest.skipUnless(duckdb is not None, "DuckDB native module unavailable")
    def test_small_demo_runs_from_workbook_through_validated_exports(self):
        with TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            workbook = temporary_root / "raw" / "Logistical_Data.xlsx"
            processed_dir = temporary_root / "processed"
            report_dir = temporary_root / "reports"
            database_file = temporary_root / "database" / "logistics.duckdb"
            powerbi_dir = temporary_root / "powerbi"

            with redirect_stdout(io.StringIO()):
                demo.write_demo_workbook(
                    workbook,
                    shipment_count=24,
                    seed=101,
                )
                extract.extract_workbook(
                    workbook,
                    processed_dir,
                    report_dir,
                )
                profile.main(processed_dir, report_dir)
                load_database.load_database(
                    processed_dir,
                    database_file,
                )
                run_staging.run_sql(
                    database_file,
                    PROJECT_ROOT / "sql" / "01_create_staging.sql",
                )
                run_lines_events.run_sql(
                    database_file,
                    PROJECT_ROOT / "sql" / "02_stage_lines_events.sql",
                )
                run_wms_invoices.run_sql(
                    database_file,
                    PROJECT_ROOT / "sql" / "03_stage_wms_invoices.sql",
                )
                run_customer_impact.run_sql(
                    database_file,
                    PROJECT_ROOT / "sql" / "04_stage_claims_customer.sql",
                )
                run_star_schema.run_sql(
                    database_file,
                    PROJECT_ROOT / "sql" / "05_build_star_schema.sql",
                )
                run_kpi_views.run_sql(
                    database_file,
                    PROJECT_ROOT / "sql" / "06_create_kpi_views.sql",
                )
                export_powerbi.export_powerbi_files(
                    database_file,
                    powerbi_dir,
                )
                passed = validate.validate_pipeline(
                    database_file,
                    processed_dir,
                    powerbi_dir,
                    report_dir,
                    PROJECT_ROOT / "sql" / "07_validate_model.sql",
                )

            self.assertGreaterEqual(len(passed), 40)
            self.assertEqual(
                len(list(processed_dir.glob("*.parquet"))),
                len(SHEET_TABLE_PAIRS),
            )
            self.assertTrue((powerbi_dir / "fact_shipment.parquet").is_file())
            duplicate_header = (
                (report_dir / "duplicate_keys.csv")
                .read_text(encoding="utf-8")
                .splitlines()[0]
            )
            self.assertIn("duplicate_count", duplicate_header)


if __name__ == "__main__":
    unittest.main()
