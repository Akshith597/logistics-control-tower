-- ============================================================
-- Logistics Control Tower
-- Power BI-ready KPI and scorecard views
--
-- Rate columns are stored as decimals (0.0 to 1.0) so Power BI
-- can format them as percentages without additional scaling.
-- Official service KPIs use official_kpi_eligible_flag = TRUE.
-- CSAT averages are weighted by valid response count because the fact
-- stores one pre-aggregated survey result per shipment.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS mart;


-- ============================================================
-- EXECUTIVE KPI SUMMARY (exactly one row)
-- ============================================================

CREATE OR REPLACE VIEW mart.vw_executive_kpis AS
SELECT
    COUNT(*) AS total_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
    ) AS official_kpi_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag IS NOT NULL
    ) AS otd_eligible_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag = TRUE
    ) AS on_time_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag = FALSE
    ) AS late_shipments,
    AVG(final_on_time_flag::INTEGER) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag IS NOT NULL
    ) AS on_time_delivery_rate,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND otif_flag IS NOT NULL
    ) AS otif_eligible_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND otif_flag = TRUE
    ) AS otif_shipments,
    AVG(otif_flag::INTEGER) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND otif_flag IS NOT NULL
    ) AS otif_rate,
    AVG(shipment_fill_rate) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
    ) AS average_fill_rate,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND shipment_fill_rate IS NOT NULL
    ) AS full_fill_eligible_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND shipment_fill_rate >= 1
    ) AS full_fill_shipments,
    AVG((shipment_fill_rate >= 1)::INTEGER) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND shipment_fill_rate IS NOT NULL
    ) AS full_fill_rate,
    AVG(days_late) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag = FALSE
    ) AS average_days_late,
    AVG(warehouse_cycle_hours) AS average_warehouse_cycle_hours,
    SUM(customer_revenue_usd) AS customer_revenue_usd,
    SUM(carrier_cost_usd) AS carrier_cost_usd,
    SUM(total_accessorial_usd) AS accessorial_cost_usd,
    SUM(claims_paid_usd) AS claims_paid_usd,
    SUM(gross_margin_usd) AS gross_margin_usd,
    SUM(gross_margin_usd) / NULLIF(
        SUM(customer_revenue_usd), 0
    ) AS gross_margin_percentage,
    COUNT(*) FILTER (WHERE complaint_flag = TRUE)
        AS shipments_with_complaints,
    AVG(complaint_flag::INTEGER) AS complaint_rate,
    COUNT(*) FILTER (WHERE claim_flag = TRUE)
        AS shipments_with_claims,
    AVG(claim_flag::INTEGER) AS claim_rate,
    SUM(average_csat_score * valid_csat_response_count) FILTER (
        WHERE valid_csat_response_count > 0
          AND average_csat_score IS NOT NULL
    ) / NULLIF(
        SUM(valid_csat_response_count) FILTER (
            WHERE valid_csat_response_count > 0
              AND average_csat_score IS NOT NULL
        ),
        0
    ) AS average_csat_score,
    100.0 * (
        SUM(COALESCE(promoter_count, 0))
        - SUM(COALESCE(detractor_count, 0))
    ) / NULLIF(
        SUM(COALESCE(promoter_count, 0))
        + SUM(COALESCE(passive_count, 0))
        + SUM(COALESCE(detractor_count, 0)),
        0
    ) AS net_promoter_score
FROM mart.fact_shipment;


-- ============================================================
-- MONTHLY TREND
-- ============================================================

CREATE OR REPLACE VIEW mart.vw_monthly_performance AS
SELECT
    DATE_TRUNC('month', ship_date)::DATE AS month_start_date,
    STRFTIME(ship_date, '%Y-%m') AS year_month,
    COUNT(*) AS total_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
    ) AS official_kpi_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag IS NOT NULL
    ) AS otd_eligible_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag = TRUE
    ) AS on_time_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag = FALSE
    ) AS late_shipments,
    AVG(final_on_time_flag::INTEGER) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag IS NOT NULL
    ) AS on_time_delivery_rate,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND otif_flag IS NOT NULL
    ) AS otif_eligible_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND otif_flag = TRUE
    ) AS otif_shipments,
    AVG(otif_flag::INTEGER) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND otif_flag IS NOT NULL
    ) AS otif_rate,
    AVG(shipment_fill_rate) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
    ) AS average_fill_rate,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND shipment_fill_rate IS NOT NULL
    ) AS full_fill_eligible_shipments,
    COUNT(*) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND shipment_fill_rate >= 1
    ) AS full_fill_shipments,
    AVG((shipment_fill_rate >= 1)::INTEGER) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND shipment_fill_rate IS NOT NULL
    ) AS full_fill_rate,
    AVG(days_late) FILTER (
        WHERE official_kpi_eligible_flag = TRUE
          AND final_on_time_flag = FALSE
    ) AS average_days_late,
    AVG(warehouse_cycle_hours) AS average_warehouse_cycle_hours,
    SUM(customer_revenue_usd) AS customer_revenue_usd,
    SUM(carrier_cost_usd) AS carrier_cost_usd,
    SUM(claims_paid_usd) AS claims_paid_usd,
    SUM(gross_margin_usd) AS gross_margin_usd,
    SUM(gross_margin_usd) / NULLIF(
        SUM(customer_revenue_usd), 0
    ) AS gross_margin_percentage,
    AVG(complaint_flag::INTEGER) AS complaint_rate,
    AVG(claim_flag::INTEGER) AS claim_rate,
    SUM(average_csat_score * valid_csat_response_count) FILTER (
        WHERE valid_csat_response_count > 0
          AND average_csat_score IS NOT NULL
    ) / NULLIF(
        SUM(valid_csat_response_count) FILTER (
            WHERE valid_csat_response_count > 0
              AND average_csat_score IS NOT NULL
        ),
        0
    ) AS average_csat_score,
    100.0 * (
        SUM(COALESCE(promoter_count, 0))
        - SUM(COALESCE(detractor_count, 0))
    ) / NULLIF(
        SUM(COALESCE(promoter_count, 0))
        + SUM(COALESCE(passive_count, 0))
        + SUM(COALESCE(detractor_count, 0)),
        0
    ) AS net_promoter_score
FROM mart.fact_shipment
GROUP BY 1, 2;


-- ============================================================
-- CARRIER SCORECARD
-- ============================================================

CREATE OR REPLACE VIEW mart.vw_carrier_scorecard AS
SELECT
    fact.carrier_key,
    carrier.scac,
    carrier.carrier_legal_name,
    carrier.primary_mode,
    carrier.carrier_status,
    COUNT(*) AS total_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS official_kpi_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS otd_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = TRUE
    ) AS on_time_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = FALSE
    ) AS late_shipments,
    AVG(fact.final_on_time_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS on_time_delivery_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag = TRUE
    ) AS otif_shipments,
    AVG(fact.otif_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_rate,
    AVG(fact.shipment_fill_rate) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS average_fill_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate >= 1
    ) AS full_fill_shipments,
    AVG((fact.shipment_fill_rate >= 1)::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_rate,
    AVG(fact.days_late) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = FALSE
    ) AS average_days_late,
    AVG(fact.tracking_exception_count) AS average_tracking_exceptions,
    SUM(fact.customer_revenue_usd) AS customer_revenue_usd,
    SUM(fact.carrier_cost_usd) AS carrier_cost_usd,
    SUM(fact.total_accessorial_usd) AS accessorial_cost_usd,
    SUM(fact.claims_paid_usd) AS claims_paid_usd,
    SUM(fact.gross_margin_usd) AS gross_margin_usd,
    SUM(fact.gross_margin_usd) / NULLIF(
        SUM(fact.customer_revenue_usd), 0
    ) AS gross_margin_percentage,
    SUM(fact.carrier_cost_usd) / NULLIF(COUNT(*), 0)
        AS carrier_cost_per_shipment,
    AVG(fact.complaint_flag::INTEGER) AS complaint_rate,
    AVG(fact.claim_flag::INTEGER) AS claim_rate,
    SUM(
        fact.average_csat_score * fact.valid_csat_response_count
    ) FILTER (
        WHERE fact.valid_csat_response_count > 0
          AND fact.average_csat_score IS NOT NULL
    ) / NULLIF(
        SUM(fact.valid_csat_response_count) FILTER (
            WHERE fact.valid_csat_response_count > 0
              AND fact.average_csat_score IS NOT NULL
        ),
        0
    ) AS average_csat_score
FROM mart.fact_shipment AS fact
LEFT JOIN mart.dim_carrier AS carrier
    ON fact.carrier_key = carrier.carrier_key
GROUP BY 1, 2, 3, 4, 5;


-- ============================================================
-- WAREHOUSE SCORECARD
-- ============================================================

CREATE OR REPLACE VIEW mart.vw_warehouse_scorecard AS
SELECT
    fact.warehouse_key,
    warehouse.warehouse_name,
    warehouse.city,
    warehouse.state,
    warehouse.daily_outbound_capacity,
    warehouse.is_active,
    COUNT(*) AS total_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS official_kpi_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS otd_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = TRUE
    ) AS on_time_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = FALSE
    ) AS late_shipments,
    AVG(fact.final_on_time_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS on_time_delivery_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag = TRUE
    ) AS otif_shipments,
    AVG(fact.otif_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_rate,
    AVG(fact.shipment_fill_rate) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS average_fill_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate >= 1
    ) AS full_fill_shipments,
    AVG((fact.shipment_fill_rate >= 1)::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_rate,
    AVG(fact.warehouse_cycle_hours) AS average_warehouse_cycle_hours,
    AVG(fact.pick_to_pack_hours) AS average_pick_to_pack_hours,
    AVG(fact.pack_to_ship_hours) AS average_pack_to_ship_hours,
    AVG(fact.short_pick_flag::INTEGER) FILTER (
        WHERE fact.wms_record_count > 0
          AND fact.short_pick_flag IS NOT NULL
    ) AS short_pick_rate,
    AVG(fact.average_inventory_accuracy) AS average_inventory_accuracy,
    SUM(fact.customer_revenue_usd) AS customer_revenue_usd,
    SUM(fact.carrier_cost_usd) AS carrier_cost_usd,
    SUM(fact.claims_paid_usd) AS claims_paid_usd,
    SUM(fact.gross_margin_usd) AS gross_margin_usd,
    SUM(fact.gross_margin_usd) / NULLIF(
        SUM(fact.customer_revenue_usd), 0
    ) AS gross_margin_percentage,
    AVG(fact.complaint_flag::INTEGER) AS complaint_rate,
    AVG(fact.claim_flag::INTEGER) AS claim_rate,
    SUM(
        fact.average_csat_score * fact.valid_csat_response_count
    ) FILTER (
        WHERE fact.valid_csat_response_count > 0
          AND fact.average_csat_score IS NOT NULL
    ) / NULLIF(
        SUM(fact.valid_csat_response_count) FILTER (
            WHERE fact.valid_csat_response_count > 0
              AND fact.average_csat_score IS NOT NULL
        ),
        0
    ) AS average_csat_score
FROM mart.fact_shipment AS fact
LEFT JOIN mart.dim_warehouse AS warehouse
    ON fact.warehouse_key = warehouse.warehouse_key
GROUP BY 1, 2, 3, 4, 5, 6;


-- ============================================================
-- CUSTOMER SCORECARD
-- ============================================================

CREATE OR REPLACE VIEW mart.vw_customer_scorecard AS
SELECT
    fact.customer_key,
    customer.legal_name,
    customer.dba_name,
    customer.industry,
    customer.customer_status,
    customer.annual_volume_tier,
    customer.primary_bill_to_state,
    COUNT(*) AS total_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS official_kpi_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS otd_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = TRUE
    ) AS on_time_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = FALSE
    ) AS late_shipments,
    AVG(fact.final_on_time_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS on_time_delivery_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag = TRUE
    ) AS otif_shipments,
    AVG(fact.otif_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_rate,
    AVG(fact.shipment_fill_rate) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS average_fill_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate >= 1
    ) AS full_fill_shipments,
    AVG((fact.shipment_fill_rate >= 1)::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_rate,
    SUM(fact.customer_revenue_usd) AS customer_revenue_usd,
    SUM(fact.carrier_cost_usd) AS carrier_cost_usd,
    SUM(fact.claims_paid_usd) AS claims_paid_usd,
    SUM(fact.gross_margin_usd) AS gross_margin_usd,
    SUM(fact.gross_margin_usd) / NULLIF(
        SUM(fact.customer_revenue_usd), 0
    ) AS gross_margin_percentage,
    COUNT(*) FILTER (WHERE fact.complaint_flag = TRUE)
        AS shipments_with_complaints,
    AVG(fact.complaint_flag::INTEGER) AS complaint_rate,
    COUNT(*) FILTER (WHERE fact.claim_flag = TRUE)
        AS shipments_with_claims,
    AVG(fact.claim_flag::INTEGER) AS claim_rate,
    SUM(
        fact.average_csat_score * fact.valid_csat_response_count
    ) FILTER (
        WHERE fact.valid_csat_response_count > 0
          AND fact.average_csat_score IS NOT NULL
    ) / NULLIF(
        SUM(fact.valid_csat_response_count) FILTER (
            WHERE fact.valid_csat_response_count > 0
              AND fact.average_csat_score IS NOT NULL
        ),
        0
    ) AS average_csat_score,
    100.0 * (
        SUM(COALESCE(fact.promoter_count, 0))
        - SUM(COALESCE(fact.detractor_count, 0))
    ) / NULLIF(
        SUM(COALESCE(fact.promoter_count, 0))
        + SUM(COALESCE(fact.passive_count, 0))
        + SUM(COALESCE(fact.detractor_count, 0)),
        0
    ) AS net_promoter_score
FROM mart.fact_shipment AS fact
LEFT JOIN mart.dim_customer AS customer
    ON fact.customer_key = customer.customer_key
GROUP BY 1, 2, 3, 4, 5, 6, 7;


-- ============================================================
-- LANE SCORECARD
-- ============================================================

CREATE OR REPLACE VIEW mart.vw_lane_scorecard AS
SELECT
    fact.lane_key,
    lane.origin_warehouse_id,
    origin.warehouse_name AS origin_warehouse_name,
    lane.destination_city,
    lane.destination_state,
    lane.destination_postal,
    lane.destination_country,
    COUNT(*) AS total_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS official_kpi_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS otd_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = TRUE
    ) AS on_time_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = FALSE
    ) AS late_shipments,
    AVG(fact.final_on_time_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag IS NOT NULL
    ) AS on_time_delivery_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag = TRUE
    ) AS otif_shipments,
    AVG(fact.otif_flag::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.otif_flag IS NOT NULL
    ) AS otif_rate,
    AVG(fact.shipment_fill_rate) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
    ) AS average_fill_rate,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_eligible_shipments,
    COUNT(*) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate >= 1
    ) AS full_fill_shipments,
    AVG((fact.shipment_fill_rate >= 1)::INTEGER) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.shipment_fill_rate IS NOT NULL
    ) AS full_fill_rate,
    AVG(fact.days_late) FILTER (
        WHERE fact.official_kpi_eligible_flag = TRUE
          AND fact.final_on_time_flag = FALSE
    ) AS average_days_late,
    AVG(fact.lane_miles_est) AS average_lane_miles,
    SUM(fact.customer_revenue_usd) AS customer_revenue_usd,
    SUM(fact.carrier_cost_usd) AS carrier_cost_usd,
    SUM(fact.total_accessorial_usd) AS accessorial_cost_usd,
    SUM(fact.claims_paid_usd) AS claims_paid_usd,
    SUM(fact.gross_margin_usd) AS gross_margin_usd,
    SUM(fact.gross_margin_usd) / NULLIF(
        SUM(fact.customer_revenue_usd), 0
    ) AS gross_margin_percentage,
    SUM(fact.carrier_cost_usd) / NULLIF(COUNT(*), 0)
        AS carrier_cost_per_shipment,
    AVG(fact.complaint_flag::INTEGER) AS complaint_rate,
    AVG(fact.claim_flag::INTEGER) AS claim_rate,
    SUM(
        fact.average_csat_score * fact.valid_csat_response_count
    ) FILTER (
        WHERE fact.valid_csat_response_count > 0
          AND fact.average_csat_score IS NOT NULL
    ) / NULLIF(
        SUM(fact.valid_csat_response_count) FILTER (
            WHERE fact.valid_csat_response_count > 0
              AND fact.average_csat_score IS NOT NULL
        ),
        0
    ) AS average_csat_score
FROM mart.fact_shipment AS fact
LEFT JOIN mart.dim_lane AS lane
    ON fact.lane_key = lane.lane_key
LEFT JOIN mart.dim_warehouse AS origin
    ON lane.origin_warehouse_id = origin.warehouse_key
GROUP BY 1, 2, 3, 4, 5, 6, 7;
