from datetime import datetime

import pandas as pd

from pipeline_config import PROCESSED_TABLES, PROJECT_ROOT
from pipeline_utils import atomic_csv, require_named_files

DATA_FOLDER = PROJECT_ROOT / "data" / "processed"
REPORT_FOLDER = PROJECT_ROOT / "reports"

PRIMARY_KEYS = {
    "erp_customers": ["erp_customer_id"],
    "customer_id_crosswalk": [
        "tms_customer_code",
        "effective_from",
    ],
    "ref_warehouses": ["warehouse_id"],
    "ref_carriers": ["carrier_id"],
    "tms_shipments": ["tms_shipment_id"],
    "tms_shipment_lines": [
        "tms_shipment_id",
        "line_number",
    ],
    "carrier_tracking_events": ["column1"],
    "wms_outbound": ["wms_outbound_id"],
    "erp_invoices": ["invoice_id"],
    "claims": ["claim_id"],
    "crm_tickets": ["ticket_id"],
    "csat_survey_responses": ["response_id"],
}


table_profiles = []
column_profiles = []
duplicate_records = []
quality_issues = []

TABLE_PROFILE_COLUMNS = (
    "table_name",
    "row_count",
    "column_count",
    "fully_duplicated_rows",
    "duplicate_key_groups",
    "file_bytes",
)
COLUMN_PROFILE_COLUMNS = (
    "table_name",
    "column_name",
    "data_type",
    "row_count",
    "null_count",
    "null_percentage",
    "distinct_count",
    "minimum_value",
    "maximum_value",
    "sample_value",
)
DUPLICATE_REPORT_COLUMNS = (
    "table_name",
    "key_columns",
    "duplicate_count",
    *dict.fromkeys(
        column
        for primary_key in PRIMARY_KEYS.values()
        for column in primary_key
    ),
)
QUALITY_REPORT_COLUMNS = (
    "table_name",
    "check_name",
    "status",
    "issue_count",
    "severity",
    "description",
)


def reset_profile_state():
    """Make repeated in-process runs produce independent reports."""
    table_profiles.clear()
    column_profiles.clear()
    duplicate_records.clear()
    quality_issues.clear()


def add_issue(
    table_name,
    check_name,
    issue_count,
    severity,
    description,
):
    quality_issues.append({
        "table_name": table_name,
        "check_name": check_name,
        "status": "Pass" if issue_count == 0 else "Issue",
        "issue_count": int(issue_count),
        "severity": severity,
        "description": description,
    })


def normalize_identifier(series):
    normalized = (
        series.astype("string")
        .str.strip()
        .str.upper()
    )
    return normalized.mask(normalized.eq(""))


def profile_table(file_path):
    table_name = file_path.stem

    print(f"Profiling {table_name}...")

    dataframe = pd.read_parquet(file_path)
    primary_key = PRIMARY_KEYS.get(table_name, [])

    fully_duplicated_rows = int(
        dataframe.duplicated(keep=False).sum()
    )

    duplicate_key_groups = 0

    if primary_key:
        missing_key_columns = [
            column
            for column in primary_key
            if column not in dataframe.columns
        ]

        if missing_key_columns:
            add_issue(
                table_name,
                "Primary-key columns exist",
                len(missing_key_columns),
                "High",
                "Missing key columns: "
                + ", ".join(missing_key_columns),
            )
        else:
            null_key_rows = int(
                dataframe[primary_key]
                .isna()
                .any(axis=1)
                .sum()
            )

            add_issue(
                table_name,
                "Null primary keys",
                null_key_rows,
                "High",
                "Primary-key fields should not be null.",
            )

            complete_key_mask = ~dataframe[primary_key].isna().any(axis=1)
            duplicate_mask = complete_key_mask & dataframe.duplicated(
                subset=primary_key,
                keep=False,
            )

            duplicate_key_groups = int(
                dataframe.loc[duplicate_mask, primary_key]
                .drop_duplicates()
                .shape[0]
            )

            add_issue(
                table_name,
                "Duplicate primary keys",
                duplicate_key_groups,
                "High",
                "Primary-key values should be unique.",
            )

            if duplicate_key_groups > 0:
                duplicate_groups = (
                    dataframe.loc[duplicate_mask, primary_key]
                    .fillna("<NULL>")
                    .astype(str)
                    .value_counts()
                    .reset_index(name="duplicate_count")
                )

                for _, row in duplicate_groups.iterrows():
                    record = {
                        "table_name": table_name,
                        "key_columns": " + ".join(primary_key),
                        "duplicate_count": int(
                            row["duplicate_count"]
                        ),
                    }

                    for key_column in primary_key:
                        record[key_column] = row[key_column]

                    duplicate_records.append(record)

    table_profiles.append({
        "table_name": table_name,
        "row_count": len(dataframe),
        "column_count": len(dataframe.columns),
        "fully_duplicated_rows": fully_duplicated_rows,
        "duplicate_key_groups": duplicate_key_groups,
        "file_bytes": file_path.stat().st_size,
    })

    for column in dataframe.columns:
        series = dataframe[column]

        null_count = int(series.isna().sum())
        distinct_count = int(series.nunique(dropna=True))

        non_null_values = series.dropna()
        sample_value = ""

        if not non_null_values.empty:
            sample_value = str(non_null_values.iloc[0])[:100]

        minimum_value = ""
        maximum_value = ""

        if pd.api.types.is_numeric_dtype(series):
            if not non_null_values.empty:
                minimum_value = non_null_values.min()
                maximum_value = non_null_values.max()

        elif (
            column.endswith("_date")
            or column.endswith("_ts")
        ):
            parsed_dates = pd.to_datetime(
                series,
                errors="coerce",
            )

            if parsed_dates.notna().any():
                minimum_value = parsed_dates.min()
                maximum_value = parsed_dates.max()

        column_profiles.append({
            "table_name": table_name,
            "column_name": column,
            "data_type": str(series.dtype),
            "row_count": len(dataframe),
            "null_count": null_count,
            "null_percentage": round(
                null_count / len(dataframe) * 100,
                2,
            ) if len(dataframe) else 0,
            "distinct_count": distinct_count,
            "minimum_value": minimum_value,
            "maximum_value": maximum_value,
            "sample_value": sample_value,
        })

    print(
        f"  {len(dataframe):,} rows and "
        f"{len(dataframe.columns)} columns"
    )


def check_relationship(
    child_table,
    child_column,
    parent_values,
    severity,
    description,
    data_folder=DATA_FOLDER,
):
    child_path = data_folder / f"{child_table}.parquet"

    child_data = pd.read_parquet(
        child_path,
        columns=[child_column],
    )

    child_ids = normalize_identifier(
        child_data[child_column]
    )

    non_null_ids = child_ids.dropna()

    unmatched_count = int(
        (~non_null_ids.isin(parent_values)).sum()
    )

    add_issue(
        child_table,
        f"Unmatched {child_column}",
        unmatched_count,
        severity,
        description,
    )


def run_business_checks(data_folder=DATA_FOLDER):
    print()
    print("Running cross-table and business-rule checks...")

    shipments = pd.read_parquet(
        data_folder / "tms_shipments.parquet",
        columns=[
            "tms_shipment_id",
            "tms_customer_code",
            "erp_customer_id_ref",
            "carrier_id",
            "origin_warehouse_id",
            "actual_pickup_ts",
            "actual_delivery_ts",
            "shipment_status",
        ],
    )

    shipment_ids = set(
        normalize_identifier(
            shipments["tms_shipment_id"]
        ).dropna()
    )

    customers = pd.read_parquet(
        data_folder / "erp_customers.parquet",
        columns=["erp_customer_id"],
    )

    customer_ids = set(
        normalize_identifier(
            customers["erp_customer_id"]
        ).dropna()
    )

    crosswalk = pd.read_parquet(
        data_folder / "customer_id_crosswalk.parquet",
        columns=["tms_customer_code"],
    )

    customer_codes = set(
        normalize_identifier(
            crosswalk["tms_customer_code"]
        ).dropna()
    )

    carriers = pd.read_parquet(
        data_folder / "ref_carriers.parquet",
        columns=["carrier_id"],
    )

    carrier_ids = set(
        normalize_identifier(
            carriers["carrier_id"]
        ).dropna()
    )

    warehouses = pd.read_parquet(
        data_folder / "ref_warehouses.parquet",
        columns=["warehouse_id"],
    )

    warehouse_ids = set(
        normalize_identifier(
            warehouses["warehouse_id"]
        ).dropna()
    )

    shipment_customer_codes = normalize_identifier(
        shipments["tms_customer_code"]
    ).dropna()

    add_issue(
        "tms_shipments",
        "Unmatched TMS customer codes",
        (~shipment_customer_codes.isin(customer_codes)).sum(),
        "High",
        "TMS customer codes should match the customer crosswalk.",
    )

    shipment_customer_ids = normalize_identifier(
        shipments["erp_customer_id_ref"]
    ).dropna()

    add_issue(
        "tms_shipments",
        "Unmatched ERP customer references",
        (~shipment_customer_ids.isin(customer_ids)).sum(),
        "High",
        "ERP customer references should match ERP_Customers.",
    )

    shipment_carriers = normalize_identifier(
        shipments["carrier_id"]
    ).dropna()

    add_issue(
        "tms_shipments",
        "Unmatched carriers",
        (~shipment_carriers.isin(carrier_ids)).sum(),
        "High",
        "Shipment carrier IDs should match Ref_Carriers.",
    )

    shipment_warehouses = normalize_identifier(
        shipments["origin_warehouse_id"]
    ).dropna()

    add_issue(
        "tms_shipments",
        "Unmatched warehouses",
        (~shipment_warehouses.isin(warehouse_ids)).sum(),
        "High",
        "Origin warehouse IDs should match Ref_Warehouses.",
    )

    # Shipment date validation
    pickup_dates = pd.to_datetime(
        shipments["actual_pickup_ts"],
        errors="coerce",
    )

    delivery_dates = pd.to_datetime(
        shipments["actual_delivery_ts"],
        errors="coerce",
    )

    delivery_before_pickup = int(
        (
            delivery_dates.notna()
            & pickup_dates.notna()
            & (delivery_dates < pickup_dates)
        ).sum()
    )

    add_issue(
        "tms_shipments",
        "Delivery before pickup",
        delivery_before_pickup,
        "High",
        "Actual delivery cannot occur before actual pickup.",
    )

    delivered_mask = (
        shipments["shipment_status"]
        .astype("string")
        .str.upper()
        .eq("DELIVERED")
    )

    missing_delivered_date = int(
        (
            delivered_mask
            & delivery_dates.isna()
        ).sum()
    )

    add_issue(
        "tms_shipments",
        "Delivered shipments missing delivery date",
        missing_delivered_date,
        "High",
        "Delivered shipments should normally have an actual delivery timestamp.",
    )

    # Shipment children
    for table_name in [
        "tms_shipment_lines",
        "carrier_tracking_events",
        "claims",
        "crm_tickets",
        "csat_survey_responses",
    ]:
        check_relationship(
            table_name,
            "tms_shipment_id",
            shipment_ids,
            "Medium",
            "Non-null shipment IDs should match TMS_Shipments.",
            data_folder=data_folder,
        )

    # WMS missing shipment IDs
    wms = pd.read_parquet(
        data_folder / "wms_outbound.parquet",
        columns=["tms_shipment_id", "sales_order_id"],
    )

    missing_wms_shipment = int(
        wms["tms_shipment_id"].isna().sum()
    )

    add_issue(
        "wms_outbound",
        "Missing TMS shipment ID",
        missing_wms_shipment,
        "Medium",
        "Use sales_order_id as the controlled fallback match.",
    )

    # Invoice missing shipment IDs
    invoices = pd.read_parquet(
        data_folder / "erp_invoices.parquet",
        columns=[
            "tms_shipment_id",
            "sales_order_id",
            "line_amount_usd",
            "accessorial_amount_usd",
            "fuel_surcharge_usd",
        ],
    )

    missing_invoice_shipment = int(
        invoices["tms_shipment_id"].isna().sum()
    )

    add_issue(
        "erp_invoices",
        "Missing TMS shipment ID",
        missing_invoice_shipment,
        "Medium",
        "Use sales order and PRO number as controlled fallbacks.",
    )

    # Shipment-line quantity checks
    lines = pd.read_parquet(
        data_folder / "tms_shipment_lines.parquet",
        columns=["qty_ordered", "qty_shipped"],
    )

    ordered = pd.to_numeric(
        lines["qty_ordered"],
        errors="coerce",
    )

    shipped = pd.to_numeric(
        lines["qty_shipped"],
        errors="coerce",
    )

    add_issue(
        "tms_shipment_lines",
        "Missing shipped quantity",
        shipped.isna().sum(),
        "Medium",
        "Missing shipped quantity should remain null, not zero.",
    )

    add_issue(
        "tms_shipment_lines",
        "Negative quantity",
        ((ordered < 0) | (shipped < 0)).sum(),
        "High",
        "Ordered and shipped quantities cannot be negative.",
    )

    add_issue(
        "tms_shipment_lines",
        "Shipped quantity above ordered quantity",
        (shipped > ordered).sum(),
        "Low",
        "Overshipments are possible but should be reviewed.",
    )

    # Duplicate delivered tracking events
    events = pd.read_parquet(
        data_folder / "carrier_tracking_events.parquet",
        columns=[
            "tms_shipment_id",
            "event_code",
        ],
    )

    delivered_events = events[
        events["event_code"]
        .astype("string")
        .str.strip()
        .str.upper()
        .eq("DLV")
        & events["tms_shipment_id"].notna()
    ]

    duplicate_delivery_events = int(
        delivered_events.duplicated(
            subset=["tms_shipment_id", "event_code"],
            keep="last",
        ).sum()
    )

    add_issue(
        "carrier_tracking_events",
        "Duplicate delivery events",
        duplicate_delivery_events,
        "Medium",
        "Keep the event with the latest ingestion timestamp.",
    )

    # Claim validation
    claims = pd.read_parquet(
        data_folder / "claims.parquet",
        columns=[
            "claim_amount_requested_usd",
            "claim_amount_paid_usd",
        ],
    )

    requested = pd.to_numeric(
        claims["claim_amount_requested_usd"],
        errors="coerce",
    )

    paid = pd.to_numeric(
        claims["claim_amount_paid_usd"],
        errors="coerce",
    )

    add_issue(
        "claims",
        "Paid claim above requested amount",
        (paid > requested).sum(),
        "High",
        "Paid claim amount should not exceed requested amount.",
    )

    # Survey score validation
    surveys = pd.read_parquet(
        data_folder / "csat_survey_responses.parquet",
        columns=[
            "csat_score_1_to_5",
            "nps_score_0_to_10",
        ],
    )

    csat = pd.to_numeric(
        surveys["csat_score_1_to_5"],
        errors="coerce",
    )

    nps = pd.to_numeric(
        surveys["nps_score_0_to_10"],
        errors="coerce",
    )

    add_issue(
        "csat_survey_responses",
        "Invalid CSAT score",
        ((csat < 1) | (csat > 5)).sum(),
        "High",
        "CSAT must be between 1 and 5.",
    )

    add_issue(
        "csat_survey_responses",
        "Invalid NPS score",
        ((nps < 0) | (nps > 10)).sum(),
        "High",
        "NPS responses must be between 0 and 10.",
    )


def save_reports(report_folder=REPORT_FOLDER):
    report_folder.mkdir(parents=True, exist_ok=True)

    atomic_csv(
        pd.DataFrame(table_profiles),
        report_folder / "table_profile.csv",
        columns=TABLE_PROFILE_COLUMNS,
    )

    atomic_csv(
        pd.DataFrame(column_profiles),
        report_folder / "column_profile.csv",
        columns=COLUMN_PROFILE_COLUMNS,
    )

    atomic_csv(
        pd.DataFrame(duplicate_records),
        report_folder / "duplicate_keys.csv",
        columns=DUPLICATE_REPORT_COLUMNS,
    )

    quality_dataframe = pd.DataFrame(quality_issues).reindex(
        columns=QUALITY_REPORT_COLUMNS
    )

    atomic_csv(
        quality_dataframe,
        report_folder / "data_quality_issues.csv",
    )

    issue_total = int(
        quality_dataframe["issue_count"].sum()
    )

    failed_checks = int(
        (quality_dataframe["status"] == "Issue").sum()
    )

    print()
    print("=" * 60)
    print("DATA PROFILING COMPLETED")
    print("=" * 60)
    print(f"Tables profiled: {len(table_profiles)}")
    print(f"Quality checks: {len(quality_dataframe)}")
    print(f"Checks requiring review: {failed_checks}")
    print(f"Total flagged records: {issue_total:,}")
    print(f"Reports saved to: {report_folder}")


def main(data_folder=DATA_FOLDER, report_folder=REPORT_FOLDER):
    reset_profile_state()
    print("=" * 60)
    print("LOGISTICS DATA PROFILING")
    print("=" * 60)
    print(f"Started: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print()

    parquet_files = require_named_files(
        data_folder,
        PROCESSED_TABLES,
        suffix=".parquet",
    )

    for file_path in parquet_files:
        profile_table(file_path)

    run_business_checks(data_folder)
    save_reports(report_folder)


if __name__ == "__main__":
    main()
