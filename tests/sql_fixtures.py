"""Build tiny, hand-authored DuckDB fixtures for the production SQL layer.

These helpers create the twelve ``raw`` tables with the documented column
contract, insert a handful of deliberately awkward rows, and then execute the
real ``sql/*.sql`` files against them. Nothing here re-implements pipeline
logic: the assertions in ``test_sql_transforms.py`` exercise the same SQL that
runs in production, just on inputs small enough to reason about by hand.
"""

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"


# ============================================================
# Raw column contract
#
# Every raw table is created as VARCHAR because the real pipeline lands
# spreadsheet extracts, and the staging layer is responsible for TRY_CAST and
# TRIM. Stating the contract here rather than importing it from the demo
# generator keeps these tests an independent check on the schema; the
# ``test_demo_generator_matches_raw_contract`` test asserts the two agree.
# ============================================================

RAW_TABLE_COLUMNS = {
    "erp_customers": (
        "erp_customer_id",
        "legal_name",
        "dba_name",
        "parent_erp_customer_id",
        "industry",
        "customer_status",
        "payment_terms",
        "credit_limit_usd",
        "primary_bill_to_state",
        "account_owner_email",
        "created_date",
        "last_modified_ts",
        "source_system",
        "is_test_account",
        "notes",
        "annual_volume_tier",
    ),
    "customer_id_crosswalk": (
        "erp_customer_id",
        "tms_customer_code",
        "is_primary_mapping",
        "effective_from",
        "effective_to",
        "mapping_confidence",
        "notes",
    ),
    "ref_warehouses": (
        "warehouse_id",
        "wms_location_code",
        "warehouse_name",
        "city",
        "state",
        "postal_code",
        "latitude",
        "longitude",
        "timezone",
        "daily_outbound_capacity",
        "is_active",
        "source_system",
    ),
    "ref_carriers": (
        "carrier_id",
        "scac",
        "carrier_legal_name",
        "mode",
        "status",
        "notes",
        "source_system",
    ),
    "tms_shipments": (
        "tms_shipment_id",
        "tms_customer_code",
        "erp_customer_id_ref",
        "sales_order_id",
        "customer_po",
        "bol_number",
        "pro_number",
        "tracking_number",
        "origin_warehouse_id",
        "origin_wms_code",
        "dest_name",
        "dest_address1",
        "dest_city",
        "dest_state",
        "dest_postal",
        "dest_country",
        "is_residential",
        "carrier_id",
        "carrier_scac",
        "mode",
        "service_level_code",
        "service_level_name",
        "planned_transit_days",
        "lane_miles_est",
        "ship_create_date",
        "ship_create_ts",
        "promised_delivery_date",
        "actual_pickup_ts",
        "actual_delivery_ts",
        "shipment_status",
        "exception_code",
        "weight_lb",
        "pieces",
        "freight_class",
        "estimated_revenue_usd",
        "estimated_cost_usd",
        "currency",
        "on_time_flag",
        "is_void",
        "is_re_tender",
        "parent_tms_shipment_id",
        "source_system",
        "extract_batch_id",
        "last_update_ts",
        "row_hash",
    ),
    "tms_shipment_lines": (
        "tms_shipment_id",
        "line_number",
        "sku",
        "description",
        "qty_ordered",
        "qty_shipped",
        "unit_weight_lb",
        "hazardous_flag",
        "source_system",
    ),
    "carrier_tracking_events": (
        "column1",
        "tms_shipment_id",
        "tracking_number",
        "event_code",
        "event_description",
        "event_ts_utc",
        "event_ts_local",
        "event_city",
        "event_state",
        "exception_reason",
        "source",
        "ingested_ts",
    ),
    "wms_outbound": (
        "wms_outbound_id",
        "wms_location_code",
        "sales_order_id",
        "tms_shipment_id",
        "pick_start_ts",
        "pack_complete_ts",
        "ship_confirm_ts",
        "lines_picked",
        "short_pick_flag",
        "inventory_accuracy_snapshot",
        "source_system",
    ),
    "erp_invoices": (
        "invoice_id",
        "invoice_type",
        "erp_customer_id",
        "tms_shipment_id",
        "sales_order_id",
        "pro_number",
        "invoice_date",
        "gl_post_date",
        "line_amount_usd",
        "accessorial_amount_usd",
        "fuel_surcharge_usd",
        "tax_usd",
        "currency",
        "payment_status",
        "dispute_flag",
        "source_system",
    ),
    "claims": (
        "claim_id",
        "tms_shipment_id",
        "pro_number",
        "claim_type",
        "filed_date",
        "claim_amount_requested_usd",
        "claim_amount_paid_usd",
        "claim_status",
        "carrier_id",
        "source_system",
        "adjuster_notes",
    ),
    "crm_tickets": (
        "ticket_id",
        "opened_ts",
        "erp_customer_id",
        "tms_customer_code",
        "tms_shipment_id",
        "tracking_number",
        "channel",
        "category_raw",
        "severity",
        "status",
        "subject",
        "description_free_text",
        "resolution_hours",
        "source_system",
    ),
    "csat_survey_responses": (
        "response_id",
        "survey_sent_ts",
        "response_ts",
        "erp_customer_id",
        "tms_shipment_id",
        "csat_score_1_to_5",
        "nps_score_0_to_10",
        "comment",
        "source_system",
    ),
}


SQL_STAGES = (
    "01_create_staging.sql",
    "02_stage_lines_events.sql",
    "03_stage_wms_invoices.sql",
    "04_stage_claims_customer.sql",
    "05_build_star_schema.sql",
    "06_create_kpi_views.sql",
)


# ============================================================
# Fixture defaults
#
# One customer, one warehouse, one carrier and one crosswalk row, so that a
# test only has to state the rows it actually cares about.
# ============================================================

BASE_CUSTOMER = {
    "erp_customer_id": "C001",
    "legal_name": "Northwind Freight LLC",
    "customer_status": "ACTIVE",
    "primary_bill_to_state": "IL",
    "created_date": "2023-01-01",
    "is_test_account": "false",
    "annual_volume_tier": "GOLD",
    "source_system": "ERP",
}

BASE_CROSSWALK = {
    "erp_customer_id": "C001",
    "tms_customer_code": "NW-001",
    "is_primary_mapping": "true",
    "effective_from": "2023-01-01",
    "mapping_confidence": "HIGH",
}

BASE_WAREHOUSE = {
    "warehouse_id": "W01",
    "wms_location_code": "CHI1",
    "warehouse_name": "Chicago DC",
    "city": "Chicago",
    "state": "IL",
    "postal_code": "60601",
    "is_active": "true",
    "source_system": "WMS",
}

BASE_CARRIER = {
    "carrier_id": "CAR1",
    "scac": "ABCD",
    "carrier_legal_name": "Acme Trucking",
    "mode": "LTL",
    "status": "ACTIVE",
    "source_system": "TMS",
}


def shipment(shipment_id, **overrides):
    """Return a delivered, on-time shipment row with sensible defaults."""
    row = {
        "tms_shipment_id": shipment_id,
        "tms_customer_code": "NW-001",
        "erp_customer_id_ref": "C001",
        "sales_order_id": f"SO-{shipment_id}",
        "pro_number": f"PRO-{shipment_id}",
        "tracking_number": f"TRK-{shipment_id}",
        "origin_warehouse_id": "W01",
        "origin_wms_code": "CHI1",
        "dest_city": "Denver",
        "dest_state": "CO",
        "dest_postal": "80202",
        "dest_country": "USA",
        "is_residential": "false",
        "carrier_id": "CAR1",
        "carrier_scac": "ABCD",
        "mode": "LTL",
        "service_level_code": "STD",
        "service_level_name": "Standard",
        "planned_transit_days": "3",
        "lane_miles_est": "1000",
        "ship_create_date": "2024-01-01",
        "ship_create_ts": "2024-01-01 08:00:00",
        "promised_delivery_date": "2024-01-04",
        "actual_pickup_ts": "2024-01-01 12:00:00",
        "actual_delivery_ts": "2024-01-03 15:00:00",
        "shipment_status": "DELIVERED",
        "currency": "USD",
        "is_void": "false",
        "is_re_tender": "false",
        "source_system": "TMS",
        "extract_batch_id": "B1",
        "last_update_ts": "2024-01-05 00:00:00",
    }
    row.update(overrides)
    return row


def create_fixture_database(tables, *, through="06_create_kpi_views.sql"):
    """Create raw tables from *tables* and run the real SQL through *through*.

    ``tables`` maps a raw table name to a list of row dicts. Keys omitted from
    a row are inserted as NULL, so each test states only the columns under
    examination. Returns an open in-memory DuckDB connection; the caller closes
    it.
    """
    unknown_tables = set(tables) - set(RAW_TABLE_COLUMNS)
    if unknown_tables:
        raise ValueError(
            "Unknown raw tables: " + ", ".join(sorted(unknown_tables))
        )

    connection = duckdb.connect(":memory:")

    for schema_name in ("raw", "staging", "mart", "quality"):
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

    for table_name, columns in RAW_TABLE_COLUMNS.items():
        column_sql = ",\n    ".join(f"{column} VARCHAR" for column in columns)
        connection.execute(
            f"CREATE OR REPLACE TABLE raw.{table_name} (\n    {column_sql}\n)"
        )

        rows = tables.get(table_name, ())
        if not rows:
            continue

        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(
            f"INSERT INTO raw.{table_name} VALUES ({placeholders})",
            [
                [_as_text(row.get(column)) for column in columns]
                for row in _validated_rows(table_name, columns, rows)
            ],
        )

    stop_index = SQL_STAGES.index(through)
    for sql_file_name in SQL_STAGES[: stop_index + 1]:
        connection.execute(
            (SQL_DIR / sql_file_name).read_text(encoding="utf-8")
        )

    return connection


def _validated_rows(table_name, columns, rows):
    """Fail loudly on a typo in a fixture column name."""
    allowed = set(columns)
    for row in rows:
        unknown_columns = set(row) - allowed
        if unknown_columns:
            raise ValueError(
                f"raw.{table_name} has no column(s): "
                + ", ".join(sorted(unknown_columns))
            )
        yield row


def _as_text(value):
    """Land every fixture value the way a spreadsheet extract would."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def fetch_one(connection, sql, parameters=None):
    """Return a single scalar, or None when the query returns no rows."""
    result = connection.execute(sql, parameters or []).fetchone()
    return None if result is None else result[0]


def fetch_dict(connection, sql, parameters=None):
    """Return one row as a column-name keyed dict."""
    cursor = connection.execute(sql, parameters or [])
    row = cursor.fetchone()
    if row is None:
        return None
    column_names = [column[0] for column in cursor.description]
    return dict(zip(column_names, row, strict=True))
