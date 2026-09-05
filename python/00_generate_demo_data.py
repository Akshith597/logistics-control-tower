"""Generate a deterministic, relationship-complete demo logistics workbook."""

import argparse
from datetime import date, datetime, timedelta
import hashlib
from pathlib import Path
import random

import pandas as pd

from pipeline_config import PROJECT_ROOT, SHEET_TABLE_PAIRS

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "Logistical_Data.xlsx"
DEFAULT_SEED = 20250830
DEFAULT_SHIPMENTS = 7200


def stable_hash(seed, value):
    """Return a compact deterministic hash suitable for demo row lineage."""
    payload = f"{seed}|{value}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def build_reference_tables():
    customers = []
    customer_names = (
        ("Northstar Medical Supply LLC", "Healthcare", "OH", "High"),
        ("BluePeak Electronics Inc", "Electronics", "FL", "Medium"),
        ("Summit Home Goods Co", "Retail", "CO", "High"),
        ("GreenField Foods LLC", "Food", "GA", "Medium"),
        ("Atlas Industrial Parts Inc", "Manufacturing", "MI", "High"),
        ("Crescent Beauty Group", "Consumer Goods", "WA", "Low"),
    )

    for index, (name, industry, state, tier) in enumerate(
        customer_names,
        start=1,
    ):
        customer_id = f"{10004520 + index}"
        customers.append({
            "erp_customer_id": customer_id,
            "legal_name": name,
            "dba_name": name.split()[0],
            "parent_erp_customer_id": None,
            "industry": industry,
            "customer_status": "Active",
            "payment_terms": "Net 30" if index % 2 else "Net 45",
            "credit_limit_usd": 50000.0 + index * 15000.0,
            "primary_bill_to_state": state,
            "account_owner_email": (
                f"account{index}@example-corp.invalid"
            ),
            "created_date": date(2018, index, min(index * 3, 28)),
            "last_modified_ts": datetime(2025, 12, 15, 9, index),
            "source_system": "ERP",
            "is_test_account": False,
            "notes": None,
            "annual_volume_tier": tier,
        })

    crosswalk = [
        {
            "erp_customer_id": customer["erp_customer_id"],
            "tms_customer_code": f"CUST{index:03d}",
            "is_primary_mapping": True,
            "effective_from": date(2019, 1, 1),
            "effective_to": None,
            "mapping_confidence": "High",
            "notes": None,
        }
        for index, customer in enumerate(customers, start=1)
    ]

    warehouses = [
        {
            "warehouse_id": "WH01",
            "wms_location_code": "CHI-JOL",
            "warehouse_name": "Chicago Central",
            "city": "Joliet",
            "state": "IL",
            "postal_code": "60435",
            "latitude": 41.5250,
            "longitude": -88.0817,
            "timezone": "America/Chicago",
            "daily_outbound_capacity": 1250,
            "is_active": True,
            "source_system": "WMS",
        },
        {
            "warehouse_id": "WH02",
            "wms_location_code": "DAL-FTW",
            "warehouse_name": "Dallas South",
            "city": "Fort Worth",
            "state": "TX",
            "postal_code": "76102",
            "latitude": 32.7555,
            "longitude": -97.3308,
            "timezone": "America/Chicago",
            "daily_outbound_capacity": 1100,
            "is_active": True,
            "source_system": "WMS",
        },
        {
            "warehouse_id": "WH03",
            "wms_location_code": "NJ-EDI",
            "warehouse_name": "New Jersey East",
            "city": "Edison",
            "state": "NJ",
            "postal_code": "08817",
            "latitude": 40.5187,
            "longitude": -74.4121,
            "timezone": "America/New_York",
            "daily_outbound_capacity": 1350,
            "is_active": True,
            "source_system": "WMS",
        },
    ]

    carriers = [
        {
            "carrier_id": "CAR01",
            "scac": "SWLG",
            "carrier_legal_name": "SwiftLine Ground",
            "mode": "Parcel",
            "status": "Active",
            "notes": None,
            "source_system": "TMS",
        },
        {
            "carrier_id": "CAR02",
            "scac": "BLAL",
            "carrier_legal_name": "BlueArrow Logistics",
            "mode": "LTL",
            "status": "Active",
            "notes": None,
            "source_system": "TMS",
        },
        {
            "carrier_id": "CAR03",
            "scac": "NFRG",
            "carrier_legal_name": "North Freight Lines",
            "mode": "FTL",
            "status": "Active",
            "notes": None,
            "source_system": "TMS",
        },
        {
            "carrier_id": "CAR04",
            "scac": "MTSP",
            "carrier_legal_name": "MetroSpeed Parcel",
            "mode": "Parcel",
            "status": "Active",
            "notes": None,
            "source_system": "TMS",
        },
    ]

    return {
        "erp_customers": pd.DataFrame(customers),
        "customer_id_crosswalk": pd.DataFrame(crosswalk),
        "ref_warehouses": pd.DataFrame(warehouses),
        "ref_carriers": pd.DataFrame(carriers),
    }


def build_demo_tables(shipment_count=DEFAULT_SHIPMENTS, seed=DEFAULT_SEED):
    """Build all source tables with deterministic values and valid joins."""
    if shipment_count < 24:
        raise ValueError("shipment_count must be at least 24")

    randomizer = random.Random(seed)
    tables = build_reference_tables()
    customers = tables["erp_customers"].to_dict("records")
    crosswalk = tables["customer_id_crosswalk"].to_dict("records")
    warehouses = tables["ref_warehouses"].to_dict("records")
    carriers = tables["ref_carriers"].to_dict("records")

    destinations = (
        ("Columbus", "OH", "43215", 420.0),
        ("Miami", "FL", "33101", 1180.0),
        ("Denver", "CO", "80202", 910.0),
        ("Atlanta", "GA", "30303", 760.0),
        ("Detroit", "MI", "48201", 380.0),
        ("Seattle", "WA", "98101", 1740.0),
    )
    service_levels = (
        ("STD", "Standard", 5),
        ("EXP", "Expedited", 2),
        ("ECO", "Economy", 7),
    )
    product_catalog = (
        ("SKU-1100", "Medical Supplies", 4.5),
        ("SKU-2200", "Electronics Carton", 2.2),
        ("SKU-3300", "Home Goods Case", 12.0),
        ("SKU-4400", "Food Ingredients", 18.5),
        ("SKU-5500", "Industrial Component", 30.0),
        ("SKU-6600", "Beauty Products", 3.4),
    )

    shipments = []
    shipment_lines = []
    tracking_events = []
    wms_rows = []
    invoice_rows = []
    claim_rows = []
    ticket_rows = []
    survey_rows = []
    event_number = 1
    invoice_number = 1

    for index in range(1, shipment_count + 1):
        shipment_id = f"TMS{200000 + index}"
        sales_order_id = f"SO{700000 + index}"
        customer_index = (index - 1) % len(customers)
        customer = customers[customer_index]
        customer_code = crosswalk[customer_index]["tms_customer_code"]
        warehouse = warehouses[(index * 5) % len(warehouses)]
        carrier = carriers[(index * 7) % len(carriers)]
        destination = destinations[customer_index]
        service_code, service_name, planned_days = service_levels[
            (index - 1) % len(service_levels)
        ]
        ship_date = date(2024, 1, 1) + timedelta(days=(index - 1) * 3)
        create_ts = datetime.combine(ship_date, datetime.min.time())
        create_ts += timedelta(hours=8 + index % 6, minutes=index % 60)
        pickup_ts = create_ts + timedelta(hours=2 + index % 5)
        promised_date = ship_date + timedelta(days=planned_days)
        canceled = index % 31 == 0
        delay_days = (-1, 0, 0, 1, 2, 0, 0)[index % 7]
        delivery_ts = None

        if not canceled:
            delivery_ts = datetime.combine(
                promised_date + timedelta(days=delay_days),
                datetime.min.time(),
            ) + timedelta(hours=10 + index % 8, minutes=index % 60)

        delivered = not canceled
        on_time = None if not delivered else delay_days <= 0
        mode_multiplier = {"Parcel": 1.0, "LTL": 2.8, "FTL": 5.5}[
            carrier["mode"]
        ]
        weight = round(35 + (index % 45) * 18.75 * mode_multiplier, 2)
        lane_miles = destination[3] + (index % 9) * 17.5
        revenue = round(95 + lane_miles * 0.38 * mode_multiplier, 2)
        cost_ratio = 0.68 + (index % 6) * 0.025
        cost = round(revenue * cost_ratio, 2)
        tracking_number = f"TRK{6000000000 + index:010d}"
        pro_number = (
            f"PRO{80000000 + index}" if carrier["mode"] != "Parcel" else None
        )
        bol_number = (
            f"BOL{500000 + index}" if carrier["mode"] == "FTL" else None
        )
        pieces = 1 + index % 12
        short_pick = index % 13 == 0
        line_count = 1 + index % 3

        shipments.append({
            "tms_shipment_id": shipment_id,
            "tms_customer_code": customer_code,
            "erp_customer_id_ref": customer["erp_customer_id"],
            "sales_order_id": sales_order_id,
            "customer_po": f"PO-{40000 + index}",
            "bol_number": bol_number,
            "pro_number": pro_number,
            "tracking_number": tracking_number,
            "origin_warehouse_id": warehouse["warehouse_id"],
            "origin_wms_code": warehouse["wms_location_code"],
            "dest_name": f"{customer['dba_name']} - {destination[0]}",
            "dest_address1": f"{100 + index} Commerce Parkway",
            "dest_city": destination[0],
            "dest_state": destination[1],
            "dest_postal": destination[2],
            "dest_country": "US",
            "is_residential": index % 8 == 0,
            "carrier_id": carrier["carrier_id"],
            "carrier_scac": carrier["scac"],
            "mode": carrier["mode"],
            "service_level_code": service_code,
            "service_level_name": service_name,
            "planned_transit_days": planned_days,
            "lane_miles_est": round(lane_miles, 1),
            "ship_create_date": ship_date,
            "ship_create_ts": create_ts,
            "promised_delivery_date": promised_date,
            "actual_pickup_ts": None if canceled else pickup_ts,
            "actual_delivery_ts": delivery_ts,
            "shipment_status": "CANCELED" if canceled else "DELIVERED",
            "exception_code": "WX" if delay_days > 0 and delivered else None,
            "weight_lb": weight,
            "pieces": pieces,
            "freight_class": None if carrier["mode"] == "Parcel" else 70.0,
            "estimated_revenue_usd": revenue,
            "estimated_cost_usd": cost,
            "currency": "USD",
            "on_time_flag": on_time,
            "is_void": canceled,
            "is_re_tender": False,
            "parent_tms_shipment_id": None,
            "source_system": "TMS",
            "extract_batch_id": f"TMS_DAILY_{ship_date:%Y%m%d}",
            "last_update_ts": (delivery_ts or create_ts) + timedelta(hours=3),
            "row_hash": stable_hash(seed, shipment_id),
        })

        for line_number in range(1, line_count + 1):
            sku, description, unit_weight = product_catalog[
                (index + line_number) % len(product_catalog)
            ]
            ordered = 2 + (index * line_number) % 18
            shipped = ordered - 1 if short_pick and line_number == 1 else ordered
            shipment_lines.append({
                "tms_shipment_id": shipment_id,
                "line_number": line_number,
                "sku": sku,
                "description": description,
                "qty_ordered": ordered,
                "qty_shipped": shipped,
                "unit_weight_lb": unit_weight,
                "hazardous_flag": sku == "SKU-4400" and index % 10 == 0,
                "source_system": "TMS",
            })

        wms_rows.append({
            "wms_outbound_id": f"WMS{700000 + index}",
            "wms_location_code": warehouse["wms_location_code"],
            "sales_order_id": sales_order_id,
            "tms_shipment_id": shipment_id,
            "pick_start_ts": create_ts - timedelta(hours=6),
            "pack_complete_ts": create_ts - timedelta(hours=2),
            "ship_confirm_ts": create_ts,
            "lines_picked": line_count,
            "short_pick_flag": short_pick,
            "inventory_accuracy_snapshot": round(
                0.965 + randomizer.random() * 0.034,
                4,
            ),
            "source_system": "WMS",
        })

        event_plan = [
            ("BOOKED", "Shipment booked", create_ts),
        ]
        if delivered:
            event_plan.append(("PU", "Picked up", pickup_ts))
            if delay_days > 0:
                event_plan.append(
                    (
                        "EXCEPTION",
                        "Weather delay",
                        pickup_ts + timedelta(days=1),
                    )
                )
            event_plan.append(("DLV", "Delivered", delivery_ts))
        else:
            event_plan.append(("CANCEL", "Shipment canceled", create_ts))

        for event_code, event_description, event_ts in event_plan:
            tracking_events.append({
                "column1": f"EVT{event_number}",
                "tms_shipment_id": shipment_id,
                "tracking_number": tracking_number,
                "event_code": event_code,
                "event_description": event_description,
                "event_ts_utc": event_ts + timedelta(hours=5),
                "event_ts_local": event_ts,
                "event_city": (
                    warehouse["city"] if event_code != "DLV" else destination[0]
                ),
                "event_state": (
                    warehouse["state"] if event_code != "DLV" else destination[1]
                ),
                "exception_reason": (
                    "Weather" if event_code == "EXCEPTION" else None
                ),
                "source": "EDI_214",
                "ingested_ts": event_ts + timedelta(minutes=12),
            })
            event_number += 1

        if delivered:
            invoice_date = delivery_ts.date() + timedelta(days=1)
            for invoice_type, amount in (
                ("CUSTOMER", revenue),
                ("CARRIER_BILL", cost),
            ):
                invoice_rows.append({
                    "invoice_id": f"INV{900000 + invoice_number}",
                    "invoice_type": invoice_type,
                    "erp_customer_id": customer["erp_customer_id"],
                    "tms_shipment_id": shipment_id,
                    "sales_order_id": sales_order_id,
                    "pro_number": pro_number,
                    "invoice_date": invoice_date,
                    "gl_post_date": invoice_date + timedelta(days=1),
                    "line_amount_usd": amount,
                    "accessorial_amount_usd": (
                        18.0
                        if delay_days > 0
                        and invoice_type == "CARRIER_BILL"
                        else 0.0
                    ),
                    "fuel_surcharge_usd": (
                        round(amount * 0.08, 2)
                        if invoice_type == "CARRIER_BILL"
                        else 0.0
                    ),
                    "tax_usd": round(revenue * 0.04, 2)
                    if invoice_type == "CUSTOMER"
                    else 0.0,
                    "currency": "USD",
                    "payment_status": "Paid" if index % 9 else "Open",
                    "dispute_flag": index % 37 == 0,
                    "source_system": "ERP",
                })
                invoice_number += 1

        if delivered and index % 17 == 0:
            requested = round(175 + index * 4.25, 2)
            claim_rows.append({
                "claim_id": f"CLM{800 + len(claim_rows) + 1}",
                "tms_shipment_id": shipment_id,
                "pro_number": pro_number,
                "claim_type": "Damage" if index % 2 else "Shortage",
                "filed_date": delivery_ts.date() + timedelta(days=4),
                "claim_amount_requested_usd": requested,
                "claim_amount_paid_usd": round(requested * 0.72, 2),
                "claim_status": "Paid",
                "carrier_id": carrier["carrier_id"],
                "source_system": "Claims",
                "adjuster_notes": "Demo claim reviewed",
            })

        if delivered and index % 11 == 0:
            categories = (
                "Late Delivery",
                "Damage",
                "Short Shipment",
                "Billing Question",
            )
            category = categories[(index // 11) % len(categories)]
            ticket_rows.append({
                "ticket_id": f"TKT-{5000 + len(ticket_rows) + 1}",
                "opened_ts": delivery_ts + timedelta(hours=8),
                "erp_customer_id": customer["erp_customer_id"],
                "tms_customer_code": customer_code,
                "tms_shipment_id": shipment_id,
                "tracking_number": tracking_number,
                "channel": "Email" if index % 2 else "Phone",
                "category_raw": category,
                "severity": "High" if delay_days > 0 else "Medium",
                "status": "Resolved",
                "subject": category,
                "description_free_text": (
                    "Synthetic customer issue for portfolio analysis."
                ),
                "resolution_hours": float(6 + index % 42),
                "source_system": "CRM",
            })

        if delivered and index % 7 == 0:
            csat = 2 if delay_days > 0 else 5
            nps = 4 if delay_days > 0 else 9
            sent_ts = delivery_ts + timedelta(hours=12)
            survey_rows.append({
                "response_id": f"CSAT{61000000 + len(survey_rows) + 1}",
                "survey_sent_ts": sent_ts,
                "response_ts": sent_ts + timedelta(days=2),
                "erp_customer_id": customer["erp_customer_id"],
                "tms_shipment_id": shipment_id,
                "csat_score_1_to_5": csat,
                "nps_score_0_to_10": nps,
                "comment": (
                    "Delivery was late." if delay_days > 0 else "Great service."
                ),
                "source_system": "Medallia_Export",
            })

    tables.update({
        "tms_shipments": pd.DataFrame(shipments),
        "tms_shipment_lines": pd.DataFrame(shipment_lines),
        "carrier_tracking_events": pd.DataFrame(tracking_events),
        "wms_outbound": pd.DataFrame(wms_rows),
        "erp_invoices": pd.DataFrame(invoice_rows),
        "claims": pd.DataFrame(claim_rows),
        "crm_tickets": pd.DataFrame(ticket_rows),
        "csat_survey_responses": pd.DataFrame(survey_rows),
    })
    return tables


def display_column_name(column_name):
    """Create readable Excel headers that normalize back to the contract name."""
    return column_name.replace("_", " ").title()


def write_demo_workbook(
    output_file=DEFAULT_OUTPUT,
    *,
    shipment_count=DEFAULT_SHIPMENTS,
    seed=DEFAULT_SEED,
    force=False,
):
    """Write all demo tables to the workbook expected by the extractor."""
    output_file = Path(output_file)
    if output_file.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing workbook:\n{output_file}\n"
            "Pass --force only when replacing it with synthetic demo data."
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = output_file.with_name(f".{output_file.name}.tmp.xlsx")
    tables = build_demo_tables(shipment_count=shipment_count, seed=seed)

    try:
        with pd.ExcelWriter(temporary_file, engine="openpyxl") as writer:
            writer.book.properties.title = (
                "Logistics Control Tower - Synthetic Demo Data"
            )
            writer.book.properties.creator = "Logistics Control Tower"
            writer.book.properties.created = datetime(2025, 1, 1)
            writer.book.properties.modified = datetime(2025, 1, 1)

            for sheet_name, table_name in SHEET_TABLE_PAIRS:
                dataframe = tables[table_name].rename(
                    columns=display_column_name
                )
                dataframe.to_excel(
                    writer,
                    sheet_name=sheet_name,
                    index=False,
                )
                worksheet = writer.sheets[sheet_name]
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions

        temporary_file.replace(output_file)
    finally:
        temporary_file.unlink(missing_ok=True)

    row_total = sum(len(dataframe) for dataframe in tables.values())
    print("=" * 68)
    print("SYNTHETIC LOGISTICS WORKBOOK CREATED")
    print("=" * 68)
    print(f"Output: {output_file}")
    print(f"Seed: {seed}")
    print(f"Shipments: {shipment_count:,}")
    print(f"Sheets: {len(tables)}")
    print(f"Total source rows: {row_total:,}")
    return output_file


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate deterministic demo data for the logistics project."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Workbook destination.",
    )
    parser.add_argument(
        "--shipments",
        type=int,
        default=DEFAULT_SHIPMENTS,
        help=f"Number of shipments (minimum 24; default: {DEFAULT_SHIPMENTS}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed (default: {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing workbook with synthetic data.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    write_demo_workbook(
        args.output,
        shipment_count=args.shipments,
        seed=args.seed,
        force=args.force,
    )


if __name__ == "__main__":
    main()
