-- ============================================================
-- Logistics Control Tower
-- Star schema and shipment-level analytical fact
-- ============================================================

CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS quality;


-- ============================================================
-- DATE DIMENSION
-- ============================================================

CREATE OR REPLACE TABLE mart.dim_date AS

WITH date_bounds AS (
    SELECT
        MIN(ship_create_date) AS minimum_date,

        MAX(
            GREATEST(
                ship_create_date,
                promised_delivery_date,
                CAST(actual_delivery_ts AS DATE)
            )
        ) AS maximum_date

    FROM staging.stg_shipments
),

calendar AS (
    SELECT CAST(calendar_date AS DATE) AS date_key

    FROM date_bounds,

    GENERATE_SERIES(
        minimum_date,
        maximum_date,
        INTERVAL 1 DAY
    ) AS dates(calendar_date)
)

SELECT
    date_key,
    EXTRACT(YEAR FROM date_key)::INTEGER AS year,
    EXTRACT(QUARTER FROM date_key)::INTEGER AS quarter,
    EXTRACT(MONTH FROM date_key)::INTEGER AS month_number,
    STRFTIME(date_key, '%B') AS month_name,
    STRFTIME(date_key, '%Y-%m') AS year_month,
    EXTRACT(WEEK FROM date_key)::INTEGER AS week_number,
    EXTRACT(DAY FROM date_key)::INTEGER AS day_of_month,
    EXTRACT(DOW FROM date_key)::INTEGER AS day_of_week_number,
    STRFTIME(date_key, '%A') AS day_name,

    CASE
        WHEN EXTRACT(DOW FROM date_key) IN (0, 6)
        THEN TRUE
        ELSE FALSE
    END AS weekend_flag

FROM calendar;


-- ============================================================
-- CUSTOMER DIMENSION
-- ============================================================

CREATE OR REPLACE TABLE mart.dim_customer AS

SELECT
    erp_customer_id AS customer_key,
    erp_customer_id,
    legal_name,
    dba_name,
    parent_erp_customer_id,
    industry,
    customer_status,
    payment_terms,
    credit_limit_usd,
    primary_bill_to_state,
    account_owner_email,
    annual_volume_tier

FROM staging.stg_customers

WHERE is_test_account = FALSE

UNION ALL

SELECT
    'UNKNOWN',
    'UNKNOWN',
    'Unknown Customer',
    NULL,
    NULL,
    'UNKNOWN',
    'UNKNOWN',
    NULL,
    NULL,
    NULL,
    NULL,
    'UNKNOWN';


-- ============================================================
-- CARRIER DIMENSION
-- ============================================================

CREATE OR REPLACE TABLE mart.dim_carrier AS

SELECT
    carrier_id AS carrier_key,
    carrier_id,
    scac,
    carrier_legal_name,
    mode AS primary_mode,
    carrier_status

FROM staging.stg_carriers

UNION ALL

SELECT
    'UNKNOWN',
    'UNKNOWN',
    NULL,
    'Unknown Carrier',
    'UNKNOWN',
    'UNKNOWN';


-- ============================================================
-- WAREHOUSE DIMENSION
-- ============================================================

CREATE OR REPLACE TABLE mart.dim_warehouse AS

SELECT
    warehouse_id AS warehouse_key,
    warehouse_id,
    wms_location_code,
    warehouse_name,
    city,
    state,
    postal_code,
    latitude,
    longitude,
    timezone,
    daily_outbound_capacity,
    is_active

FROM staging.stg_warehouses

UNION ALL

SELECT
    'UNKNOWN',
    'UNKNOWN',
    NULL,
    'Unknown Warehouse',
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    FALSE;


-- ============================================================
-- SERVICE DIMENSION
-- ============================================================

CREATE OR REPLACE TABLE mart.dim_service AS

WITH service_rows AS (
    SELECT
        COALESCE(mode, 'UNKNOWN') AS mode,

        COALESCE(service_level_code, 'UNKNOWN')
            AS service_level_code,

        COALESCE(service_level_name, 'UNKNOWN')
            AS service_level_name,

        COALESCE(mode, 'UNKNOWN')
            || '|'
            || CASE
                WHEN service_level_code IS NOT NULL
                THEN 'CODE:' || service_level_code
                WHEN service_level_name IS NOT NULL
                THEN 'NAME:' || service_level_name
                ELSE 'UNKNOWN'
            END AS service_key,

        planned_transit_days

    FROM staging.stg_shipments

    WHERE final_live_shipment_flag = TRUE
)

SELECT
    service_key,
    mode,
    MODE(service_level_code) AS service_level_code,
    MODE(service_level_name) AS service_level_name,

    -- Transit time varies by shipment and lane. Keep the
    -- shipment-level value in the fact and expose a stable,
    -- representative value in this one-row-per-service dimension.
    CAST(
        ROUND(MEDIAN(planned_transit_days))
        AS INTEGER
    ) AS planned_transit_days

FROM service_rows

GROUP BY
    service_key,
    mode

HAVING service_key <> 'UNKNOWN|UNKNOWN'

UNION

SELECT
    'UNKNOWN|UNKNOWN',
    'UNKNOWN',
    'UNKNOWN',
    'UNKNOWN',
    NULL;


-- ============================================================
-- LANE DIMENSION
-- ============================================================

CREATE OR REPLACE TABLE mart.dim_lane AS

SELECT DISTINCT
    COALESCE(origin_warehouse_id, 'UNKNOWN')
        || '|'
        || COALESCE(dest_country, 'UNKNOWN')
        || '|'
        || COALESCE(dest_state, 'UNKNOWN')
        || '|'
        || COALESCE(dest_city, 'UNKNOWN')
        || '|'
        || COALESCE(dest_postal, 'UNKNOWN')
        AS lane_key,

    COALESCE(origin_warehouse_id, 'UNKNOWN')
        AS origin_warehouse_id,

    COALESCE(dest_state, 'UNKNOWN')
        AS destination_state,

    COALESCE(dest_city, 'UNKNOWN')
        AS destination_city,

    COALESCE(dest_postal, 'UNKNOWN')
        AS destination_postal,

    COALESCE(dest_country, 'UNKNOWN')
        AS destination_country

FROM staging.stg_shipments

WHERE final_live_shipment_flag = TRUE;


-- ============================================================
-- SHIPMENT-LEVEL AGGREGATES
-- Each CTE must return no more than one row per shipment.
-- ============================================================

CREATE OR REPLACE TABLE mart.fact_shipment AS

WITH customer_crosswalk AS (
    SELECT
        tms_customer_code_normalized,
        erp_customer_id

    FROM staging.stg_customer_crosswalk

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY tms_customer_code_normalized
        ORDER BY
            is_primary_mapping DESC,
            effective_from DESC NULLS LAST
    ) = 1
),

resolved_shipments AS (
    SELECT
        shipment.*,

        COALESCE(
            direct_customer.erp_customer_id,
            crosswalk_customer.erp_customer_id,
            'UNKNOWN'
        ) AS resolved_customer_key,

        COALESCE(
            resolved_customer.is_test_account,
            FALSE
        ) AS resolved_test_account_flag

    FROM staging.stg_shipments AS shipment

    LEFT JOIN staging.stg_customers AS direct_customer
        ON shipment.erp_customer_id_ref
           = direct_customer.erp_customer_id

    LEFT JOIN customer_crosswalk AS crosswalk_customer
        ON direct_customer.erp_customer_id IS NULL
       AND shipment.tms_customer_code_normalized
           = crosswalk_customer.tms_customer_code_normalized

    LEFT JOIN staging.stg_customers AS resolved_customer
        ON COALESCE(
            direct_customer.erp_customer_id,
            crosswalk_customer.erp_customer_id
        ) = resolved_customer.erp_customer_id
),

line_aggregate AS (
    SELECT
        tms_shipment_id,

        COUNT(*) AS shipment_line_count,

        SUM(qty_ordered) AS total_quantity_ordered,

        SUM(qty_shipped)
            FILTER (WHERE qty_shipped IS NOT NULL)
            AS total_quantity_shipped,

        COUNT(*)
            FILTER (WHERE qty_shipped IS NULL)
            AS missing_shipped_quantity_lines,

        COUNT(*)
            FILTER (
                WHERE quantity_status = 'SHORT SHIPPED'
            ) AS short_shipped_lines,

        COUNT(*)
            FILTER (
                WHERE quantity_status = 'OVER SHIPPED'
            ) AS over_shipped_lines,

        SUM(calculated_line_weight_lb)
            AS calculated_line_weight_lb,

        BOOL_OR(hazardous_flag)
            AS hazardous_shipment_flag,

        CASE
            WHEN COUNT(*)
                 FILTER (WHERE qty_shipped IS NULL) > 0
            THEN NULL

            WHEN SUM(qty_ordered) > 0
            THEN SUM(qty_shipped) * 1.0
                 / SUM(qty_ordered)

            ELSE NULL
        END AS shipment_fill_rate

    FROM staging.stg_shipment_lines

    GROUP BY tms_shipment_id
),

event_aggregate AS (
    SELECT
        tms_shipment_id,

        COUNT(*) AS tracking_event_count,

        MIN(event_ts_local)
            FILTER (WHERE event_code = 'PU')
            AS first_pickup_event_ts,

        MAX(event_ts_local)
            FILTER (WHERE event_code = 'DLV')
            AS final_delivery_event_ts,

        COUNT(*)
            FILTER (
                WHERE exception_reason IS NOT NULL
                   OR event_code IN (
                       'EXC',
                       'DELAY',
                       'LATE'
                   )
            ) AS tracking_exception_count

    FROM staging.stg_tracking_events_dedup

    GROUP BY tms_shipment_id
),

wms_aggregate AS (
    SELECT
        matched_tms_shipment_id AS tms_shipment_id,

        COUNT(*) AS wms_record_count,

        MAX(total_warehouse_cycle_hours)
            AS warehouse_cycle_hours,

        MAX(pick_to_pack_hours)
            AS pick_to_pack_hours,

        MAX(pack_to_ship_hours)
            AS pack_to_ship_hours,

        BOOL_OR(short_pick_flag)
            AS short_pick_flag,

        AVG(inventory_accuracy_snapshot)
            AS average_inventory_accuracy

    FROM staging.stg_wms_outbound

    WHERE shipment_match_flag = TRUE

    GROUP BY matched_tms_shipment_id
),

invoice_aggregate AS (
    SELECT
        matched_tms_shipment_id AS tms_shipment_id,

        COUNT(*) AS invoice_count,

        SUM(customer_revenue_usd)
            AS customer_revenue_usd,

        SUM(carrier_cost_usd)
            AS carrier_cost_usd,

        -- Dashboard cost components include carrier bills only.
        -- Customer accessorials are already included in revenue.
        SUM(accessorial_amount_usd)
            FILTER (WHERE invoice_type = 'CARRIER_BILL')
            AS total_accessorial_usd,

        SUM(fuel_surcharge_usd)
            FILTER (WHERE invoice_type = 'CARRIER_BILL')
            AS total_fuel_surcharge_usd,

        COUNT(*)
            FILTER (WHERE dispute_flag = TRUE)
            AS disputed_invoice_count

    FROM staging.stg_invoices

    WHERE shipment_match_flag = TRUE

    GROUP BY matched_tms_shipment_id
),

claim_aggregate AS (
    SELECT
        matched_tms_shipment_id AS tms_shipment_id,

        COUNT(*) AS claim_count,

        SUM(claim_amount_requested_usd)
            AS claims_requested_usd,

        SUM(
            COALESCE(claim_amount_paid_usd, 0)
        ) AS claims_paid_usd

    FROM staging.stg_claims

    WHERE shipment_match_flag = TRUE

    GROUP BY matched_tms_shipment_id
),

ticket_aggregate AS (
    SELECT
        matched_tms_shipment_id AS tms_shipment_id,

        COUNT(*) AS ticket_count,

        COUNT(*)
            FILTER (
                WHERE severity IN ('HIGH', 'CRITICAL')
            ) AS severe_ticket_count,

        AVG(resolution_hours)
            FILTER (
                WHERE valid_resolution_time_flag = TRUE
            ) AS average_resolution_hours,

        COUNT(*)
            FILTER (
                WHERE category_normalized
                      = 'LATE DELIVERY'
            ) AS late_delivery_ticket_count,

        COUNT(*)
            FILTER (
                WHERE category_normalized = 'DAMAGE'
            ) AS damage_ticket_count

    FROM staging.stg_crm_tickets

    WHERE shipment_match_flag = TRUE

    GROUP BY matched_tms_shipment_id
),

survey_aggregate AS (
    SELECT
        tms_shipment_id,

        COUNT(*) AS survey_response_count,

        COUNT(*)
            FILTER (WHERE valid_csat_flag = TRUE)
            AS valid_csat_response_count,

        AVG(csat_score)
            FILTER (WHERE valid_csat_flag = TRUE)
            AS average_csat_score,

        COUNT(*)
            FILTER (
                WHERE nps_category = 'PROMOTER'
            ) AS promoter_count,

        COUNT(*)
            FILTER (
                WHERE nps_category = 'PASSIVE'
            ) AS passive_count,

        COUNT(*)
            FILTER (
                WHERE nps_category = 'DETRACTOR'
            ) AS detractor_count,

        CASE
            WHEN COUNT(*)
                 FILTER (WHERE valid_nps_flag = TRUE) > 0
            THEN
                100.0
                * (
                    COUNT(*)
                        FILTER (
                            WHERE nps_category = 'PROMOTER'
                        )
                    -
                    COUNT(*)
                        FILTER (
                            WHERE nps_category = 'DETRACTOR'
                        )
                )
                /
                COUNT(*)
                    FILTER (WHERE valid_nps_flag = TRUE)

            ELSE NULL
        END AS shipment_nps

    FROM staging.stg_csat_responses

    WHERE shipment_match_flag = TRUE

    GROUP BY tms_shipment_id
),

fact_base AS (
    SELECT
        shipment.tms_shipment_id
            AS shipment_key,

        shipment.tms_shipment_id,

        shipment.resolved_customer_key
            AS customer_key,

        COALESCE(
            shipment.carrier_id,
            'UNKNOWN'
        ) AS carrier_key,

        COALESCE(
            shipment.origin_warehouse_id,
            'UNKNOWN'
        ) AS warehouse_key,

        COALESCE(shipment.mode, 'UNKNOWN')
            || '|'
            || CASE
                WHEN shipment.service_level_code IS NOT NULL
                THEN 'CODE:' || shipment.service_level_code
                WHEN shipment.service_level_name IS NOT NULL
                THEN 'NAME:' || shipment.service_level_name
                ELSE 'UNKNOWN'
            END AS service_key,

        COALESCE(
            shipment.origin_warehouse_id,
            'UNKNOWN'
        )
            || '|'
            || COALESCE(
                shipment.dest_country,
                'UNKNOWN'
            )
            || '|'
            || COALESCE(
                shipment.dest_state,
                'UNKNOWN'
            )
            || '|'
            || COALESCE(
                shipment.dest_city,
                'UNKNOWN'
            )
            || '|'
            || COALESCE(
                shipment.dest_postal,
                'UNKNOWN'
            ) AS lane_key,

        shipment.ship_create_date AS ship_date,
        shipment.promised_delivery_date,
        CAST(
            shipment.actual_delivery_ts AS DATE
        ) AS actual_delivery_date,

        shipment.sales_order_id,
        shipment.customer_po,
        shipment.bol_number,
        shipment.pro_number,
        shipment.tracking_number,

        shipment.dest_city,
        shipment.dest_state,
        shipment.dest_postal,
        shipment.dest_country,

        shipment.mode,
        shipment.service_level_code,
        shipment.service_level_name,

        shipment.shipment_status,
        shipment.exception_code,

        shipment.planned_transit_days,
        shipment.lane_miles_est,
        shipment.weight_lb,
        shipment.pieces,

        shipment.final_on_time_flag,
        shipment.days_late,
        shipment.official_kpi_eligible_flag,

        COALESCE(
            line.shipment_line_count,
            0
        ) AS shipment_line_count,

        line.total_quantity_ordered,
        line.total_quantity_shipped,
        line.missing_shipped_quantity_lines,
        line.short_shipped_lines,
        line.over_shipped_lines,
        line.shipment_fill_rate,
        line.calculated_line_weight_lb,
        line.hazardous_shipment_flag,

        COALESCE(
            event.tracking_event_count,
            0
        ) AS tracking_event_count,

        event.first_pickup_event_ts,
        event.final_delivery_event_ts,

        COALESCE(
            event.tracking_exception_count,
            0
        ) AS tracking_exception_count,

        COALESCE(
            wms.wms_record_count,
            0
        ) AS wms_record_count,

        wms.warehouse_cycle_hours,
        wms.pick_to_pack_hours,
        wms.pack_to_ship_hours,
        wms.short_pick_flag,
        wms.average_inventory_accuracy,

        COALESCE(
            invoice.invoice_count,
            0
        ) AS invoice_count,

        COALESCE(
            invoice.customer_revenue_usd,
            0
        ) AS customer_revenue_usd,

        COALESCE(
            invoice.carrier_cost_usd,
            0
        ) AS carrier_cost_usd,

        COALESCE(
            invoice.total_accessorial_usd,
            0
        ) AS total_accessorial_usd,

        COALESCE(
            invoice.total_fuel_surcharge_usd,
            0
        ) AS total_fuel_surcharge_usd,

        COALESCE(
            invoice.disputed_invoice_count,
            0
        ) AS disputed_invoice_count,

        COALESCE(
            claim.claim_count,
            0
        ) AS claim_count,

        COALESCE(
            claim.claims_requested_usd,
            0
        ) AS claims_requested_usd,

        COALESCE(
            claim.claims_paid_usd,
            0
        ) AS claims_paid_usd,

        COALESCE(
            ticket.ticket_count,
            0
        ) AS ticket_count,

        COALESCE(
            ticket.severe_ticket_count,
            0
        ) AS severe_ticket_count,

        ticket.average_resolution_hours,

        COALESCE(
            ticket.late_delivery_ticket_count,
            0
        ) AS late_delivery_ticket_count,

        COALESCE(
            ticket.damage_ticket_count,
            0
        ) AS damage_ticket_count,

        COALESCE(
            survey.survey_response_count,
            0
        ) AS survey_response_count,

        COALESCE(
            survey.valid_csat_response_count,
            0
        ) AS valid_csat_response_count,

        survey.average_csat_score,
        survey.promoter_count,
        survey.passive_count,
        survey.detractor_count,
        survey.shipment_nps

    FROM resolved_shipments AS shipment

    LEFT JOIN line_aggregate AS line
        ON shipment.tms_shipment_id
           = line.tms_shipment_id

    LEFT JOIN event_aggregate AS event
        ON shipment.tms_shipment_id
           = event.tms_shipment_id

    LEFT JOIN wms_aggregate AS wms
        ON shipment.tms_shipment_id
           = wms.tms_shipment_id

    LEFT JOIN invoice_aggregate AS invoice
        ON shipment.tms_shipment_id
           = invoice.tms_shipment_id

    LEFT JOIN claim_aggregate AS claim
        ON shipment.tms_shipment_id
           = claim.tms_shipment_id

    LEFT JOIN ticket_aggregate AS ticket
        ON shipment.tms_shipment_id
           = ticket.tms_shipment_id

    LEFT JOIN survey_aggregate AS survey
        ON shipment.tms_shipment_id
           = survey.tms_shipment_id

    WHERE shipment.final_live_shipment_flag = TRUE
      AND shipment.resolved_test_account_flag = FALSE
)

SELECT
    fact_base.*,

    customer_revenue_usd
        - carrier_cost_usd
        - claims_paid_usd
        AS gross_margin_usd,

    CASE
        WHEN customer_revenue_usd <> 0
        THEN (
            customer_revenue_usd
            - carrier_cost_usd
            - claims_paid_usd
        ) / customer_revenue_usd
        ELSE NULL
    END AS gross_margin_percentage,

    CASE
        WHEN final_on_time_flag IS NULL
          OR shipment_fill_rate IS NULL
        THEN NULL

        WHEN final_on_time_flag = TRUE
         AND shipment_fill_rate >= 1
        THEN TRUE

        ELSE FALSE
    END AS otif_flag,

    CASE
        WHEN ticket_count > 0
        THEN TRUE
        ELSE FALSE
    END AS complaint_flag,

    CASE
        WHEN claim_count > 0
        THEN TRUE
        ELSE FALSE
    END AS claim_flag

FROM fact_base;


-- ============================================================
-- STAR-SCHEMA QUALITY SUMMARY
-- ============================================================

CREATE OR REPLACE TABLE quality.star_schema_summary AS

SELECT
    'Fact shipment rows' AS metric,
    COUNT(*) AS metric_value
FROM mart.fact_shipment

UNION ALL

SELECT
    'Duplicate fact shipment keys',
    COUNT(*)
FROM (
    SELECT shipment_key
    FROM mart.fact_shipment
    GROUP BY shipment_key
    HAVING COUNT(*) > 1
)

UNION ALL

SELECT
    'Official KPI shipments',
    COUNT(*)
FROM mart.fact_shipment
WHERE official_kpi_eligible_flag = TRUE

UNION ALL

SELECT
    'Unknown customers',
    COUNT(*)
FROM mart.fact_shipment
WHERE customer_key = 'UNKNOWN'

UNION ALL

SELECT
    'Unknown carriers',
    COUNT(*)
FROM mart.fact_shipment
WHERE carrier_key = 'UNKNOWN'

UNION ALL

SELECT
    'Unknown warehouses',
    COUNT(*)
FROM mart.fact_shipment
WHERE warehouse_key = 'UNKNOWN'

UNION ALL

SELECT
    'Shipments missing fill rate',
    COUNT(*)
FROM mart.fact_shipment
WHERE shipment_fill_rate IS NULL

UNION ALL

SELECT
    'Shipments with invoice data',
    COUNT(*)
FROM mart.fact_shipment
WHERE invoice_count > 0

UNION ALL

SELECT
    'Shipments with claims',
    COUNT(*)
FROM mart.fact_shipment
WHERE claim_count > 0

UNION ALL

SELECT
    'Shipments with CRM tickets',
    COUNT(*)
FROM mart.fact_shipment
WHERE ticket_count > 0

UNION ALL

SELECT
    'Shipments with CSAT responses',
    COUNT(*)
FROM mart.fact_shipment
WHERE survey_response_count > 0;
