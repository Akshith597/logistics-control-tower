-- ============================================================
-- Logistics Control Tower
-- Read-only portfolio analysis examples
--
-- These queries reproduce the published opportunity tables from
-- the curated mart. Thresholds are analytical guardrails, not
-- operating policy. Run after 06_create_kpi_views.sql.
-- ============================================================


-- ============================================================
-- 1. CARRIER RATE RANKING
-- Lowest OTD among carriers with 1,000+ OTD-eligible shipments.
-- ============================================================

WITH eligible_carriers AS (
    SELECT
        carrier_key,
        scac,
        carrier_legal_name,
        primary_mode,
        official_kpi_shipments,
        otd_eligible_shipments,
        on_time_shipments,
        late_shipments,
        on_time_delivery_rate,
        otif_eligible_shipments,
        otif_shipments,
        otif_rate,
        claim_rate,
        gross_margin_percentage
    FROM mart.vw_carrier_scorecard
    WHERE otd_eligible_shipments >= 1000
      AND on_time_delivery_rate IS NOT NULL
),

ranked_carriers AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                on_time_delivery_rate ASC,
                late_shipments DESC,
                carrier_key
        ) AS rate_rank,
        eligible_carriers.*
    FROM eligible_carriers
)

SELECT *
FROM ranked_carriers
WHERE rate_rank <= 10
ORDER BY rate_rank;


-- ============================================================
-- 2. LANE RATE RANKING
-- Lowest OTIF among lanes with 250+ OTIF-eligible shipments.
-- ============================================================

WITH eligible_lanes AS (
    SELECT
        lane_key,
        origin_warehouse_name,
        destination_city,
        destination_state,
        destination_country,
        official_kpi_shipments,
        otd_eligible_shipments,
        on_time_shipments,
        late_shipments,
        on_time_delivery_rate,
        otif_eligible_shipments,
        otif_shipments,
        otif_rate,
        average_days_late,
        gross_margin_percentage
    FROM mart.vw_lane_scorecard
    WHERE otif_eligible_shipments >= 250
      AND otif_rate IS NOT NULL
),

ranked_lanes AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                otif_rate ASC,
                late_shipments DESC,
                lane_key
        ) AS rate_rank,
        eligible_lanes.*
    FROM eligible_lanes
)

SELECT *
FROM ranked_lanes
WHERE rate_rank <= 15
ORDER BY rate_rank;


-- ============================================================
-- 3. ACTIVE-CUSTOMER PROFITABILITY RANKING
-- Lowest aggregate margin rate among active customers with 1,000+ rows.
-- ============================================================

WITH eligible_customers AS (
    SELECT
        customer_key,
        legal_name,
        industry,
        customer_status,
        total_shipments,
        customer_revenue_usd,
        gross_margin_usd,
        gross_margin_percentage,
        complaint_rate,
        claim_rate,
        average_csat_score
    FROM mart.vw_customer_scorecard
    WHERE customer_status = 'ACTIVE'
      AND total_shipments >= 1000
      AND gross_margin_percentage IS NOT NULL
),

ranked_customers AS (
    SELECT
        ROW_NUMBER() OVER (
            ORDER BY
                gross_margin_percentage ASC,
                total_shipments DESC,
                customer_key
        ) AS margin_rate_rank,
        eligible_customers.*
    FROM eligible_customers
)

SELECT *
FROM ranked_customers
WHERE margin_rate_rank <= 10
ORDER BY margin_rate_rank;


-- ============================================================
-- 4. CUSTOMER IMPACT BY DELIVERY STATUS
-- Descriptive association only; this is not a causal estimate.
-- CSAT is response-weighted because the fact is shipment-grain.
-- ============================================================

WITH delivery_groups AS (
    SELECT
        CASE
            WHEN final_on_time_flag = TRUE THEN 'On time'
            ELSE 'Late'
        END AS delivery_status,
        COUNT(*) AS shipments,
        AVG(complaint_flag::INTEGER) AS complaint_rate,
        AVG(claim_flag::INTEGER) AS claim_rate,
        SUM(
            average_csat_score * survey_response_count
        ) FILTER (
            WHERE survey_response_count > 0
              AND average_csat_score IS NOT NULL
        ) / NULLIF(
            SUM(survey_response_count) FILTER (
                WHERE survey_response_count > 0
                  AND average_csat_score IS NOT NULL
            ),
            0
        ) AS average_csat_score,
        AVG(days_late) AS average_days_late
    FROM mart.fact_shipment
    WHERE official_kpi_eligible_flag = TRUE
      AND final_on_time_flag IS NOT NULL
    GROUP BY 1
),

comparisons AS (
    SELECT
        delivery_groups.*,
        complaint_rate / NULLIF(
            MAX(complaint_rate) FILTER (
                WHERE delivery_status = 'On time'
            ) OVER (),
            0
        ) AS complaint_rate_vs_on_time,
        claim_rate / NULLIF(
            MAX(claim_rate) FILTER (
                WHERE delivery_status = 'On time'
            ) OVER (),
            0
        ) AS claim_rate_vs_on_time,
        MAX(average_csat_score) FILTER (
            WHERE delivery_status = 'On time'
        ) OVER () - average_csat_score
            AS csat_gap_below_on_time
    FROM delivery_groups
)

SELECT *
FROM comparisons
ORDER BY
    CASE delivery_status
        WHEN 'Late' THEN 1
        WHEN 'On time' THEN 2
        ELSE 3
    END;
