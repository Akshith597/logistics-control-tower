"""Interactive Streamlit companion for the Logistics Control Tower report.

The app reads only reviewed Parquet exports in data/public_dashboard. The workbook
and local DuckDB database stay out of the public deployment.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

APP_ROOT = Path(__file__).resolve().parent
DATA_ROOT = APP_ROOT / "data" / "public_dashboard"

st.set_page_config(
    page_title="Logistics Control Tower",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_model() -> dict[str, pd.DataFrame]:
    """Load the reviewed shipment-grain exports used by the dashboard."""

    required = {
        "fact": "fact_shipment.parquet",
        "carrier": "dim_carrier.parquet",
        "warehouse": "dim_warehouse.parquet",
    }
    missing = [
        filename
        for filename in required.values()
        if not (DATA_ROOT / filename).exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Missing dashboard exports: "
            + ", ".join(missing)
            + ". Run python python/run_pipeline.py first."
        )

    frames = {
        key: pd.read_parquet(DATA_ROOT / filename) for key, filename in required.items()
    }
    fact = frames["fact"]
    for date_column in (
        "ship_date",
        "promised_delivery_date",
        "actual_delivery_date",
    ):
        fact[date_column] = pd.to_datetime(fact[date_column], errors="coerce")

    carrier_names = frames["carrier"].set_index("carrier_key")["carrier_legal_name"]
    warehouse_names = frames["warehouse"].set_index("warehouse_key")["warehouse_name"]
    fact["carrier_name"] = (
        fact["carrier_key"].map(carrier_names).fillna("Unknown carrier")
    )
    fact["warehouse_name"] = (
        fact["warehouse_key"].map(warehouse_names).fillna("Unknown warehouse")
    )
    return frames


def safe_rate(numerator: int | float, denominator: int | float) -> float | None:
    """Return a ratio without presenting an undefined rate as zero."""

    if not denominator:
        return None
    return float(numerator) / float(denominator)


def display_rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def summarize(shipments: pd.DataFrame) -> dict[str, float | int | None]:
    """Recalculate KPI denominators at the current filtered shipment grain."""

    official = shipments[shipments["official_kpi_eligible_flag"].fillna(False)]
    otd = official[official["final_on_time_flag"].notna()]
    otif = official[official["otif_flag"].notna()]
    fill = official[official["shipment_fill_rate"].notna()]
    revenue = float(shipments["customer_revenue_usd"].fillna(0).sum())
    margin = float(shipments["gross_margin_usd"].fillna(0).sum())
    return {
        "shipments": len(shipments),
        "otd_eligible": len(otd),
        "otd_rate": safe_rate(otd["final_on_time_flag"].fillna(False).sum(), len(otd)),
        "otif_eligible": len(otif),
        "otif_rate": safe_rate(otif["otif_flag"].fillna(False).sum(), len(otif)),
        "full_fill_eligible": len(fill),
        "full_fill_rate": safe_rate((fill["shipment_fill_rate"] >= 1).sum(), len(fill)),
        "revenue": revenue,
        "margin": margin,
        "margin_rate": safe_rate(margin, revenue),
        "late_shipments": int((~otd["final_on_time_flag"].fillna(True)).sum()),
    }


def monthly_trend(shipments: pd.DataFrame) -> pd.DataFrame:
    """Build a monthly service trend from the filtered fact table."""

    dated = shipments[shipments["ship_date"].notna()].copy()
    if dated.empty:
        return pd.DataFrame()
    dated["month"] = dated["ship_date"].dt.to_period("M").dt.to_timestamp()
    rows: list[dict[str, object]] = []
    for month, group in dated.groupby("month", sort=True):
        metrics = summarize(group)
        rows.append(
            {
                "Month": month,
                "On-time delivery": metrics["otd_rate"],
                "OTIF": metrics["otif_rate"],
                "Full-fill": metrics["full_fill_rate"],
            }
        )
    return pd.DataFrame(rows).set_index("Month")


def download_links() -> None:
    pbix_url = (
        "https://github.com/Akshith597/logistics-control-tower/"
        "releases/latest/download/Logistics_Control_Tower.pbix"
    )
    data_url = (
        "https://github.com/Akshith597/logistics-control-tower/"
        "releases/latest/download/logistics_dashboard_data.zip"
    )
    source_url = "https://github.com/Akshith597/logistics-control-tower"
    st.markdown(
        f"""
        <div class="download-links">
          <a href="{pbix_url}" target="_blank">Download PBIX</a>
          <a href="{data_url}" target="_blank">Download data bundle</a>
          <a href="{source_url}" target="_blank">View source on GitHub</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


try:
    model = load_model()
except FileNotFoundError as error:
    st.error(str(error))
    st.stop()

fact = model["fact"]

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; padding-bottom: 3rem; }
      .hero { padding: 0.3rem 0 1.1rem; }
      .hero h1 { margin-bottom: 0.15rem; letter-spacing: -0.04em; }
      .hero p { color: #536273; font-size: 1.05rem; margin-top: 0; }
      .download-links {
        display: flex; gap: 1rem; flex-wrap: wrap; margin: 0.35rem 0 1.2rem;
      }
      .download-links a { color: #0b7285; font-weight: 650; text-decoration: none; }
      .download-links a:hover { text-decoration: underline; }
      [data-testid="stMetricValue"] { letter-spacing: -0.04em; }
    </style>
    <div class="hero">
      <h1>Logistics Control Tower</h1>
      <p>Shipment-grain service, fulfillment, profitability, and exception
      intelligence.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
download_links()
st.info(
    "Synthetic portfolio dataset · Rates are recalculated at the filtered "
    "shipment grain "
    "and shown with their eligible denominators."
)

with st.sidebar:
    st.header("Control tower filters")
    carrier_options = sorted(fact["carrier_name"].dropna().unique())
    warehouse_options = sorted(fact["warehouse_name"].dropna().unique())
    selected_carriers = st.multiselect("Carrier", carrier_options)
    selected_warehouses = st.multiselect("Warehouse", warehouse_options)

    dated_fact = fact[fact["ship_date"].notna()]
    min_date = dated_fact["ship_date"].min().date()
    max_date = dated_fact["ship_date"].max().date()
    selected_dates = st.date_input(
        "Shipment date",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    st.caption(
        "Undated source rows are not included in this browser view. "
        "The date control scopes the dashboard to dated shipments."
    )

filtered = fact.copy()
if selected_carriers:
    filtered = filtered[filtered["carrier_name"].isin(selected_carriers)]
if selected_warehouses:
    filtered = filtered[filtered["warehouse_name"].isin(selected_warehouses)]
if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
else:
    start_date = end_date = selected_dates
filtered = filtered[
    filtered["ship_date"].dt.date.between(start_date, end_date, inclusive="both")
]

metrics = summarize(filtered)
st.caption(
    f"Showing {metrics['shipments']:,} dated shipments · "
    f"{metrics['otd_eligible']:,} OTD-eligible · "
    f"{metrics['otif_eligible']:,} OTIF-eligible"
)

st.subheader("Executive pulse")
kpi_columns = st.columns(5)
kpi_columns[0].metric("Shipments", f"{metrics['shipments']:,}")
kpi_columns[1].metric(
    "On-time delivery",
    display_rate(metrics["otd_rate"]),
    help=(
        f"{metrics['otd_eligible']:,} eligible shipments with a resolved "
        "on-time result."
    ),
)
kpi_columns[2].metric(
    "OTIF",
    display_rate(metrics["otif_rate"]),
    help=(
        f"{metrics['otif_eligible']:,} eligible shipments with a resolved "
        "OTIF result."
    ),
)
kpi_columns[3].metric(
    "Full-fill",
    display_rate(metrics["full_fill_rate"]),
    help=(
        f"{metrics['full_fill_eligible']:,} eligible shipments with a known "
        "fill rate."
    ),
)
kpi_columns[4].metric("Revenue", f"${metrics['revenue'] / 1_000_000:.1f}M")

st.subheader("Service trajectory")
trend = monthly_trend(filtered)
if trend.empty:
    st.warning("No dated shipments match the current filters.")
else:
    st.line_chart(trend, y=["On-time delivery", "OTIF", "Full-fill"], height=320)

left, right = st.columns(2)
with left:
    st.subheader("Carrier performance")
    carrier_rows: list[dict[str, object]] = []
    for carrier, group in filtered.groupby("carrier_name", sort=True):
        summary = summarize(group)
        carrier_rows.append(
            {
                "Carrier": carrier,
                "Shipments": summary["shipments"],
                "OTD": summary["otd_rate"],
                "OTIF": summary["otif_rate"],
                "Late shipments": summary["late_shipments"],
            }
        )
    carrier_table = pd.DataFrame(
        carrier_rows,
        columns=["Carrier", "Shipments", "OTD", "OTIF", "Late shipments"],
    ).set_index("Carrier")
    if carrier_table.empty:
        st.info("No carrier rows match the current filters.")
    else:
        st.bar_chart(carrier_table[["OTD", "OTIF"]], height=300)
        st.dataframe(
            carrier_table.style.format(
                {
                    "OTD": "{:.1%}",
                    "OTIF": "{:.1%}",
                    "Shipments": "{:,.0f}",
                    "Late shipments": "{:,.0f}",
                }
            ),
            use_container_width=True,
        )

with right:
    st.subheader("Warehouse operations")
    warehouse_rows: list[dict[str, object]] = []
    for warehouse, group in filtered.groupby("warehouse_name", sort=True):
        summary = summarize(group)
        warehouse_rows.append(
            {
                "Warehouse": warehouse,
                "Shipments": summary["shipments"],
                "OTD": summary["otd_rate"],
                "OTIF": summary["otif_rate"],
                "Full-fill": summary["full_fill_rate"],
                "Margin rate": summary["margin_rate"],
            }
        )
    warehouse_table = pd.DataFrame(
        warehouse_rows,
        columns=["Warehouse", "Shipments", "OTD", "OTIF", "Full-fill", "Margin rate"],
    ).set_index("Warehouse")
    if warehouse_table.empty:
        st.info("No warehouse rows match the current filters.")
    else:
        st.bar_chart(warehouse_table[["OTD", "OTIF", "Full-fill"]], height=300)
        st.dataframe(
            warehouse_table.style.format(
                {
                    "OTD": "{:.1%}",
                    "OTIF": "{:.1%}",
                    "Full-fill": "{:.1%}",
                    "Margin rate": "{:.1%}",
                    "Shipments": "{:,.0f}",
                }
            ),
            use_container_width=True,
        )

st.subheader("Lane exception queue")
lane_source = filtered.assign(
    lane=(
        filtered["warehouse_name"]
        + " → "
        + filtered["dest_city"].fillna("Unknown city")
        + ", "
        + filtered["dest_state"].fillna("??")
    )
)
lane_table = (
    lane_source.groupby("lane", dropna=False)
    .agg(
        Shipments=("shipment_key", "size"),
        OTD=("final_on_time_flag", lambda values: values.dropna().mean()),
        OTIF=("otif_flag", lambda values: values.dropna().mean()),
        Late=("final_on_time_flag", lambda values: (~values.dropna()).sum()),
        Claims=("claim_flag", "sum"),
        Complaints=("complaint_flag", "sum"),
        Revenue=("customer_revenue_usd", "sum"),
        Margin=("gross_margin_usd", "sum"),
    )
    .sort_values(["Late", "Shipments"], ascending=False)
    .head(12)
)
if lane_table.empty:
    st.info("No lane exceptions match the current filters.")
else:
    st.dataframe(
        lane_table.style.format(
            {
                "OTD": "{:.1%}",
                "OTIF": "{:.1%}",
                "Shipments": "{:,.0f}",
                "Late": "{:,.0f}",
                "Claims": "{:,.0f}",
                "Complaints": "{:,.0f}",
                "Revenue": "${:,.0f}",
                "Margin": "${:,.0f}",
            }
        ),
        use_container_width=True,
    )

with st.expander("What this project demonstrates"):
    st.markdown(
        """
        **Python** builds a deterministic extraction, profiling, and insight pipeline.
        **SQL** stages and reconciles source systems into a shipment-grain DuckDB star
        schema with controlled fallbacks and fan-out protection. **Power BI** adds the
        semantic model, governed DAX measures, report pages, and data-quality review.
        This Streamlit companion recreates the decision-facing views from the reviewed
        Parquet exports so the work can be explored in a browser.

        The metrics are observations from a production-like synthetic dataset. Rates
        use their eligible denominators; association language is not causal evidence;
        survey measures are directional because response coverage is limited.
        """
    )
