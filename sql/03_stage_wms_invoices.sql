-- ============================================================
-- Logistics Control Tower
-- Stage and match WMS outbound records and ERP invoices
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS quality;


-- ============================================================
-- WMS OUTBOUND
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_wms_outbound AS

WITH cleaned_wms AS (
    SELECT
        NULLIF(TRIM(wms_outbound_id), '')
            AS wms_outbound_id,

        UPPER(NULLIF(TRIM(wms_location_code), ''))
            AS wms_location_code,

        NULLIF(TRIM(sales_order_id), '')
            AS sales_order_id,

        NULLIF(TRIM(tms_shipment_id), '')
            AS source_tms_shipment_id,

        TRY_CAST(pick_start_ts AS TIMESTAMP)
            AS pick_start_ts,

        TRY_CAST(pack_complete_ts AS TIMESTAMP)
            AS pack_complete_ts,

        TRY_CAST(ship_confirm_ts AS TIMESTAMP)
            AS ship_confirm_ts,

        TRY_CAST(lines_picked AS INTEGER)
            AS lines_picked,

        COALESCE(
            TRY_CAST(short_pick_flag AS BOOLEAN),
            FALSE
        ) AS short_pick_flag,

        TRY_CAST(
            inventory_accuracy_snapshot AS DOUBLE
        ) AS inventory_accuracy_snapshot,

        NULLIF(TRIM(source_system), '')
            AS source_system

    FROM raw.wms_outbound
),

sales_order_lookup AS (
    SELECT
        sales_order_id,
        tms_shipment_id,
        last_update_ts

    FROM staging.stg_shipments

    WHERE final_live_shipment_flag = TRUE
      AND sales_order_id IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY sales_order_id
        ORDER BY
            last_update_ts DESC NULLS LAST,
            tms_shipment_id DESC
    ) = 1
),

matched_wms AS (
    SELECT
        wms.*,

        direct_shipment.tms_shipment_id
            AS direct_match_shipment_id,

        fallback_shipment.tms_shipment_id
            AS fallback_match_shipment_id

    FROM cleaned_wms AS wms

    LEFT JOIN staging.stg_shipments AS direct_shipment
        ON wms.source_tms_shipment_id
           = direct_shipment.tms_shipment_id

    LEFT JOIN sales_order_lookup AS fallback_shipment
        ON direct_shipment.tms_shipment_id IS NULL
       AND wms.sales_order_id
           = fallback_shipment.sales_order_id
)

SELECT
    wms_outbound_id,
    wms_location_code,
    sales_order_id,
    source_tms_shipment_id,

    COALESCE(
        direct_match_shipment_id,
        fallback_match_shipment_id
    ) AS matched_tms_shipment_id,

    CASE
        WHEN direct_match_shipment_id IS NOT NULL
        THEN 'TMS SHIPMENT ID'

        WHEN fallback_match_shipment_id IS NOT NULL
        THEN 'SALES ORDER FALLBACK'

        ELSE 'UNMATCHED'
    END AS shipment_match_method,

    pick_start_ts,
    pack_complete_ts,
    ship_confirm_ts,
    lines_picked,
    short_pick_flag,
    inventory_accuracy_snapshot,
    source_system,

    CASE
        WHEN pick_start_ts IS NOT NULL
         AND pack_complete_ts IS NOT NULL
         AND pack_complete_ts >= pick_start_ts
        THEN DATE_DIFF(
            'minute',
            pick_start_ts,
            pack_complete_ts
        ) / 60.0
        ELSE NULL
    END AS pick_to_pack_hours,

    CASE
        WHEN pack_complete_ts IS NOT NULL
         AND ship_confirm_ts IS NOT NULL
         AND ship_confirm_ts >= pack_complete_ts
        THEN DATE_DIFF(
            'minute',
            pack_complete_ts,
            ship_confirm_ts
        ) / 60.0
        ELSE NULL
    END AS pack_to_ship_hours,

    CASE
        WHEN pick_start_ts IS NOT NULL
         AND ship_confirm_ts IS NOT NULL
         AND ship_confirm_ts >= pick_start_ts
        THEN DATE_DIFF(
            'minute',
            pick_start_ts,
            ship_confirm_ts
        ) / 60.0
        ELSE NULL
    END AS total_warehouse_cycle_hours,

    CASE
        WHEN pack_complete_ts IS NOT NULL
         AND pick_start_ts IS NOT NULL
         AND pack_complete_ts < pick_start_ts
        THEN TRUE

        WHEN ship_confirm_ts IS NOT NULL
         AND pack_complete_ts IS NOT NULL
         AND ship_confirm_ts < pack_complete_ts
        THEN TRUE

        ELSE FALSE
    END AS invalid_timestamp_sequence_flag,

    CASE
        WHEN COALESCE(
            direct_match_shipment_id,
            fallback_match_shipment_id
        ) IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS shipment_match_flag

FROM matched_wms;


-- ============================================================
-- ERP INVOICES
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_invoices AS

WITH cleaned_invoices AS (
    SELECT
        NULLIF(TRIM(invoice_id), '')
            AS invoice_id,

        UPPER(NULLIF(TRIM(invoice_type), ''))
            AS invoice_type,

        NULLIF(TRIM(CAST(erp_customer_id AS VARCHAR)), '')
            AS erp_customer_id,

        NULLIF(TRIM(tms_shipment_id), '')
            AS source_tms_shipment_id,

        NULLIF(TRIM(sales_order_id), '')
            AS sales_order_id,

        NULLIF(TRIM(pro_number), '')
            AS pro_number,

        TRY_CAST(invoice_date AS DATE)
            AS invoice_date,

        TRY_CAST(gl_post_date AS DATE)
            AS gl_post_date,

        TRY_CAST(line_amount_usd AS DECIMAL(18, 2))
            AS line_amount_usd,

        TRY_CAST(
            accessorial_amount_usd AS DECIMAL(18, 2)
        ) AS accessorial_amount_usd,

        TRY_CAST(
            fuel_surcharge_usd AS DECIMAL(18, 2)
        ) AS fuel_surcharge_usd,

        TRY_CAST(tax_usd AS DECIMAL(18, 2))
            AS tax_usd,

        UPPER(NULLIF(TRIM(currency), ''))
            AS currency,

        UPPER(NULLIF(TRIM(payment_status), ''))
            AS payment_status,

        COALESCE(
            TRY_CAST(dispute_flag AS BOOLEAN),
            FALSE
        ) AS dispute_flag,

        NULLIF(TRIM(source_system), '')
            AS source_system

    FROM raw.erp_invoices
),

sales_order_lookup AS (
    SELECT
        sales_order_id,
        tms_shipment_id,
        last_update_ts

    FROM staging.stg_shipments

    WHERE final_live_shipment_flag = TRUE
      AND sales_order_id IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY sales_order_id
        ORDER BY
            last_update_ts DESC NULLS LAST,
            tms_shipment_id DESC
    ) = 1
),

pro_number_lookup AS (
    SELECT
        pro_number,
        tms_shipment_id,
        last_update_ts

    FROM staging.stg_shipments

    WHERE final_live_shipment_flag = TRUE
      AND pro_number IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY pro_number
        ORDER BY
            last_update_ts DESC NULLS LAST,
            tms_shipment_id DESC
    ) = 1
),

matched_invoices AS (
    SELECT
        invoice.*,

        direct_shipment.tms_shipment_id
            AS direct_match_shipment_id,

        sales_order_shipment.tms_shipment_id
            AS sales_order_match_shipment_id,

        pro_shipment.tms_shipment_id
            AS pro_match_shipment_id

    FROM cleaned_invoices AS invoice

    LEFT JOIN staging.stg_shipments AS direct_shipment
        ON invoice.source_tms_shipment_id
           = direct_shipment.tms_shipment_id

    LEFT JOIN sales_order_lookup AS sales_order_shipment
        ON direct_shipment.tms_shipment_id IS NULL
       AND invoice.sales_order_id
           = sales_order_shipment.sales_order_id

    LEFT JOIN pro_number_lookup AS pro_shipment
        ON direct_shipment.tms_shipment_id IS NULL
       AND sales_order_shipment.tms_shipment_id IS NULL
       AND invoice.pro_number
           = pro_shipment.pro_number
)

SELECT
    invoice_id,
    invoice_type,
    erp_customer_id,
    source_tms_shipment_id,
    sales_order_id,
    pro_number,

    COALESCE(
        direct_match_shipment_id,
        sales_order_match_shipment_id,
        pro_match_shipment_id
    ) AS matched_tms_shipment_id,

    CASE
        WHEN direct_match_shipment_id IS NOT NULL
        THEN 'TMS SHIPMENT ID'

        WHEN sales_order_match_shipment_id IS NOT NULL
        THEN 'SALES ORDER FALLBACK'

        WHEN pro_match_shipment_id IS NOT NULL
        THEN 'PRO NUMBER FALLBACK'

        ELSE 'UNMATCHED'
    END AS shipment_match_method,

    invoice_date,
    gl_post_date,
    line_amount_usd,
    accessorial_amount_usd,
    fuel_surcharge_usd,
    tax_usd,
    currency,
    payment_status,
    dispute_flag,
    source_system,

    COALESCE(line_amount_usd, 0)
        + COALESCE(accessorial_amount_usd, 0)
        + COALESCE(fuel_surcharge_usd, 0)
        AS net_freight_amount_usd,

    COALESCE(line_amount_usd, 0)
        + COALESCE(accessorial_amount_usd, 0)
        + COALESCE(fuel_surcharge_usd, 0)
        + COALESCE(tax_usd, 0)
        AS invoice_total_usd,

    CASE
        WHEN invoice_type = 'CUSTOMER'
        THEN
            COALESCE(line_amount_usd, 0)
            + COALESCE(accessorial_amount_usd, 0)
            + COALESCE(fuel_surcharge_usd, 0)
        ELSE 0
    END AS customer_revenue_usd,

    CASE
        WHEN invoice_type = 'CARRIER_BILL'
        THEN
            COALESCE(line_amount_usd, 0)
            + COALESCE(accessorial_amount_usd, 0)
            + COALESCE(fuel_surcharge_usd, 0)
        ELSE 0
    END AS carrier_cost_usd,

    CASE
        WHEN COALESCE(
            direct_match_shipment_id,
            sales_order_match_shipment_id,
            pro_match_shipment_id
        ) IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS shipment_match_flag

FROM matched_invoices;


-- ============================================================
-- WMS AND INVOICE QUALITY SUMMARY
-- ============================================================

CREATE OR REPLACE TABLE quality.wms_invoice_summary AS

SELECT
    'Total WMS rows' AS metric,
    COUNT(*) AS metric_value
FROM staging.stg_wms_outbound

UNION ALL

SELECT
    'WMS direct shipment matches',
    COUNT(*)
FROM staging.stg_wms_outbound
WHERE shipment_match_method = 'TMS SHIPMENT ID'

UNION ALL

SELECT
    'WMS sales-order fallback matches',
    COUNT(*)
FROM staging.stg_wms_outbound
WHERE shipment_match_method = 'SALES ORDER FALLBACK'

UNION ALL

SELECT
    'Unmatched WMS rows',
    COUNT(*)
FROM staging.stg_wms_outbound
WHERE shipment_match_method = 'UNMATCHED'

UNION ALL

SELECT
    'WMS short picks',
    COUNT(*)
FROM staging.stg_wms_outbound
WHERE short_pick_flag = TRUE

UNION ALL

SELECT
    'WMS invalid timestamp sequences',
    COUNT(*)
FROM staging.stg_wms_outbound
WHERE invalid_timestamp_sequence_flag = TRUE

UNION ALL

SELECT
    'Total invoice rows',
    COUNT(*)
FROM staging.stg_invoices

UNION ALL

SELECT
    'Invoice direct shipment matches',
    COUNT(*)
FROM staging.stg_invoices
WHERE shipment_match_method = 'TMS SHIPMENT ID'

UNION ALL

SELECT
    'Invoice sales-order fallback matches',
    COUNT(*)
FROM staging.stg_invoices
WHERE shipment_match_method = 'SALES ORDER FALLBACK'

UNION ALL

SELECT
    'Invoice PRO-number fallback matches',
    COUNT(*)
FROM staging.stg_invoices
WHERE shipment_match_method = 'PRO NUMBER FALLBACK'

UNION ALL

SELECT
    'Unmatched invoices',
    COUNT(*)
FROM staging.stg_invoices
WHERE shipment_match_method = 'UNMATCHED'

UNION ALL

SELECT
    'Customer revenue invoices',
    COUNT(*)
FROM staging.stg_invoices
WHERE invoice_type = 'CUSTOMER'

UNION ALL

SELECT
    'Carrier bill invoices',
    COUNT(*)
FROM staging.stg_invoices
WHERE invoice_type = 'CARRIER_BILL'

UNION ALL

SELECT
    'Disputed invoices',
    COUNT(*)
FROM staging.stg_invoices
WHERE dispute_flag = TRUE;