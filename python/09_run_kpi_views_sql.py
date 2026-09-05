from pipeline_config import KPI_VIEWS, PROJECT_ROOT
from pipeline_utils import duckdb_transaction, require_file

DATABASE_FILE = PROJECT_ROOT / "database" / "logistics.duckdb"
SQL_FILE = PROJECT_ROOT / "sql" / "06_create_kpi_views.sql"


def run_sql(database_file=DATABASE_FILE, sql_file=SQL_FILE):
    sql_file = require_file(sql_file, "SQL file")
    sql = sql_file.read_text(encoding="utf-8")

    with duckdb_transaction(database_file) as connection:
        print("Creating KPI views...")
        connection.execute(sql)

        created_views = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'mart'
                """
            ).fetchall()
        }

        missing_views = set(KPI_VIEWS) - created_views
        if missing_views:
            raise RuntimeError(
                "Missing KPI views: " + ", ".join(sorted(missing_views))
            )

        fact_totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_shipments,
                COUNT(*) FILTER (
                    WHERE official_kpi_eligible_flag = TRUE
                ) AS official_kpi_shipments
            FROM mart.fact_shipment
            """
        ).fetchone()

        executive_totals = connection.execute(
            """
            SELECT total_shipments, official_kpi_shipments
            FROM mart.vw_executive_kpis
            """
        ).fetchone()

        if executive_totals != fact_totals:
            raise RuntimeError(
                "Executive KPI totals do not reconcile to fact_shipment."
            )

        monthly_total = connection.execute(
            """
            SELECT SUM(total_shipments)
            FROM mart.vw_monthly_performance
            """
        ).fetchone()[0]

        if monthly_total != fact_totals[0]:
            raise RuntimeError(
                "Monthly shipment totals do not reconcile to fact_shipment."
            )

        print()
        print("KPI-view validation:")
        print("-" * 72)
        print(f"{'View':38} {'Rows':>12} {'Shipment total':>18}")
        print("-" * 72)

        for view_name in KPI_VIEWS:
            row_count = connection.execute(
                f"SELECT COUNT(*) FROM mart.{view_name}"
            ).fetchone()[0]

            if view_name == "vw_executive_kpis":
                shipment_total = executive_totals[0]
            elif view_name == "vw_monthly_performance":
                shipment_total = monthly_total
            else:
                shipment_total = connection.execute(
                    f"SELECT SUM(total_shipments) FROM mart.{view_name}"
                ).fetchone()[0]

            if shipment_total != fact_totals[0]:
                raise RuntimeError(
                    f"{view_name} shipment total does not reconcile "
                    "to fact_shipment."
                )

            print(
                f"mart.{view_name:33} "
                f"{row_count:12,} {shipment_total:18,}"
            )

        executive_row = connection.execute(
            """
            SELECT
                total_shipments,
                official_kpi_shipments,
                on_time_delivery_rate,
                otif_rate,
                average_fill_rate,
                customer_revenue_usd,
                gross_margin_usd,
                gross_margin_percentage,
                complaint_rate,
                claim_rate,
                average_csat_score,
                net_promoter_score
            FROM mart.vw_executive_kpis
            """
        ).fetchone()

        print()
        print("Executive KPI sample:")
        print("-" * 72)
        labels = (
            "Total shipments",
            "Official KPI shipments",
            "On-time delivery rate",
            "OTIF rate",
            "Average fill rate",
            "Customer revenue (USD)",
            "Gross margin (USD)",
            "Gross margin percentage",
            "Complaint rate",
            "Claim rate",
            "Average CSAT score",
            "Net promoter score",
        )

        for label, value in zip(labels, executive_row, strict=True):
            print(f"{label}: {value}")

    print()
    print("KPI views completed and validated successfully.")


if __name__ == "__main__":
    run_sql()
