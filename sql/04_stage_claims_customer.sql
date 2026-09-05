-- ============================================================
-- Logistics Control Tower
-- Claims, CRM tickets and customer survey staging
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS quality;


-- ============================================================
-- CLAIMS
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_claims AS

WITH cleaned_claims AS (
    SELECT
        NULLIF(TRIM(claim_id), '')
            AS claim_id,

        NULLIF(TRIM(tms_shipment_id), '')
            AS source_tms_shipment_id,

        NULLIF(TRIM(pro_number), '')
            AS pro_number,

        UPPER(NULLIF(TRIM(claim_type), ''))
            AS claim_type_raw,

        TRY_CAST(filed_date AS DATE)
            AS filed_date,

        TRY_CAST(
            claim_amount_requested_usd AS DECIMAL(18, 2)
        ) AS claim_amount_requested_usd,

        TRY_CAST(
            claim_amount_paid_usd AS DECIMAL(18, 2)
        ) AS claim_amount_paid_usd,

        UPPER(NULLIF(TRIM(claim_status), ''))
            AS claim_status,

        NULLIF(TRIM(carrier_id), '')
            AS carrier_id,

        NULLIF(TRIM(source_system), '')
            AS source_system,

        NULLIF(TRIM(adjuster_notes), '')
            AS adjuster_notes

    FROM raw.claims
),

pro_lookup AS (
    SELECT
        pro_number,
        tms_shipment_id,
        actual_delivery_ts,
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

matched_claims AS (
    SELECT
        claim.*,

        direct_shipment.tms_shipment_id
            AS direct_match_shipment_id,

        direct_shipment.actual_delivery_ts
            AS direct_delivery_ts,

        fallback_shipment.tms_shipment_id
            AS fallback_match_shipment_id,

        fallback_shipment.actual_delivery_ts
            AS fallback_delivery_ts

    FROM cleaned_claims AS claim

    LEFT JOIN staging.stg_shipments AS direct_shipment
        ON claim.source_tms_shipment_id
           = direct_shipment.tms_shipment_id

    LEFT JOIN pro_lookup AS fallback_shipment
        ON direct_shipment.tms_shipment_id IS NULL
       AND claim.pro_number = fallback_shipment.pro_number
)

SELECT
    claim_id,
    source_tms_shipment_id,
    pro_number,

    COALESCE(
        direct_match_shipment_id,
        fallback_match_shipment_id
    ) AS matched_tms_shipment_id,

    CASE
        WHEN direct_match_shipment_id IS NOT NULL
        THEN 'TMS SHIPMENT ID'

        WHEN fallback_match_shipment_id IS NOT NULL
        THEN 'PRO NUMBER FALLBACK'

        ELSE 'UNMATCHED'
    END AS shipment_match_method,

    CASE
        WHEN claim_type_raw LIKE '%CONCEALED%'
        THEN 'CONCEALED DAMAGE'

        WHEN claim_type_raw LIKE '%DAMAGE%'
        THEN 'DAMAGE'

        WHEN claim_type_raw LIKE '%SHORT%'
        THEN 'SHORTAGE'

        WHEN claim_type_raw LIKE '%LOSS%'
          OR claim_type_raw LIKE '%LOST%'
        THEN 'LOSS'

        ELSE COALESCE(claim_type_raw, 'OTHER')
    END AS claim_type,

    filed_date,
    claim_amount_requested_usd,
    claim_amount_paid_usd,
    claim_status,
    carrier_id,
    source_system,
    adjuster_notes,

    CASE
        WHEN claim_amount_paid_usd
             > claim_amount_requested_usd
        THEN TRUE
        ELSE FALSE
    END AS paid_exceeds_requested_flag,

    CASE
        WHEN filed_date IS NOT NULL
         AND COALESCE(
             direct_delivery_ts,
             fallback_delivery_ts
         ) IS NOT NULL
        THEN DATE_DIFF(
            'day',
            CAST(
                COALESCE(
                    direct_delivery_ts,
                    fallback_delivery_ts
                ) AS DATE
            ),
            filed_date
        )
        ELSE NULL
    END AS days_delivery_to_claim,

    CASE
        WHEN COALESCE(
            direct_match_shipment_id,
            fallback_match_shipment_id
        ) IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS shipment_match_flag

FROM matched_claims;


-- ============================================================
-- CRM TICKETS
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_crm_tickets AS

WITH cleaned_tickets AS (
    SELECT
        NULLIF(TRIM(ticket_id), '')
            AS ticket_id,

        TRY_CAST(opened_ts AS TIMESTAMP)
            AS opened_ts,

        NULLIF(TRIM(CAST(erp_customer_id AS VARCHAR)), '')
            AS source_erp_customer_id,

        NULLIF(TRIM(tms_customer_code), '')
            AS tms_customer_code_raw,

        UPPER(
            REPLACE(
                REPLACE(TRIM(tms_customer_code), '-', ''),
                ' ',
                ''
            )
        ) AS tms_customer_code_normalized,

        NULLIF(TRIM(tms_shipment_id), '')
            AS source_tms_shipment_id,

        NULLIF(TRIM(tracking_number), '')
            AS tracking_number,

        UPPER(NULLIF(TRIM(channel), ''))
            AS channel,

        NULLIF(TRIM(category_raw), '')
            AS category_raw,

        UPPER(NULLIF(TRIM(category_raw), ''))
            AS category_upper,

        UPPER(NULLIF(TRIM(severity), ''))
            AS severity,

        UPPER(NULLIF(TRIM(status), ''))
            AS ticket_status,

        NULLIF(TRIM(subject), '')
            AS subject,

        NULLIF(TRIM(description_free_text), '')
            AS description_free_text,

        TRY_CAST(resolution_hours AS DOUBLE)
            AS resolution_hours,

        NULLIF(TRIM(source_system), '')
            AS source_system

    FROM raw.crm_tickets
),

tracking_lookup AS (
    SELECT
        tracking_number,
        tms_shipment_id,
        last_update_ts

    FROM staging.stg_shipments

    WHERE final_live_shipment_flag = TRUE
      AND tracking_number IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY tracking_number
        ORDER BY
            last_update_ts DESC NULLS LAST,
            tms_shipment_id DESC
    ) = 1
),

customer_code_lookup AS (
    SELECT
        tms_customer_code_normalized,
        erp_customer_id,
        is_primary_mapping,
        effective_from

    FROM staging.stg_customer_crosswalk

    WHERE tms_customer_code_normalized IS NOT NULL

    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY tms_customer_code_normalized
        ORDER BY
            is_primary_mapping DESC,
            effective_from DESC NULLS LAST
    ) = 1
),

matched_tickets AS (
    SELECT
        ticket.*,

        direct_shipment.tms_shipment_id
            AS direct_match_shipment_id,

        tracking_shipment.tms_shipment_id
            AS tracking_match_shipment_id,

        direct_customer.erp_customer_id
            AS direct_match_customer_id,

        crosswalk_customer.erp_customer_id
            AS crosswalk_match_customer_id

    FROM cleaned_tickets AS ticket

    LEFT JOIN staging.stg_shipments AS direct_shipment
        ON ticket.source_tms_shipment_id
           = direct_shipment.tms_shipment_id

    LEFT JOIN tracking_lookup AS tracking_shipment
        ON direct_shipment.tms_shipment_id IS NULL
       AND ticket.tracking_number
           = tracking_shipment.tracking_number

    LEFT JOIN staging.stg_customers AS direct_customer
        ON ticket.source_erp_customer_id
           = direct_customer.erp_customer_id

    LEFT JOIN customer_code_lookup AS crosswalk_customer
        ON direct_customer.erp_customer_id IS NULL
       AND ticket.tms_customer_code_normalized
           = crosswalk_customer.tms_customer_code_normalized
)

SELECT
    ticket_id,
    opened_ts,

    source_erp_customer_id,
    tms_customer_code_raw,
    tms_customer_code_normalized,

    COALESCE(
        direct_match_customer_id,
        crosswalk_match_customer_id
    ) AS matched_erp_customer_id,

    CASE
        WHEN direct_match_customer_id IS NOT NULL
        THEN 'ERP CUSTOMER ID'

        WHEN crosswalk_match_customer_id IS NOT NULL
        THEN 'CUSTOMER CROSSWALK'

        ELSE 'UNMATCHED'
    END AS customer_match_method,

    source_tms_shipment_id,
    tracking_number,

    COALESCE(
        direct_match_shipment_id,
        tracking_match_shipment_id
    ) AS matched_tms_shipment_id,

    CASE
        WHEN direct_match_shipment_id IS NOT NULL
        THEN 'TMS SHIPMENT ID'

        WHEN tracking_match_shipment_id IS NOT NULL
        THEN 'TRACKING NUMBER FALLBACK'

        ELSE 'UNMATCHED'
    END AS shipment_match_method,

    channel,
    category_raw,

    CASE
        WHEN category_upper LIKE '%DAMAGE%'
        THEN 'DAMAGE'

        WHEN category_upper LIKE '%LATE%'
          OR category_upper LIKE '%DELAY%'
        THEN 'LATE DELIVERY'

        WHEN category_upper LIKE '%PARTIAL%'
          OR category_upper LIKE '%SHORT%'
          OR category_upper LIKE '%MISSING%'
        THEN 'SHORTAGE / PARTIAL DELIVERY'

        WHEN category_upper LIKE '%LOST%'
          OR category_upper LIKE '%LOSS%'
        THEN 'LOST SHIPMENT'

        WHEN category_upper LIKE '%DRIVER%'
        THEN 'DRIVER BEHAVIOR'

        WHEN category_upper LIKE '%BILL%'
          OR category_upper LIKE '%INVOICE%'
        THEN 'BILLING'

        ELSE 'OTHER'
    END AS category_normalized,

    severity,
    ticket_status,
    subject,
    description_free_text,
    resolution_hours,
    source_system,

    CASE
        WHEN resolution_hours IS NOT NULL
         AND resolution_hours >= 0
        THEN TRUE
        ELSE FALSE
    END AS valid_resolution_time_flag,

    CASE
        WHEN COALESCE(
            direct_match_shipment_id,
            tracking_match_shipment_id
        ) IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS shipment_match_flag,

    CASE
        WHEN COALESCE(
            direct_match_customer_id,
            crosswalk_match_customer_id
        ) IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS customer_match_flag

FROM matched_tickets;


-- ============================================================
-- CSAT SURVEY RESPONSES
-- ============================================================

CREATE OR REPLACE TABLE staging.stg_csat_responses AS

WITH cleaned_responses AS (
    SELECT
        NULLIF(TRIM(response_id), '')
            AS response_id,

        TRY_CAST(survey_sent_ts AS TIMESTAMP)
            AS survey_sent_ts,

        TRY_CAST(response_ts AS TIMESTAMP)
            AS response_ts,

        NULLIF(TRIM(CAST(erp_customer_id AS VARCHAR)), '')
            AS erp_customer_id,

        NULLIF(TRIM(tms_shipment_id), '')
            AS tms_shipment_id,

        TRY_CAST(csat_score_1_to_5 AS INTEGER)
            AS csat_score,

        TRY_CAST(nps_score_0_to_10 AS INTEGER)
            AS nps_score,

        NULLIF(TRIM("comment"), '')
            AS survey_comment,

        NULLIF(TRIM(source_system), '')
            AS source_system

    FROM raw.csat_survey_responses
)

SELECT
    response.response_id,
    response.survey_sent_ts,
    response.response_ts,
    response.erp_customer_id,
    response.tms_shipment_id,
    response.csat_score,
    response.nps_score,
    response.survey_comment,
    response.source_system,

    CASE
        WHEN response.csat_score BETWEEN 1 AND 5
        THEN TRUE
        ELSE FALSE
    END AS valid_csat_flag,

    CASE
        WHEN response.nps_score BETWEEN 0 AND 10
        THEN TRUE
        ELSE FALSE
    END AS valid_nps_flag,

    CASE
        WHEN response.nps_score BETWEEN 9 AND 10
        THEN 'PROMOTER'

        WHEN response.nps_score BETWEEN 7 AND 8
        THEN 'PASSIVE'

        WHEN response.nps_score BETWEEN 0 AND 6
        THEN 'DETRACTOR'

        ELSE 'INVALID'
    END AS nps_category,

    CASE
        WHEN response.survey_sent_ts IS NOT NULL
         AND response.response_ts IS NOT NULL
         AND response.response_ts
             >= response.survey_sent_ts
        THEN DATE_DIFF(
            'day',
            CAST(response.survey_sent_ts AS DATE),
            CAST(response.response_ts AS DATE)
        )
        ELSE NULL
    END AS response_days,

    CASE
        WHEN shipment.tms_shipment_id IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS shipment_match_flag,

    CASE
        WHEN customer.erp_customer_id IS NOT NULL
        THEN TRUE
        ELSE FALSE
    END AS customer_match_flag

FROM cleaned_responses AS response

LEFT JOIN staging.stg_shipments AS shipment
    ON response.tms_shipment_id
       = shipment.tms_shipment_id

LEFT JOIN staging.stg_customers AS customer
    ON response.erp_customer_id
       = customer.erp_customer_id;


-- ============================================================
-- CUSTOMER-IMPACT QUALITY SUMMARY
-- ============================================================

CREATE OR REPLACE TABLE quality.customer_impact_summary AS

SELECT
    'Total claims' AS metric,
    COUNT(*) AS metric_value
FROM staging.stg_claims

UNION ALL

SELECT
    'Unmatched claims',
    COUNT(*)
FROM staging.stg_claims
WHERE shipment_match_flag = FALSE

UNION ALL

SELECT
    'Claims paid above requested',
    COUNT(*)
FROM staging.stg_claims
WHERE paid_exceeds_requested_flag = TRUE

UNION ALL

SELECT
    'Total CRM tickets',
    COUNT(*)
FROM staging.stg_crm_tickets

UNION ALL

SELECT
    'Unmatched ticket shipments',
    COUNT(*)
FROM staging.stg_crm_tickets
WHERE shipment_match_flag = FALSE

UNION ALL

SELECT
    'Unmatched ticket customers',
    COUNT(*)
FROM staging.stg_crm_tickets
WHERE customer_match_flag = FALSE

UNION ALL

SELECT
    'Tickets categorized as OTHER',
    COUNT(*)
FROM staging.stg_crm_tickets
WHERE category_normalized = 'OTHER'

UNION ALL

SELECT
    'Total CSAT responses',
    COUNT(*)
FROM staging.stg_csat_responses

UNION ALL

SELECT
    'Invalid CSAT scores',
    COUNT(*)
FROM staging.stg_csat_responses
WHERE valid_csat_flag = FALSE

UNION ALL

SELECT
    'Invalid NPS scores',
    COUNT(*)
FROM staging.stg_csat_responses
WHERE valid_nps_flag = FALSE

UNION ALL

SELECT
    'Unmatched CSAT shipments',
    COUNT(*)
FROM staging.stg_csat_responses
WHERE shipment_match_flag = FALSE

UNION ALL

SELECT
    'Promoters',
    COUNT(*)
FROM staging.stg_csat_responses
WHERE nps_category = 'PROMOTER'

UNION ALL

SELECT
    'Passives',
    COUNT(*)
FROM staging.stg_csat_responses
WHERE nps_category = 'PASSIVE'

UNION ALL

SELECT
    'Detractors',
    COUNT(*)
FROM staging.stg_csat_responses
WHERE nps_category = 'DETRACTOR';