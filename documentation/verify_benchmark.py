"""Print benchmark totals and illustrative decision scenarios after a rebuild."""

from pathlib import Path

import duckdb

root = Path(__file__).resolve().parents[1]
with duckdb.connect(str(root / "database/logistics.duckdb"), read_only=True) as con:
    executive = con.execute("SELECT * FROM mart.vw_executive_kpis").fetchdf()
    expected = {
        "total_shipments": 98_595,
        "customer_revenue_usd": 72_336_827.17,
        "otd_eligible_shipments": 78_452,
        "on_time_shipments": 59_986,
        "otif_eligible_shipments": 74_198,
        "otif_shipments": 46_321,
    }
    for metric, target in expected.items():
        actual = float(executive.iloc[0][metric])
        if abs(actual - target) > 0.005:
            raise SystemExit(
                f"Benchmark mismatch: {metric}={actual}, expected {target}. "
                "Rebuild using the full-size release workbook."
            )
    print("Benchmark reconciliation passed.")
    print(executive.to_string(index=False))
    print(con.execute("""
        SELECT
            COUNT(*) AS shipments,
            SUM(customer_revenue_usd) AS revenue,
            SUM(carrier_cost_usd) AS carrier_cost,
            SUM(claims_paid_usd) AS paid_claims,
            SUM(customer_revenue_usd) * 0.01 AS one_percent_revenue_recovery,
            COUNT(*) FILTER (
                WHERE official_kpi_eligible_flag
                  AND final_on_time_flag = FALSE
            ) * 0.10 * 25 AS routing_pilot_net_benefit,
            COUNT(*) FILTER (
                WHERE official_kpi_eligible_flag
                  AND otif_flag IS NOT NULL
                  AND final_on_time_flag = TRUE
                  AND shipment_fill_rate < 1
            ) AS on_time_underfilled,
            COUNT(*) FILTER (
                WHERE official_kpi_eligible_flag
                  AND otif_flag IS NOT NULL
                  AND final_on_time_flag = TRUE
                  AND shipment_fill_rate < 1
            ) * 0.10 * 25 AS underfill_pilot_net_benefit
        FROM mart.fact_shipment
    """).fetchdf().to_string(index=False))
