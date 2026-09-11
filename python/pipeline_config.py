"""Shared, deterministic configuration for the logistics pipeline."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def configured_path(environment_name: str, default: Path | str) -> Path:
    """Resolve an optional path override relative to the project root."""
    value = os.environ.get(environment_name)
    path = Path(value) if value else Path(default)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


DEFAULT_INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "Logistical_Data.xlsx"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports"
INPUT_FILE = configured_path("LOGISTICS_INPUT_FILE", DEFAULT_INPUT_FILE)
REPORT_DIR = configured_path("LOGISTICS_REPORT_DIR", DEFAULT_REPORT_DIR)

SHEET_TABLE_PAIRS = (
    ("ERP_Customers", "erp_customers"),
    ("Customer_ID_Crosswalk", "customer_id_crosswalk"),
    ("Ref_Warehouses", "ref_warehouses"),
    ("Ref_Carriers", "ref_carriers"),
    ("TMS_Shipments", "tms_shipments"),
    ("TMS_Shipment_Lines", "tms_shipment_lines"),
    ("Carrier_Tracking_Events", "carrier_tracking_events"),
    ("WMS_Outbound", "wms_outbound"),
    ("ERP_Invoices", "erp_invoices"),
    ("Claims", "claims"),
    ("CRM_Tickets", "crm_tickets"),
    ("CSAT_Survey_Responses", "csat_survey_responses"),
)

SOURCE_SHEETS = tuple(sheet for sheet, _ in SHEET_TABLE_PAIRS)
PROCESSED_TABLES = tuple(table for _, table in SHEET_TABLE_PAIRS)

KPI_VIEWS = (
    "vw_executive_kpis",
    "vw_monthly_performance",
    "vw_carrier_scorecard",
    "vw_warehouse_scorecard",
    "vw_customer_scorecard",
    "vw_lane_scorecard",
)

POWERBI_EXPORTS = (
    ("mart.fact_shipment", "fact_shipment.parquet"),
    ("mart.dim_date", "dim_date.parquet"),
    ("mart.dim_customer", "dim_customer.parquet"),
    ("mart.dim_carrier", "dim_carrier.parquet"),
    ("mart.dim_warehouse", "dim_warehouse.parquet"),
    ("mart.dim_service", "dim_service.parquet"),
    ("mart.dim_lane", "dim_lane.parquet"),
    ("mart.vw_executive_kpis", "vw_executive_kpis.parquet"),
    ("mart.vw_monthly_performance", "vw_monthly_performance.parquet"),
    ("mart.vw_carrier_scorecard", "vw_carrier_scorecard.parquet"),
    ("mart.vw_warehouse_scorecard", "vw_warehouse_scorecard.parquet"),
    ("mart.vw_customer_scorecard", "vw_customer_scorecard.parquet"),
    ("mart.vw_lane_scorecard", "vw_lane_scorecard.parquet"),
)
