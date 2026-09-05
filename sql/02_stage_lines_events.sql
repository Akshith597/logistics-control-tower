-- ============================================================
-- SHIPMENT LINE STAGING
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_shipment_lines AS

WITH cleaned AS (
    SELECT
        NULLIF(TRIM(tms_shipment_id), '')
            AS tms_shipment_id,

        TRY_CAST(line_number AS INTEGER)
            AS line_number,

        UPPER(NULLIF(TRIM(sku), ''))
            AS sku,

        NULLIF(TRIM(description), '')
            AS product_description,

        TRY_CAST(qty_ordered AS INTEGER)
            AS qty_ordered,

        TRY_CAST(qty_shipped AS INTEGER)
            AS qty_shipped,

        TRY_CAST(unit_weight_lb AS DOUBLE)
            AS unit_weight_lb,

        COALESCE(
            TRY_CAST(hazardous_flag AS BOOLEAN),
            FALSE
        ) AS hazardous_flag,

        NULLIF(TRIM(source_system), '')
            AS source_system

    FROM raw.tms_shipment_lines
)

SELECT
    cleaned.*,

    CASE
        WHEN qty_ordered > 0
         AND qty_shipped IS NOT NULL
        THEN qty_shipped * 1.0 / qty_ordered
        ELSE NULL
    END AS line_fill_rate,

    CASE
        WHEN qty_shipped IS NULL
        THEN 'INCOMPLETE EXTRACT'

        WHEN qty_shipped < 0
          OR qty_ordered < 0
        THEN 'INVALID QUANTITY'

        WHEN qty_shipped = qty_ordered
        THEN 'FULLY SHIPPED'

        WHEN qty_shipped < qty_ordered
        THEN 'SHORT SHIPPED'

        WHEN qty_shipped > qty_ordered
        THEN 'OVER SHIPPED'

        ELSE 'UNKNOWN'
    END AS quantity_status,

    CASE
        WHEN qty_shipped IS NOT NULL
         AND unit_weight_lb IS NOT NULL
        THEN qty_shipped * unit_weight_lb
        ELSE NULL
    END AS calculated_line_weight_lb,

    CASE
        WHEN shipment.tms_shipment_id IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS shipment_match_flag

FROM cleaned

LEFT JOIN staging.stg_shipments AS shipment
    ON cleaned.tms_shipment_id
       = shipment.tms_shipment_id;


-- ============================================================
-- TRACKING EVENT STAGING
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_tracking_events AS

WITH cleaned AS (
    SELECT
        NULLIF(TRIM(column1), '')
            AS tracking_event_id,

        NULLIF(TRIM(tms_shipment_id), '')
            AS tms_shipment_id,

        NULLIF(TRIM(tracking_number), '')
            AS tracking_number,

        UPPER(NULLIF(TRIM(event_code), ''))
            AS event_code,

        NULLIF(TRIM(event_description), '')
            AS event_description,

        TRY_CAST(event_ts_utc AS TIMESTAMP)
            AS event_ts_utc,

        TRY_CAST(event_ts_local AS TIMESTAMP)
            AS event_ts_local,

        NULLIF(TRIM(event_city), '')
            AS event_city,

        UPPER(NULLIF(TRIM(event_state), ''))
            AS event_state,

        NULLIF(TRIM(exception_reason), '')
            AS exception_reason,

        UPPER(NULLIF(TRIM(source), ''))
            AS event_source,

        TRY_CAST(ingested_ts AS TIMESTAMP)
            AS ingested_ts

    FROM raw.carrier_tracking_events
),

ranked AS (
    SELECT
        cleaned.*,

        ROW_NUMBER() OVER (
            PARTITION BY
                CASE
                    WHEN event_code = 'DLV'
                    THEN tms_shipment_id || '|DLV'
                    ELSE tracking_event_id
                END
            ORDER BY
                ingested_ts DESC NULLS LAST,
                event_ts_utc DESC NULLS LAST,
                tracking_event_id DESC
        ) AS duplicate_rank

    FROM cleaned
)

SELECT
    ranked.*,

    CASE
        WHEN duplicate_rank = 1
        THEN TRUE
        ELSE FALSE
    END AS keep_event_flag,

    CASE
        WHEN duplicate_rank > 1
        THEN TRUE
        ELSE FALSE
    END AS duplicate_event_flag,

    CASE
        WHEN shipment.tms_shipment_id IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS shipment_match_flag

FROM ranked

LEFT JOIN staging.stg_shipments AS shipment
    ON ranked.tms_shipment_id
       = shipment.tms_shipment_id;


-- ============================================================
-- DEDUPLICATED EVENT TABLE
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_tracking_events_dedup AS
SELECT *
FROM staging.stg_tracking_events
WHERE keep_event_flag = TRUE;


-- ============================================================
-- QUALITY SUMMARY
-- ============================================================

CREATE OR REPLACE TABLE quality.line_event_summary AS

SELECT
    'Shipment lines' AS metric,
    COUNT(*) AS metric_value
FROM staging.stg_shipment_lines

UNION ALL

SELECT
    'Short-shipped lines',
    COUNT(*)
FROM staging.stg_shipment_lines
WHERE quantity_status = 'SHORT SHIPPED'

UNION ALL

SELECT
    'Over-shipped lines',
    COUNT(*)
FROM staging.stg_shipment_lines
WHERE quantity_status = 'OVER SHIPPED'

UNION ALL

SELECT
    'Lines missing shipped quantity',
    COUNT(*)
FROM staging.stg_shipment_lines
WHERE qty_shipped IS NULL

UNION ALL

SELECT
    'Unmatched shipment lines',
    COUNT(*)
FROM staging.stg_shipment_lines
WHERE shipment_match_flag = FALSE

UNION ALL

SELECT
    'Raw tracking events',
    COUNT(*)
FROM staging.stg_tracking_events

UNION ALL

SELECT
    'Duplicate delivery events removed',
    COUNT(*)
FROM staging.stg_tracking_events
WHERE duplicate_event_flag = TRUE

UNION ALL

SELECT
    'Deduplicated tracking events',
    COUNT(*)
FROM staging.stg_tracking_events_dedup

UNION ALL

SELECT
    'Unmatched tracking events',
    COUNT(*)
FROM staging.stg_tracking_events
WHERE shipment_match_flag = FALSE;