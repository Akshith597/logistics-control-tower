"""Fixture tests for the SQL transformation layer.

Each test builds a handful of raw rows chosen to isolate one rule, runs the
real ``sql/*.sql`` files over them, and asserts the exact expected output.
Where the end-to-end pipeline test proves the model holds together on a full
dataset, these prove the individual rules are right on the awkward inputs a
generated dataset rarely produces: duplicate delivery scans, partially
extracted quantities, invoices that only match on a fallback key, and
customers reachable only through the crosswalk.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from sql_fixtures import (
    BASE_CARRIER,
    BASE_CROSSWALK,
    BASE_CUSTOMER,
    BASE_WAREHOUSE,
    PROJECT_ROOT,
    RAW_TABLE_COLUMNS,
    SQL_DIR,
    create_fixture_database,
    fetch_dict,
    fetch_one,
    shipment,
)

REFERENCE_TABLES = {
    "erp_customers": [BASE_CUSTOMER],
    "customer_id_crosswalk": [BASE_CROSSWALK],
    "ref_warehouses": [BASE_WAREHOUSE],
    "ref_carriers": [BASE_CARRIER],
}


def fixture(**tables):
    """Build a fixture database on top of the shared reference rows."""
    return create_fixture_database({**REFERENCE_TABLES, **tables})


class SqlFixtureTestCase(unittest.TestCase):
    """Track fixture connections so each test closes its own database."""

    def setUp(self):
        self.connections = []

    def tearDown(self):
        for connection in self.connections:
            connection.close()

    def build(self, **tables):
        connection = fixture(**tables)
        self.connections.append(connection)
        return connection

    def fact(self, connection, shipment_key):
        return fetch_dict(
            connection,
            "SELECT * FROM mart.fact_shipment WHERE shipment_key = ?",
            [shipment_key],
        )


# ============================================================
# Tracking event deduplication
# ============================================================


class TrackingEventDeduplicationTests(SqlFixtureTestCase):
    def test_repeat_delivery_scans_collapse_to_the_latest_ingest(self):
        """Three DLV scans for one shipment must leave exactly one event."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            carrier_tracking_events=[
                {
                    "column1": "E1",
                    "tms_shipment_id": "S1",
                    "event_code": "DLV",
                    "event_ts_utc": "2024-01-03 15:00:00",
                    "ingested_ts": "2024-01-03 16:00:00",
                    "event_city": "Denver",
                },
                {
                    "column1": "E2",
                    "tms_shipment_id": "S1",
                    "event_code": "DLV",
                    "event_ts_utc": "2024-01-03 15:00:00",
                    "ingested_ts": "2024-01-04 09:00:00",
                    "event_city": "Denver replay",
                },
                {
                    "column1": "E3",
                    "tms_shipment_id": "S1",
                    "event_code": "DLV",
                    "event_ts_utc": "2024-01-03 15:00:00",
                    "ingested_ts": "2024-01-02 09:00:00",
                    "event_city": "Denver early",
                },
            ],
        )

        kept = connection.execute(
            """
            SELECT tracking_event_id, event_city
            FROM staging.stg_tracking_events_dedup
            """
        ).fetchall()

        self.assertEqual(kept, [("E2", "Denver replay")])
        self.assertEqual(
            fetch_one(
                connection,
                """
                SELECT COUNT(*)
                FROM staging.stg_tracking_events
                WHERE duplicate_event_flag = TRUE
                """,
            ),
            2,
        )

    def test_delivery_scans_are_deduplicated_per_shipment_not_globally(self):
        """Two shipments each keep their own delivery scan."""
        connection = self.build(
            tms_shipments=[shipment("S1"), shipment("S2")],
            carrier_tracking_events=[
                {
                    "column1": "E1",
                    "tms_shipment_id": "S1",
                    "event_code": "DLV",
                    "ingested_ts": "2024-01-03 16:00:00",
                },
                {
                    "column1": "E2",
                    "tms_shipment_id": "S2",
                    "event_code": "DLV",
                    "ingested_ts": "2024-01-03 16:00:00",
                },
            ],
        )

        self.assertEqual(
            fetch_one(
                connection,
                "SELECT COUNT(*) FROM staging.stg_tracking_events_dedup",
            ),
            2,
        )

    def test_non_delivery_scans_are_kept_even_when_they_repeat(self):
        """Only DLV collapses per shipment; movement scans stay distinct."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            carrier_tracking_events=[
                {
                    "column1": "E1",
                    "tms_shipment_id": "S1",
                    "event_code": "PU",
                    "ingested_ts": "2024-01-01 12:00:00",
                },
                {
                    "column1": "E2",
                    "tms_shipment_id": "S1",
                    "event_code": "PU",
                    "ingested_ts": "2024-01-01 13:00:00",
                },
                {
                    "column1": "E3",
                    "tms_shipment_id": "S1",
                    "event_code": "ARR",
                    "ingested_ts": "2024-01-02 08:00:00",
                },
            ],
        )

        self.assertEqual(
            fetch_one(
                connection,
                "SELECT COUNT(*) FROM staging.stg_tracking_events_dedup",
            ),
            3,
        )

    def test_events_for_unknown_shipments_are_flagged_not_dropped(self):
        """Unmatched events stay visible for data-quality reporting."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            carrier_tracking_events=[
                {
                    "column1": "E1",
                    "tms_shipment_id": "GHOST",
                    "event_code": "DLV",
                    "ingested_ts": "2024-01-03 16:00:00",
                },
            ],
        )

        self.assertEqual(
            fetch_one(
                connection,
                """
                SELECT COUNT(*)
                FROM staging.stg_tracking_events
                WHERE shipment_match_flag = FALSE
                """,
            ),
            1,
        )


# ============================================================
# Fill rate and OTIF
# ============================================================


class FillRateTests(SqlFixtureTestCase):
    def test_one_missing_shipped_quantity_makes_the_fill_rate_unknown(self):
        """A partial extract must not be reported as a short shipment."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            tms_shipment_lines=[
                {
                    "tms_shipment_id": "S1",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": "10",
                },
                {
                    "tms_shipment_id": "S1",
                    "line_number": "2",
                    "sku": "B",
                    "qty_ordered": "10",
                    "qty_shipped": None,
                },
            ],
        )

        row = self.fact(connection, "S1")
        self.assertIsNone(row["shipment_fill_rate"])
        self.assertIsNone(row["otif_flag"])
        self.assertEqual(row["missing_shipped_quantity_lines"], 1)
        self.assertTrue(row["final_on_time_flag"])

    def test_fill_rate_is_a_ratio_of_sums_not_an_average_of_ratios(self):
        """10/10 plus 5/20 is 0.5 across units, not 0.625 across lines."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            tms_shipment_lines=[
                {
                    "tms_shipment_id": "S1",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": "10",
                },
                {
                    "tms_shipment_id": "S1",
                    "line_number": "2",
                    "sku": "B",
                    "qty_ordered": "20",
                    "qty_shipped": "5",
                },
            ],
        )

        row = self.fact(connection, "S1")
        self.assertAlmostEqual(row["shipment_fill_rate"], 0.5)
        self.assertFalse(row["otif_flag"])

    def test_a_shipment_with_no_lines_has_no_fill_rate_or_otif_result(self):
        connection = self.build(tms_shipments=[shipment("S1")])

        row = self.fact(connection, "S1")
        self.assertIsNone(row["shipment_fill_rate"])
        self.assertIsNone(row["otif_flag"])
        self.assertEqual(row["shipment_line_count"], 0)

    def test_over_shipment_still_counts_as_in_full(self):
        """Fill rate above 1 satisfies the documented ``>= 1`` OTIF rule."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            tms_shipment_lines=[
                {
                    "tms_shipment_id": "S1",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": "12",
                },
            ],
        )

        row = self.fact(connection, "S1")
        self.assertAlmostEqual(row["shipment_fill_rate"], 1.2)
        self.assertTrue(row["otif_flag"])
        self.assertEqual(row["over_shipped_lines"], 1)

    def test_a_late_but_complete_shipment_fails_otif(self):
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    promised_delivery_date="2024-01-02",
                    actual_delivery_ts="2024-01-05 09:00:00",
                ),
            ],
            tms_shipment_lines=[
                {
                    "tms_shipment_id": "S1",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": "10",
                },
            ],
        )

        row = self.fact(connection, "S1")
        self.assertFalse(row["final_on_time_flag"])
        self.assertFalse(row["otif_flag"])
        self.assertEqual(row["days_late"], 3)


class KpiDenominatorTests(SqlFixtureTestCase):
    def test_otd_and_otif_use_different_denominators(self):
        """An on-time shipment with an unknown fill rate counts only in OTD."""
        connection = self.build(
            tms_shipments=[
                shipment("S1"),
                shipment("S2"),
                shipment(
                    "S9",
                    ship_create_date="2024-06-01",
                    ship_create_ts="2024-06-01 08:00:00",
                    promised_delivery_date="2024-06-05",
                    actual_delivery_ts="2024-06-04 10:00:00",
                ),
            ],
            tms_shipment_lines=[
                {
                    "tms_shipment_id": "S1",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": "10",
                },
                {
                    "tms_shipment_id": "S2",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": None,
                },
            ],
        )

        kpis = fetch_dict(connection, "SELECT * FROM mart.vw_executive_kpis")

        # S1 and S2 are both KPI eligible and both delivered on time, but only
        # S1 has a resolvable fill rate, so OTIF sees one fewer shipment.
        self.assertEqual(kpis["otd_eligible_shipments"], 2)
        self.assertEqual(kpis["otif_eligible_shipments"], 1)
        self.assertEqual(kpis["on_time_delivery_rate"], 1.0)
        self.assertEqual(kpis["otif_rate"], 1.0)

    def test_shipments_inside_the_extract_lag_are_not_kpi_eligible(self):
        """The most recent three ship days are still settling in the source."""
        connection = self.build(
            tms_shipments=[
                shipment("S_OLD", ship_create_date="2024-01-01"),
                shipment("S_EDGE", ship_create_date="2024-01-07"),
                shipment("S_NEW", ship_create_date="2024-01-10"),
            ],
        )

        eligibility = dict(
            connection.execute(
                """
                SELECT shipment_key, official_kpi_eligible_flag
                FROM mart.fact_shipment
                """
            ).fetchall()
        )

        self.assertTrue(eligibility["S_OLD"])
        self.assertTrue(eligibility["S_EDGE"])
        self.assertFalse(eligibility["S_NEW"])

    def test_gross_margin_percentage_is_a_ratio_of_sums(self):
        """Margin % must not be the average of per-shipment margins."""
        connection = self.build(
            tms_shipments=[shipment("S1"), shipment("S2")],
            erp_invoices=[
                _invoice("I1", "S1", "CUSTOMER", line_amount_usd="100.00"),
                _invoice("I2", "S1", "CARRIER_BILL", line_amount_usd="50.00"),
                _invoice("I3", "S2", "CUSTOMER", line_amount_usd="900.00"),
                _invoice("I4", "S2", "CARRIER_BILL", line_amount_usd="800.00"),
            ],
        )

        kpis = fetch_dict(connection, "SELECT * FROM mart.vw_executive_kpis")

        # Ratio of sums: 150 / 1000 = 15%.
        # Average of ratios would be (50% + 11.1%) / 2 = 30.6%.
        self.assertEqual(float(kpis["customer_revenue_usd"]), 1000.0)
        self.assertEqual(float(kpis["gross_margin_usd"]), 150.0)
        self.assertAlmostEqual(kpis["gross_margin_percentage"], 0.15)


# ============================================================
# Fallback matching
# ============================================================


def _invoice(invoice_id, shipment_id, invoice_type, **overrides):
    row = {
        "invoice_id": invoice_id,
        "invoice_type": invoice_type,
        "erp_customer_id": "C001",
        "tms_shipment_id": shipment_id,
        "invoice_date": "2024-01-10",
        "gl_post_date": "2024-01-10",
        "line_amount_usd": "100.00",
        "currency": "USD",
        "payment_status": "PAID",
        "dispute_flag": "false",
        "source_system": "ERP",
    }
    row.update(overrides)
    return row


class InvoiceMatchingTests(SqlFixtureTestCase):
    def test_match_methods_fall_back_in_documented_precedence(self):
        connection = self.build(
            tms_shipments=[shipment("S1")],
            erp_invoices=[
                _invoice("I_DIRECT", "S1", "CUSTOMER"),
                _invoice(
                    "I_SO",
                    None,
                    "CUSTOMER",
                    sales_order_id="SO-S1",
                ),
                _invoice(
                    "I_PRO",
                    None,
                    "CUSTOMER",
                    pro_number="PRO-S1",
                ),
                _invoice(
                    "I_NONE",
                    None,
                    "CUSTOMER",
                    sales_order_id="SO-UNKNOWN",
                    pro_number="PRO-UNKNOWN",
                ),
            ],
        )

        methods = dict(
            connection.execute(
                """
                SELECT invoice_id, shipment_match_method
                FROM staging.stg_invoices
                """
            ).fetchall()
        )

        self.assertEqual(methods["I_DIRECT"], "TMS SHIPMENT ID")
        self.assertEqual(methods["I_SO"], "SALES ORDER FALLBACK")
        self.assertEqual(methods["I_PRO"], "PRO NUMBER FALLBACK")
        self.assertEqual(methods["I_NONE"], "UNMATCHED")

    def test_sales_order_fallback_prefers_the_most_recently_updated_shipment(
        self,
    ):
        """A reused sales order must resolve to exactly one shipment."""
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S_OLD",
                    sales_order_id="SO-SHARED",
                    last_update_ts="2024-01-02 00:00:00",
                ),
                shipment(
                    "S_NEW",
                    sales_order_id="SO-SHARED",
                    last_update_ts="2024-01-09 00:00:00",
                ),
            ],
            erp_invoices=[
                _invoice(
                    "I_SO",
                    None,
                    "CUSTOMER",
                    sales_order_id="SO-SHARED",
                ),
            ],
        )

        matches = connection.execute(
            """
            SELECT invoice_id, matched_tms_shipment_id
            FROM staging.stg_invoices
            """
        ).fetchall()

        self.assertEqual(matches, [("I_SO", "S_NEW")])

    def test_carrier_and_customer_amounts_land_in_separate_measures(self):
        connection = self.build(
            tms_shipments=[shipment("S1")],
            erp_invoices=[
                _invoice(
                    "I_CUST",
                    "S1",
                    "CUSTOMER",
                    line_amount_usd="500.00",
                    accessorial_amount_usd="25.00",
                    fuel_surcharge_usd="15.00",
                    tax_usd="40.00",
                ),
                _invoice(
                    "I_CARR",
                    "S1",
                    "CARRIER_BILL",
                    line_amount_usd="300.00",
                    accessorial_amount_usd="10.00",
                    fuel_surcharge_usd="20.00",
                ),
            ],
        )

        row = self.fact(connection, "S1")

        # Tax is excluded from revenue; accessorial and fuel columns report the
        # carrier bill only, because customer accessorials are inside revenue.
        self.assertEqual(float(row["customer_revenue_usd"]), 540.0)
        self.assertEqual(float(row["carrier_cost_usd"]), 330.0)
        self.assertEqual(float(row["total_accessorial_usd"]), 10.0)
        self.assertEqual(float(row["total_fuel_surcharge_usd"]), 20.0)
        self.assertEqual(float(row["gross_margin_usd"]), 210.0)


class WmsMatchingTests(SqlFixtureTestCase):
    def test_wms_rows_fall_back_to_the_sales_order(self):
        connection = self.build(
            tms_shipments=[shipment("S1")],
            wms_outbound=[
                {
                    "wms_outbound_id": "W_DIRECT",
                    "wms_location_code": "CHI1",
                    "tms_shipment_id": "S1",
                    "sales_order_id": "SO-S1",
                    "pick_start_ts": "2024-01-01 06:00:00",
                    "pack_complete_ts": "2024-01-01 07:30:00",
                    "ship_confirm_ts": "2024-01-01 08:00:00",
                },
                {
                    "wms_outbound_id": "W_FALLBACK",
                    "wms_location_code": "CHI1",
                    "sales_order_id": "SO-S1",
                },
                {
                    "wms_outbound_id": "W_NONE",
                    "wms_location_code": "CHI1",
                    "sales_order_id": "SO-GHOST",
                },
            ],
        )

        methods = dict(
            connection.execute(
                """
                SELECT wms_outbound_id, shipment_match_method
                FROM staging.stg_wms_outbound
                """
            ).fetchall()
        )

        self.assertEqual(methods["W_DIRECT"], "TMS SHIPMENT ID")
        self.assertEqual(methods["W_FALLBACK"], "SALES ORDER FALLBACK")
        self.assertEqual(methods["W_NONE"], "UNMATCHED")

    def test_out_of_order_warehouse_timestamps_are_flagged_not_negative(self):
        """A pack before a pick must yield NULL hours, never a negative one."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            wms_outbound=[
                {
                    "wms_outbound_id": "W1",
                    "wms_location_code": "CHI1",
                    "tms_shipment_id": "S1",
                    "pick_start_ts": "2024-01-01 09:00:00",
                    "pack_complete_ts": "2024-01-01 06:00:00",
                    "ship_confirm_ts": "2024-01-01 10:00:00",
                },
            ],
        )

        row = fetch_dict(
            connection,
            "SELECT * FROM staging.stg_wms_outbound WHERE wms_outbound_id='W1'",
        )

        self.assertTrue(row["invalid_timestamp_sequence_flag"])
        self.assertIsNone(row["pick_to_pack_hours"])
        self.assertEqual(row["total_warehouse_cycle_hours"], 1.0)


# ============================================================
# Customer resolution
# ============================================================


class CustomerResolutionTests(SqlFixtureTestCase):
    def test_crosswalk_resolves_a_shipment_with_no_direct_customer_id(self):
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    erp_customer_id_ref=None,
                    tms_customer_code="NW-001",
                ),
            ],
        )

        self.assertEqual(self.fact(connection, "S1")["customer_key"], "C001")

    def test_customer_codes_match_across_punctuation_and_case(self):
        """``nw 001`` and ``NW-001`` normalize to the same crosswalk key."""
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    erp_customer_id_ref=None,
                    tms_customer_code=" nw 001 ",
                ),
            ],
        )

        self.assertEqual(self.fact(connection, "S1")["customer_key"], "C001")

    def test_the_primary_crosswalk_row_wins_over_a_later_secondary_row(self):
        connection = self.build(
            customer_id_crosswalk=[
                {
                    "erp_customer_id": "C001",
                    "tms_customer_code": "NW-001",
                    "is_primary_mapping": "true",
                    "effective_from": "2023-01-01",
                },
                {
                    "erp_customer_id": "C999",
                    "tms_customer_code": "NW-001",
                    "is_primary_mapping": "false",
                    "effective_from": "2024-06-01",
                },
            ],
            tms_shipments=[
                shipment("S1", erp_customer_id_ref=None),
            ],
        )

        self.assertEqual(self.fact(connection, "S1")["customer_key"], "C001")

    def test_a_direct_customer_id_wins_over_the_crosswalk(self):
        connection = self.build(
            erp_customers=[
                BASE_CUSTOMER,
                {**BASE_CUSTOMER, "erp_customer_id": "C002"},
            ],
            tms_shipments=[
                shipment(
                    "S1",
                    erp_customer_id_ref="C002",
                    tms_customer_code="NW-001",
                ),
            ],
        )

        self.assertEqual(self.fact(connection, "S1")["customer_key"], "C002")

    def test_an_unresolvable_customer_lands_on_the_unknown_member(self):
        """The fact must still join, so the shipment is never lost."""
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    erp_customer_id_ref="GHOST",
                    tms_customer_code="ZZ-999",
                ),
            ],
        )

        self.assertEqual(self.fact(connection, "S1")["customer_key"], "UNKNOWN")
        self.assertEqual(
            fetch_one(
                connection,
                """
                SELECT COUNT(*)
                FROM mart.fact_shipment AS fact
                LEFT JOIN mart.dim_customer AS dimension
                    ON fact.customer_key = dimension.customer_key
                WHERE dimension.customer_key IS NULL
                """,
            ),
            0,
        )


# ============================================================
# Shipment eligibility
# ============================================================


class ShipmentEligibilityTests(SqlFixtureTestCase):
    def test_a_re_tendered_parent_is_replaced_by_its_child(self):
        """Counting both the original and the re-tender would double count."""
        connection = self.build(
            tms_shipments=[
                shipment("S_PARENT"),
                shipment(
                    "S_CHILD",
                    parent_tms_shipment_id="S_PARENT",
                    is_re_tender="true",
                ),
            ],
        )

        keys = [
            row[0]
            for row in connection.execute(
                "SELECT shipment_key FROM mart.fact_shipment ORDER BY 1"
            ).fetchall()
        ]

        self.assertEqual(keys, ["S_CHILD"])

    def test_voided_and_cancelled_shipments_never_reach_the_fact(self):
        connection = self.build(
            tms_shipments=[
                shipment("S_LIVE"),
                shipment("S_VOID_FLAG", is_void="true"),
                shipment("S_CANCELLED", shipment_status="CANCELLED"),
                shipment("S_REPLACED", shipment_status="REPLACED"),
            ],
        )

        keys = [
            row[0]
            for row in connection.execute(
                "SELECT shipment_key FROM mart.fact_shipment ORDER BY 1"
            ).fetchall()
        ]

        self.assertEqual(keys, ["S_LIVE"])

    def test_the_source_on_time_flag_overrides_the_calculated_one(self):
        """The carrier's own result wins; the disagreement is still counted."""
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    promised_delivery_date="2024-01-02",
                    actual_delivery_ts="2024-01-05 09:00:00",
                    on_time_flag="true",
                ),
            ],
        )

        row = self.fact(connection, "S1")
        self.assertTrue(row["final_on_time_flag"])
        self.assertEqual(
            fetch_one(
                connection,
                """
                SELECT metric_value
                FROM quality.shipment_quality_summary
                WHERE metric
                      = 'Source and calculated on-time results conflict'
                """,
            ),
            1,
        )

    def test_an_undelivered_shipment_has_no_on_time_result(self):
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    shipment_status="IN_TRANSIT",
                    actual_delivery_ts=None,
                ),
            ],
        )

        row = self.fact(connection, "S1")
        self.assertIsNone(row["final_on_time_flag"])
        self.assertIsNone(row["days_late"])


# ============================================================
# Fan-out
# ============================================================


class FanOutTests(SqlFixtureTestCase):
    def test_many_children_still_produce_one_fact_row_with_summed_measures(
        self,
    ):
        """The classic star-schema failure: joins multiplying the measures."""
        connection = self.build(
            tms_shipments=[shipment("S1")],
            tms_shipment_lines=[
                {
                    "tms_shipment_id": "S1",
                    "line_number": str(number),
                    "sku": f"SKU{number}",
                    "qty_ordered": "10",
                    "qty_shipped": "10",
                }
                for number in range(1, 4)
            ],
            carrier_tracking_events=[
                {
                    "column1": f"E{number}",
                    "tms_shipment_id": "S1",
                    "event_code": "ARR",
                    "ingested_ts": f"2024-01-0{number} 08:00:00",
                }
                for number in range(1, 4)
            ],
            wms_outbound=[
                {
                    "wms_outbound_id": f"W{number}",
                    "wms_location_code": "CHI1",
                    "tms_shipment_id": "S1",
                }
                for number in range(1, 3)
            ],
            erp_invoices=[
                _invoice("I1", "S1", "CUSTOMER", line_amount_usd="100.00"),
                _invoice("I2", "S1", "CUSTOMER", line_amount_usd="200.00"),
                _invoice("I3", "S1", "CARRIER_BILL", line_amount_usd="120.00"),
            ],
            claims=[
                {
                    "claim_id": "CL1",
                    "tms_shipment_id": "S1",
                    "claim_type": "DAMAGE",
                    "filed_date": "2024-01-10",
                    "claim_amount_requested_usd": "80.00",
                    "claim_amount_paid_usd": "30.00",
                    "claim_status": "PAID",
                    "carrier_id": "CAR1",
                },
                {
                    "claim_id": "CL2",
                    "tms_shipment_id": "S1",
                    "claim_type": "SHORTAGE",
                    "filed_date": "2024-01-11",
                    "claim_amount_requested_usd": "40.00",
                    "claim_amount_paid_usd": "20.00",
                    "claim_status": "PAID",
                    "carrier_id": "CAR1",
                },
            ],
            crm_tickets=[
                {
                    "ticket_id": f"T{number}",
                    "opened_ts": "2024-01-06 09:00:00",
                    "erp_customer_id": "C001",
                    "tms_shipment_id": "S1",
                    "channel": "EMAIL",
                    "category_raw": "Late delivery",
                    "severity": "HIGH",
                    "status": "CLOSED",
                    "resolution_hours": "4",
                }
                for number in range(1, 3)
            ],
            csat_survey_responses=[
                {
                    "response_id": f"R{number}",
                    "survey_sent_ts": "2024-01-06 09:00:00",
                    "response_ts": "2024-01-07 09:00:00",
                    "erp_customer_id": "C001",
                    "tms_shipment_id": "S1",
                    "csat_score_1_to_5": "4",
                    "nps_score_0_to_10": "9",
                }
                for number in range(1, 3)
            ],
        )

        self.assertEqual(
            fetch_one(connection, "SELECT COUNT(*) FROM mart.fact_shipment"),
            1,
        )

        row = self.fact(connection, "S1")
        self.assertEqual(row["shipment_line_count"], 3)
        self.assertEqual(row["invoice_count"], 3)
        self.assertEqual(row["claim_count"], 2)
        self.assertEqual(row["ticket_count"], 2)
        self.assertEqual(row["survey_response_count"], 2)
        self.assertEqual(float(row["customer_revenue_usd"]), 300.0)
        self.assertEqual(float(row["carrier_cost_usd"]), 120.0)
        self.assertEqual(float(row["claims_paid_usd"]), 50.0)
        self.assertEqual(
            float(row["gross_margin_usd"]),
            300.0 - 120.0 - 50.0,
        )
        self.assertAlmostEqual(row["shipment_fill_rate"], 1.0)


# ============================================================
# Survey scoring
# ============================================================


def _survey(response_id, **overrides):
    row = {
        "response_id": response_id,
        "survey_sent_ts": "2024-01-06 09:00:00",
        "response_ts": "2024-01-07 09:00:00",
        "erp_customer_id": "C001",
        "tms_shipment_id": "S1",
        "source_system": "CRM",
    }
    row.update(overrides)
    return row


class SurveyScoringTests(SqlFixtureTestCase):
    def test_out_of_range_csat_scores_are_excluded_from_the_average(self):
        connection = self.build(
            tms_shipments=[shipment("S1")],
            csat_survey_responses=[
                _survey("R1", csat_score_1_to_5="5"),
                _survey("R2", csat_score_1_to_5="3"),
                _survey("R3", csat_score_1_to_5="0"),
                _survey("R4", csat_score_1_to_5="6"),
                _survey("R5", csat_score_1_to_5=None),
            ],
        )

        row = self.fact(connection, "S1")
        self.assertEqual(row["survey_response_count"], 5)
        self.assertEqual(row["valid_csat_response_count"], 2)
        self.assertAlmostEqual(row["average_csat_score"], 4.0)

    def test_nps_categories_follow_the_standard_thresholds(self):
        connection = self.build(
            tms_shipments=[shipment("S1")],
            csat_survey_responses=[
                _survey("R1", nps_score_0_to_10="10"),
                _survey("R2", nps_score_0_to_10="9"),
                _survey("R3", nps_score_0_to_10="8"),
                _survey("R4", nps_score_0_to_10="7"),
                _survey("R5", nps_score_0_to_10="6"),
                _survey("R6", nps_score_0_to_10="0"),
                _survey("R7", nps_score_0_to_10="11"),
            ],
        )

        row = self.fact(connection, "S1")
        self.assertEqual(row["promoter_count"], 2)
        self.assertEqual(row["passive_count"], 2)
        self.assertEqual(row["detractor_count"], 2)

    def test_a_shipment_with_no_survey_reports_zero_not_null_counts(self):
        connection = self.build(tms_shipments=[shipment("S1")])

        row = self.fact(connection, "S1")
        self.assertEqual(row["survey_response_count"], 0)
        self.assertEqual(row["valid_csat_response_count"], 0)
        self.assertIsNone(row["average_csat_score"])


# ============================================================
# Dimension keys
# ============================================================


class DimensionKeyTests(SqlFixtureTestCase):
    def test_missing_lane_attributes_become_unknown_segments(self):
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    origin_warehouse_id=None,
                    dest_state=None,
                    dest_postal=None,
                ),
            ],
        )

        row = self.fact(connection, "S1")
        self.assertEqual(
            row["lane_key"],
            "UNKNOWN|US|UNKNOWN|Denver|UNKNOWN",
        )
        self.assertEqual(
            fetch_one(
                connection,
                "SELECT COUNT(*) FROM mart.dim_lane WHERE lane_key = ?",
                [row["lane_key"]],
            ),
            1,
        )

    def test_country_synonyms_collapse_to_a_single_lane(self):
        """``USA`` and ``United States`` must not split one lane in two."""
        connection = self.build(
            tms_shipments=[
                shipment("S1", dest_country="USA"),
                shipment("S2", dest_country="United States"),
                shipment("S3", dest_country="us"),
            ],
        )

        self.assertEqual(
            fetch_one(
                connection,
                "SELECT COUNT(DISTINCT lane_key) FROM mart.fact_shipment",
            ),
            1,
        )

    def test_service_key_falls_back_from_code_to_name_to_unknown(self):
        connection = self.build(
            tms_shipments=[
                shipment("S1", mode="LTL", service_level_code="STD"),
                shipment(
                    "S2",
                    mode="LTL",
                    service_level_code=None,
                    service_level_name="Standard",
                ),
                shipment(
                    "S3",
                    mode="LTL",
                    service_level_code=None,
                    service_level_name=None,
                ),
                shipment(
                    "S4",
                    mode=None,
                    service_level_code=None,
                    service_level_name=None,
                ),
            ],
        )

        keys = dict(
            connection.execute(
                "SELECT shipment_key, service_key FROM mart.fact_shipment"
            ).fetchall()
        )

        self.assertEqual(keys["S1"], "LTL|CODE:STD")
        self.assertEqual(keys["S2"], "LTL|NAME:STANDARD")
        self.assertEqual(keys["S3"], "LTL|UNKNOWN")
        self.assertEqual(keys["S4"], "UNKNOWN|UNKNOWN")

    def test_conformed_dimensions_carry_an_explicit_unknown_member(self):
        """Resolution can fail for these four, so the member must pre-exist."""
        connection = self.build(tms_shipments=[shipment("S1")])

        dimensions = (
            ("dim_customer", "customer_key", "UNKNOWN"),
            ("dim_carrier", "carrier_key", "UNKNOWN"),
            ("dim_warehouse", "warehouse_key", "UNKNOWN"),
            ("dim_service", "service_key", "UNKNOWN|UNKNOWN"),
        )

        for table_name, key_column, unknown_key in dimensions:
            with self.subTest(dimension=table_name):
                self.assertEqual(
                    fetch_one(
                        connection,
                        f"""
                        SELECT COUNT(*)
                        FROM mart.{table_name}
                        WHERE {key_column} = ?
                        """,
                        [unknown_key],
                    ),
                    1,
                )

    def test_a_fully_unknown_lane_still_materializes_in_the_dimension(self):
        """dim_lane is derived from the fact's own rows, so it cannot orphan."""
        connection = self.build(
            tms_shipments=[
                shipment(
                    "S1",
                    origin_warehouse_id=None,
                    dest_country=None,
                    dest_state=None,
                    dest_city=None,
                    dest_postal=None,
                ),
            ],
        )

        self.assertEqual(
            self.fact(connection, "S1")["lane_key"],
            "UNKNOWN|UNKNOWN|UNKNOWN|UNKNOWN|UNKNOWN",
        )
        self.assertEqual(
            fetch_one(
                connection,
                """
                SELECT COUNT(*)
                FROM mart.dim_lane
                WHERE lane_key = 'UNKNOWN|UNKNOWN|UNKNOWN|UNKNOWN|UNKNOWN'
                """,
            ),
            1,
        )


# ============================================================
# Model invariants on adversarial input
# ============================================================


class ValidationSuiteTests(SqlFixtureTestCase):
    def _adversarial_fixture(self):
        """One fixture containing every awkward case the tests above isolate."""
        return self.build(
            tms_shipments=[
                shipment("S_CLEAN"),
                shipment("S_LATE", actual_delivery_ts="2024-01-09 09:00:00"),
                shipment(
                    "S_NO_CUSTOMER",
                    erp_customer_id_ref="GHOST",
                    tms_customer_code="ZZ-999",
                ),
                shipment(
                    "S_NO_LANE",
                    origin_warehouse_id=None,
                    dest_state=None,
                    dest_city=None,
                ),
                shipment(
                    "S_IN_TRANSIT",
                    shipment_status="IN_TRANSIT",
                    actual_delivery_ts=None,
                ),
                shipment("S_VOID", is_void="true"),
                shipment("S_PARENT"),
                shipment("S_CHILD", parent_tms_shipment_id="S_PARENT"),
                shipment("S_RECENT", ship_create_date="2024-02-01"),
            ],
            tms_shipment_lines=[
                {
                    "tms_shipment_id": "S_CLEAN",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": "10",
                },
                {
                    "tms_shipment_id": "S_LATE",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "10",
                    "qty_shipped": None,
                },
                {
                    "tms_shipment_id": "GHOST_SHIPMENT",
                    "line_number": "1",
                    "sku": "A",
                    "qty_ordered": "5",
                    "qty_shipped": "5",
                },
            ],
            carrier_tracking_events=[
                {
                    "column1": "E1",
                    "tms_shipment_id": "S_CLEAN",
                    "event_code": "DLV",
                    "ingested_ts": "2024-01-03 16:00:00",
                },
                {
                    "column1": "E2",
                    "tms_shipment_id": "S_CLEAN",
                    "event_code": "DLV",
                    "ingested_ts": "2024-01-04 16:00:00",
                },
            ],
            erp_invoices=[
                _invoice("I1", "S_CLEAN", "CUSTOMER", accessorial_amount_usd="12.34"),
                _invoice(
                    "I2",
                    "S_CLEAN",
                    "CARRIER_BILL",
                    accessorial_amount_usd="7.89",
                    fuel_surcharge_usd="1.11",
                ),
                _invoice("I3", None, "CUSTOMER", sales_order_id="SO-S_LATE"),
                _invoice("I4", None, "CUSTOMER", pro_number="PRO-S_LATE"),
                _invoice("I5", None, "CUSTOMER", sales_order_id="SO-GHOST"),
            ],
            claims=[
                {
                    "claim_id": "CL1",
                    "tms_shipment_id": "S_LATE",
                    "claim_type": "DAMAGE",
                    "filed_date": "2024-01-10",
                    "claim_amount_requested_usd": "80.00",
                    "claim_amount_paid_usd": None,
                    "claim_status": "OPEN",
                    "carrier_id": "CAR1",
                },
            ],
            csat_survey_responses=[
                _survey("R1", tms_shipment_id="S_CLEAN", csat_score_1_to_5="9"),
                _survey(
                    "R2",
                    tms_shipment_id="S_CLEAN",
                    csat_score_1_to_5="4",
                    nps_score_0_to_10="10",
                ),
            ],
        )

    def test_every_critical_validation_passes_on_adversarial_input(self):
        connection = self._adversarial_fixture()
        validation_sql = (SQL_DIR / "07_validate_model.sql").read_text(encoding="utf-8")

        results = connection.execute(validation_sql).fetchall()
        failures = [row[0] for row in results if row[3] != "PASS"]

        self.assertEqual(failures, [])
        self.assertGreaterEqual(len(results), 28)
        test_names = {row[0] for row in results}
        self.assertIn("aggregate gross margin is positive", test_names)
        self.assertIn(
            "shipment dates stay within the declared 2024-2025 fixture window",
            test_names,
        )

    def test_the_portfolio_analysis_query_runs_against_the_model(self):
        """The showcase SQL must stay in step with the schema it queries."""
        connection = self._adversarial_fixture()
        analysis_sql = (SQL_DIR / "08_portfolio_analysis.sql").read_text(
            encoding="utf-8"
        )

        connection.execute(analysis_sql)


# ============================================================
# Schema contract
# ============================================================


class RawContractTests(unittest.TestCase):
    def test_the_demo_generator_matches_the_declared_raw_contract(self):
        """These fixtures and the generator must describe the same schema."""
        specification = importlib.util.spec_from_file_location(
            "demo_data_for_contract",
            PROJECT_ROOT / "python" / "00_generate_demo_data.py",
        )
        demo = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(demo)

        generated = demo.build_demo_tables(shipment_count=24)

        self.assertEqual(
            sorted(generated),
            sorted(RAW_TABLE_COLUMNS),
        )
        for table_name, frame in generated.items():
            with self.subTest(table=table_name):
                self.assertEqual(
                    tuple(frame.columns),
                    RAW_TABLE_COLUMNS[table_name],
                )


if __name__ == "__main__":
    unittest.main()
