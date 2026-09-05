-- ============================================================
-- Logistics Control Tower
-- Staging Layer: reference data and shipments
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS quality;


-- ============================================================
-- CUSTOMER MASTER
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_customers AS
SELECT
    NULLIF(TRIM(CAST(erp_customer_id AS VARCHAR)), '')
        AS erp_customer_id,

    NULLIF(TRIM(legal_name), '')
        AS legal_name,

    NULLIF(TRIM(dba_name), '')
        AS dba_name,

    NULLIF(TRIM(CAST(parent_erp_customer_id AS VARCHAR)), '')
        AS parent_erp_customer_id,

    NULLIF(TRIM(industry), '')
        AS industry,

    UPPER(NULLIF(TRIM(customer_status), ''))
        AS customer_status,

    NULLIF(TRIM(payment_terms), '')
        AS payment_terms,

    TRY_CAST(credit_limit_usd AS DECIMAL(18, 2))
        AS credit_limit_usd,

    UPPER(NULLIF(TRIM(primary_bill_to_state), ''))
        AS primary_bill_to_state,

    LOWER(NULLIF(TRIM(account_owner_email), ''))
        AS account_owner_email,

    TRY_CAST(created_date AS DATE)
        AS created_date,

    TRY_CAST(last_modified_ts AS TIMESTAMP)
        AS last_modified_ts,

    COALESCE(
        TRY_CAST(is_test_account AS BOOLEAN),
        FALSE
    ) AS is_test_account,

    NULLIF(TRIM(CAST(notes AS VARCHAR)), '')
        AS notes,

    UPPER(NULLIF(TRIM(annual_volume_tier), ''))
        AS annual_volume_tier,

    NULLIF(TRIM(source_system), '')
        AS source_system

FROM raw.erp_customers;


-- ============================================================
-- CUSTOMER CROSSWALK
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_customer_crosswalk AS
SELECT
    NULLIF(TRIM(CAST(erp_customer_id AS VARCHAR)), '')
        AS erp_customer_id,

    NULLIF(TRIM(tms_customer_code), '')
        AS tms_customer_code_raw,

    UPPER(
        REPLACE(
            REPLACE(TRIM(tms_customer_code), '-', ''),
            ' ',
            ''
        )
    ) AS tms_customer_code_normalized,

    COALESCE(
        TRY_CAST(is_primary_mapping AS BOOLEAN),
        FALSE
    ) AS is_primary_mapping,

    TRY_CAST(effective_from AS DATE)
        AS effective_from,

    TRY_CAST(effective_to AS DATE)
        AS effective_to,

    UPPER(NULLIF(TRIM(mapping_confidence), ''))
        AS mapping_confidence,

    NULLIF(TRIM(CAST(notes AS VARCHAR)), '')
        AS notes

FROM raw.customer_id_crosswalk;


-- ============================================================
-- WAREHOUSE REFERENCE
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_warehouses AS
SELECT
    NULLIF(TRIM(warehouse_id), '')
        AS warehouse_id,

    UPPER(NULLIF(TRIM(wms_location_code), ''))
        AS wms_location_code,

    NULLIF(TRIM(warehouse_name), '')
        AS warehouse_name,

    NULLIF(TRIM(city), '')
        AS city,

    UPPER(NULLIF(TRIM(state), ''))
        AS state,

    NULLIF(TRIM(CAST(postal_code AS VARCHAR)), '')
        AS postal_code,

    TRY_CAST(latitude AS DOUBLE)
        AS latitude,

    TRY_CAST(longitude AS DOUBLE)
        AS longitude,

    NULLIF(TRIM(timezone), '')
        AS timezone,

    TRY_CAST(daily_outbound_capacity AS INTEGER)
        AS daily_outbound_capacity,

    COALESCE(
        TRY_CAST(is_active AS BOOLEAN),
        FALSE
    ) AS is_active,

    NULLIF(TRIM(source_system), '')
        AS source_system

FROM raw.ref_warehouses;


-- ============================================================
-- CARRIER REFERENCE
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_carriers AS
SELECT
    NULLIF(TRIM(carrier_id), '')
        AS carrier_id,

    UPPER(NULLIF(TRIM(scac), ''))
        AS scac,

    NULLIF(TRIM(carrier_legal_name), '')
        AS carrier_legal_name,

    UPPER(NULLIF(TRIM(mode), ''))
        AS mode,

    UPPER(NULLIF(TRIM(status), ''))
        AS carrier_status,

    NULLIF(TRIM(CAST(notes AS VARCHAR)), '')
        AS notes,

    NULLIF(TRIM(source_system), '')
        AS source_system

FROM raw.ref_carriers;


-- ============================================================
-- SHIPMENT STAGING
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_shipments AS

WITH normalized AS (
    SELECT
        NULLIF(TRIM(tms_shipment_id), '')
            AS tms_shipment_id,

        NULLIF(TRIM(tms_customer_code), '')
            AS tms_customer_code_raw,

        UPPER(
            REPLACE(
                REPLACE(TRIM(tms_customer_code), '-', ''),
                ' ',
                ''
            )
        ) AS tms_customer_code_normalized,

        NULLIF(TRIM(CAST(erp_customer_id_ref AS VARCHAR)), '')
            AS erp_customer_id_ref,

        NULLIF(TRIM(sales_order_id), '')
            AS sales_order_id,

        NULLIF(TRIM(customer_po), '')
            AS customer_po,

        NULLIF(TRIM(bol_number), '')
            AS bol_number,

        NULLIF(TRIM(pro_number), '')
            AS pro_number,

        NULLIF(TRIM(tracking_number), '')
            AS tracking_number,

        NULLIF(TRIM(origin_warehouse_id), '')
            AS origin_warehouse_id,

        UPPER(NULLIF(TRIM(origin_wms_code), ''))
            AS origin_wms_code,

        NULLIF(TRIM(dest_name), '')
            AS dest_name,

        NULLIF(TRIM(dest_city), '')
            AS dest_city,

        UPPER(NULLIF(TRIM(dest_state), ''))
            AS dest_state,

        NULLIF(TRIM(CAST(dest_postal AS VARCHAR)), '')
            AS dest_postal,

        CASE
            WHEN UPPER(TRIM(dest_country)) IN (
                'US',
                'USA',
                'UNITED STATES',
                'UNITED STATES OF AMERICA'
            )
            THEN 'US'
            ELSE UPPER(NULLIF(TRIM(dest_country), ''))
        END AS dest_country,

        COALESCE(
            TRY_CAST(is_residential AS BOOLEAN),
            FALSE
        ) AS is_residential,

        NULLIF(TRIM(carrier_id), '')
            AS carrier_id,

        UPPER(NULLIF(TRIM(carrier_scac), ''))
            AS carrier_scac,

        UPPER(NULLIF(TRIM(mode), ''))
            AS mode,

        UPPER(NULLIF(TRIM(service_level_code), ''))
            AS service_level_code,

        UPPER(NULLIF(TRIM(service_level_name), ''))
            AS service_level_name,

        TRY_CAST(planned_transit_days AS INTEGER)
            AS planned_transit_days,

        TRY_CAST(lane_miles_est AS DOUBLE)
            AS lane_miles_est,

        TRY_CAST(ship_create_date AS DATE)
            AS ship_create_date,

        TRY_CAST(ship_create_ts AS TIMESTAMP)
            AS ship_create_ts,

        TRY_CAST(promised_delivery_date AS DATE)
            AS promised_delivery_date,

        TRY_CAST(actual_pickup_ts AS TIMESTAMP)
            AS actual_pickup_ts,

        TRY_CAST(actual_delivery_ts AS TIMESTAMP)
            AS actual_delivery_ts,

        UPPER(NULLIF(TRIM(shipment_status), ''))
            AS shipment_status,

        UPPER(NULLIF(TRIM(exception_code), ''))
            AS exception_code,

        TRY_CAST(weight_lb AS DOUBLE)
            AS weight_lb,

        TRY_CAST(pieces AS INTEGER)
            AS pieces,

        TRY_CAST(freight_class AS DOUBLE)
            AS freight_class,

        TRY_CAST(estimated_revenue_usd AS DECIMAL(18, 2))
            AS estimated_revenue_usd,

        TRY_CAST(estimated_cost_usd AS DECIMAL(18, 2))
            AS estimated_cost_usd,

        UPPER(NULLIF(TRIM(currency), ''))
            AS currency,

        TRY_CAST(on_time_flag AS BOOLEAN)
            AS source_on_time_flag,

        COALESCE(
            TRY_CAST(is_void AS BOOLEAN),
            FALSE
        ) AS is_void,

        COALESCE(
            TRY_CAST(is_re_tender AS BOOLEAN),
            FALSE
        ) AS is_re_tender,

        NULLIF(TRIM(parent_tms_shipment_id), '')
            AS parent_tms_shipment_id,

        NULLIF(TRIM(source_system), '')
            AS source_system,

        NULLIF(TRIM(extract_batch_id), '')
            AS extract_batch_id,

        TRY_CAST(last_update_ts AS TIMESTAMP)
            AS last_update_ts,

        NULLIF(TRIM(row_hash), '')
            AS row_hash,

        CASE
            WHEN COALESCE(
                TRY_CAST(is_void AS BOOLEAN),
                FALSE
            ) = FALSE
            AND UPPER(TRIM(shipment_status)) NOT IN (
                'VOID',
                'CANCELLED',
                'CANCELED',
                'REPLACED'
            )
            THEN TRUE
            ELSE FALSE
        END AS base_eligible_flag

    FROM raw.tms_shipments
),

enriched AS (
    SELECT
        normalized.*,

        CASE
            WHEN shipment_status = 'DELIVERED'
             AND actual_delivery_ts IS NOT NULL
             AND promised_delivery_date IS NOT NULL
            THEN CAST(actual_delivery_ts AS DATE)
                 <= promised_delivery_date
            ELSE NULL
        END AS calculated_on_time_flag,

        CASE
            WHEN shipment_status = 'DELIVERED'
             AND actual_delivery_ts IS NOT NULL
             AND promised_delivery_date IS NOT NULL
             AND CAST(actual_delivery_ts AS DATE)
                 > promised_delivery_date
            THEN DATE_DIFF(
                'day',
                promised_delivery_date,
                CAST(actual_delivery_ts AS DATE)
            )
            WHEN shipment_status = 'DELIVERED'
             AND actual_delivery_ts IS NOT NULL
             AND promised_delivery_date IS NOT NULL
            THEN 0
            ELSE NULL
        END AS days_late,

        CASE
            WHEN base_eligible_flag = TRUE
             AND NOT EXISTS (
                 SELECT 1
                 FROM normalized AS child
                 WHERE child.parent_tms_shipment_id
                       = normalized.tms_shipment_id
                   AND child.base_eligible_flag = TRUE
             )
            THEN TRUE
            ELSE FALSE
        END AS final_live_shipment_flag

    FROM normalized
)

SELECT
    enriched.*,

    COALESCE(
        source_on_time_flag,
        calculated_on_time_flag
    ) AS final_on_time_flag,

    CASE
        WHEN final_live_shipment_flag = TRUE
         AND ship_create_date
             <= MAX(ship_create_date) OVER ()
                - INTERVAL 3 DAY
        THEN TRUE
        ELSE FALSE
    END AS official_kpi_eligible_flag

FROM enriched;


-- ============================================================
-- STAGING QUALITY COUNTS
-- ============================================================

CREATE OR REPLACE TABLE quality.staging_table_counts AS

SELECT
    'stg_customers' AS table_name,
    COUNT(*) AS row_count
FROM staging.stg_customers

UNION ALL

SELECT
    'stg_customer_crosswalk',
    COUNT(*)
FROM staging.stg_customer_crosswalk

UNION ALL

SELECT
    'stg_warehouses',
    COUNT(*)
FROM staging.stg_warehouses

UNION ALL

SELECT
    'stg_carriers',
    COUNT(*)
FROM staging.stg_carriers

UNION ALL

SELECT
    'stg_shipments',
    COUNT(*)
FROM staging.stg_shipments;


-- ============================================================
-- SHIPMENT QUALITY SUMMARY
-- Informational controls: these surface source-system gaps and
-- do not silently remove otherwise eligible shipment records.
-- ============================================================

CREATE OR REPLACE TABLE quality.shipment_quality_summary AS

SELECT
    'Total staged shipments' AS metric,
    COUNT(*) AS metric_value
FROM staging.stg_shipments

UNION ALL

SELECT
    'Final live shipments',
    COUNT(*)
FROM staging.stg_shipments
WHERE final_live_shipment_flag = TRUE

UNION ALL

SELECT
    'Staged official-KPI-eligible shipments',
    COUNT(*)
FROM staging.stg_shipments
WHERE official_kpi_eligible_flag = TRUE

UNION ALL

SELECT
    'Delivered shipments missing actual delivery timestamp',
    COUNT(*)
FROM staging.stg_shipments
WHERE shipment_status = 'DELIVERED'
  AND actual_delivery_ts IS NULL

UNION ALL

SELECT
    'Source and calculated on-time results conflict',
    COUNT(*)
FROM staging.stg_shipments
WHERE source_on_time_flag IS NOT NULL
  AND calculated_on_time_flag IS NOT NULL
  AND source_on_time_flag
      IS DISTINCT FROM calculated_on_time_flag

UNION ALL

SELECT
    'Staged official-KPI-eligible shipments missing on-time result',
    COUNT(*)
FROM staging.stg_shipments
WHERE official_kpi_eligible_flag = TRUE
  AND final_on_time_flag IS NULL

UNION ALL

SELECT
    'Final live shipments missing ship date',
    COUNT(*)
FROM staging.stg_shipments
WHERE final_live_shipment_flag = TRUE
  AND ship_create_date IS NULL

UNION ALL

SELECT
    'Final live shipments missing promised date',
    COUNT(*)
FROM staging.stg_shipments
WHERE final_live_shipment_flag = TRUE
  AND promised_delivery_date IS NULL

UNION ALL

SELECT
    'Delivery timestamp precedes pickup timestamp',
    COUNT(*)
FROM staging.stg_shipments
WHERE actual_pickup_ts IS NOT NULL
  AND actual_delivery_ts IS NOT NULL
  AND actual_delivery_ts < actual_pickup_ts;
