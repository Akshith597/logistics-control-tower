-- ============================================================
-- Logistics Control Tower
-- Read-only semantic-model validation
--
-- Run after 01_create_staging.sql through 06_create_kpi_views.sql.
-- A healthy model returns PASS for every test below.
-- ============================================================

WITH validation_results AS (
    SELECT
        'fact_shipment key is not null' AS test_name,
        'CRITICAL' AS severity,
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment
            WHERE shipment_key IS NULL
        ) AS failure_count

    UNION ALL

    SELECT
        'fact_shipment has one row per shipment',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM (
                SELECT shipment_key
                FROM mart.fact_shipment
                GROUP BY shipment_key
                HAVING COUNT(*) > 1
            ) AS duplicate_fact_keys
        )

    UNION ALL

    SELECT
        'dim_customer key is unique',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM (
                SELECT customer_key
                FROM mart.dim_customer
                GROUP BY customer_key
                HAVING customer_key IS NULL OR COUNT(*) > 1
            ) AS invalid_customer_keys
        )

    UNION ALL

    SELECT
        'dim_carrier key is unique',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM (
                SELECT carrier_key
                FROM mart.dim_carrier
                GROUP BY carrier_key
                HAVING carrier_key IS NULL OR COUNT(*) > 1
            ) AS invalid_carrier_keys
        )

    UNION ALL

    SELECT
        'dim_warehouse key is unique',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM (
                SELECT warehouse_key
                FROM mart.dim_warehouse
                GROUP BY warehouse_key
                HAVING warehouse_key IS NULL OR COUNT(*) > 1
            ) AS invalid_warehouse_keys
        )

    UNION ALL

    SELECT
        'dim_service key is unique',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM (
                SELECT service_key
                FROM mart.dim_service
                GROUP BY service_key
                HAVING service_key IS NULL OR COUNT(*) > 1
            ) AS invalid_service_keys
        )

    UNION ALL

    SELECT
        'dim_lane key is unique',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM (
                SELECT lane_key
                FROM mart.dim_lane
                GROUP BY lane_key
                HAVING lane_key IS NULL OR COUNT(*) > 1
            ) AS invalid_lane_keys
        )

    UNION ALL

    SELECT
        'fact customer keys resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_customer AS dimension
                ON fact.customer_key = dimension.customer_key
            WHERE dimension.customer_key IS NULL
        )

    UNION ALL

    SELECT
        'fact carrier keys resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_carrier AS dimension
                ON fact.carrier_key = dimension.carrier_key
            WHERE dimension.carrier_key IS NULL
        )

    UNION ALL

    SELECT
        'fact warehouse keys resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_warehouse AS dimension
                ON fact.warehouse_key = dimension.warehouse_key
            WHERE dimension.warehouse_key IS NULL
        )

    UNION ALL

    SELECT
        'fact service keys resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_service AS dimension
                ON fact.service_key = dimension.service_key
            WHERE dimension.service_key IS NULL
        )

    UNION ALL

    SELECT
        'fact lane keys resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_lane AS dimension
                ON fact.lane_key = dimension.lane_key
            WHERE dimension.lane_key IS NULL
        )

    UNION ALL

    SELECT
        'gross margin identity is consistent',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment
            WHERE gross_margin_usd IS DISTINCT FROM (
                customer_revenue_usd
                - carrier_cost_usd
                - claims_paid_usd
            )
        )

    UNION ALL

    SELECT
        'OTIF flag follows its documented rule',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment
            WHERE otif_flag IS DISTINCT FROM (
                CASE
                    WHEN final_on_time_flag IS NULL
                      OR shipment_fill_rate IS NULL
                    THEN NULL
                    WHEN final_on_time_flag = TRUE
                     AND shipment_fill_rate >= 1
                    THEN TRUE
                    ELSE FALSE
                END
            )
        )

    UNION ALL

    SELECT
        'valid CSAT responses do not exceed survey responses',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment
            WHERE valid_csat_response_count < 0
               OR valid_csat_response_count > survey_response_count
        )

    UNION ALL

    SELECT
        'CSAT averages have valid response counts',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment
            WHERE average_csat_score IS NOT NULL
              AND valid_csat_response_count = 0
        )

    UNION ALL

    SELECT
        'executive shipment total reconciles to fact',
        'CRITICAL',
        ABS(
            (
                SELECT total_shipments
                FROM mart.vw_executive_kpis
            )
            -
            (
                SELECT COUNT(*)
                FROM mart.fact_shipment
            )
        )

    UNION ALL

    SELECT
        'monthly shipment totals reconcile to fact',
        'CRITICAL',
        ABS(
            COALESCE(
                (
                    SELECT SUM(total_shipments)
                    FROM mart.vw_monthly_performance
                ),
                0
            )
            -
            (
                SELECT COUNT(*)
                FROM mart.fact_shipment
            )
        )

    UNION ALL

    SELECT
        'carrier scorecard totals reconcile to fact',
        'CRITICAL',
        ABS(
            COALESCE(
                (
                    SELECT SUM(total_shipments)
                    FROM mart.vw_carrier_scorecard
                ),
                0
            )
            -
            (
                SELECT COUNT(*)
                FROM mart.fact_shipment
            )
        )

    UNION ALL

    SELECT
        'warehouse scorecard totals reconcile to fact',
        'CRITICAL',
        ABS(
            COALESCE(
                (
                    SELECT SUM(total_shipments)
                    FROM mart.vw_warehouse_scorecard
                ),
                0
            )
            -
            (
                SELECT COUNT(*)
                FROM mart.fact_shipment
            )
        )

    UNION ALL

    SELECT
        'customer scorecard totals reconcile to fact',
        'CRITICAL',
        ABS(
            COALESCE(
                (
                    SELECT SUM(total_shipments)
                    FROM mart.vw_customer_scorecard
                ),
                0
            )
            -
            (
                SELECT COUNT(*)
                FROM mart.fact_shipment
            )
        )

    UNION ALL

    SELECT
        'lane scorecard totals reconcile to fact',
        'CRITICAL',
        ABS(
            COALESCE(
                (
                    SELECT SUM(total_shipments)
                    FROM mart.vw_lane_scorecard
                ),
                0
            )
            -
            (
                SELECT COUNT(*)
                FROM mart.fact_shipment
            )
        )

    UNION ALL

    SELECT
        'non-null fact ship dates resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_date AS dimension
                ON fact.ship_date = dimension.date_key
            WHERE fact.ship_date IS NOT NULL
              AND dimension.date_key IS NULL
        )

    UNION ALL

    SELECT
        'non-null promised dates resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_date AS dimension
                ON fact.promised_delivery_date = dimension.date_key
            WHERE fact.promised_delivery_date IS NOT NULL
              AND dimension.date_key IS NULL
        )

    UNION ALL

    SELECT
        'non-null actual delivery dates resolve',
        'CRITICAL',
        (
            SELECT COUNT(*)
            FROM mart.fact_shipment AS fact
            LEFT JOIN mart.dim_date AS dimension
                ON fact.actual_delivery_date = dimension.date_key
            WHERE fact.actual_delivery_date IS NOT NULL
              AND dimension.date_key IS NULL
        )

    UNION ALL

    SELECT
        'carrier accessorial cost reconciles to invoices',
        'CRITICAL',
        CASE
            WHEN ABS(
                COALESCE(
                    (
                        SELECT SUM(total_accessorial_usd)
                        FROM mart.fact_shipment
                    ),
                    0
                )
                -
                COALESCE(
                    (
                        SELECT SUM(invoice.accessorial_amount_usd)
                        FROM staging.stg_invoices AS invoice
                        INNER JOIN mart.fact_shipment AS fact
                            ON invoice.matched_tms_shipment_id
                               = fact.shipment_key
                        WHERE invoice.shipment_match_flag = TRUE
                          AND invoice.invoice_type = 'CARRIER_BILL'
                    ),
                    0
                )
            ) <= 0.01
            THEN 0
            ELSE 1
        END

    UNION ALL

    SELECT
        'carrier fuel surcharge cost reconciles to invoices',
        'CRITICAL',
        CASE
            WHEN ABS(
                COALESCE(
                    (
                        SELECT SUM(total_fuel_surcharge_usd)
                        FROM mart.fact_shipment
                    ),
                    0
                )
                -
                COALESCE(
                    (
                        SELECT SUM(invoice.fuel_surcharge_usd)
                        FROM staging.stg_invoices AS invoice
                        INNER JOIN mart.fact_shipment AS fact
                            ON invoice.matched_tms_shipment_id
                               = fact.shipment_key
                        WHERE invoice.shipment_match_flag = TRUE
                          AND invoice.invoice_type = 'CARRIER_BILL'
                    ),
                    0
                )
            ) <= 0.01
            THEN 0
            ELSE 1
        END
)

SELECT
    test_name,
    severity,
    failure_count,
    CASE
        WHEN failure_count = 0 THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM validation_results
ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'WARNING' THEN 2
        ELSE 3
    END,
    test_name;
