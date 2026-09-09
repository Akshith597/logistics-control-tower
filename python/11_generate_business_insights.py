"""Generate portfolio-ready findings from the curated Power BI model.

This step reads the same star-schema exports used by Power BI. Keeping the
analysis on that semantic layer makes every published metric reconcilable to the
dashboard and avoids maintaining a second definition of the business logic.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from pipeline_config import REPORT_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "data" / "powerbi"

MIN_CARRIER_OTD_ELIGIBLE = 1_000
MIN_LANE_OTIF_ELIGIBLE = 250
MIN_ACTIVE_CUSTOMER_SHIPMENTS = 1_000


def read_model_table(name: str, required_columns: set[str]) -> pd.DataFrame:
    """Read a model table and fail with a useful schema error."""
    path = MODEL_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing Power BI export: {path}\n"
            "Run the pipeline through the export step first."
        )

    dataframe = pd.read_parquet(path)
    missing_columns = required_columns - set(dataframe.columns)
    if missing_columns:
        raise ValueError(
            f"{path.name} is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )
    return dataframe


def safe_ratio(numerator: float | int, denominator: float | int) -> float:
    """Return a ratio or NaN when it cannot be interpreted safely."""
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return float("nan")
    return float(numerator) / float(denominator)


def format_number(value: float | int) -> str:
    return f"{value:,.0f}"


def format_currency(value: float | int) -> str:
    return f"${value / 1_000_000:,.1f}M"


def format_percent(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value:.1%}"


def format_multiple(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value:.1f}x"


def markdown_table(dataframe: pd.DataFrame) -> str:
    """Render a small dataframe as Markdown without an extra dependency."""
    display = dataframe.fillna("").astype(str)
    headers = [str(column) for column in display.columns]
    rows = [headers, ["---"] * len(headers)]
    rows.extend(display.itertuples(index=False, name=None))
    return "\n".join(
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in rows
    )


def build_analysis_context(fact: pd.DataFrame) -> dict[str, object]:
    """Calculate denominators, coverage, and data-quality context once."""
    official = fact["official_kpi_eligible_flag"].fillna(False).astype(bool)
    otd_eligible = official & fact["final_on_time_flag"].notna()
    otif_eligible = official & fact["otif_flag"].notna()
    fill_measured = official & fact["shipment_fill_rate"].notna()
    otif_failures = otif_eligible & fact["otif_flag"].eq(False)
    on_time_underfilled = (
        otif_eligible
        & fact["final_on_time_flag"].eq(True)
        & fact["shipment_fill_rate"].lt(1)
    )
    surveyed = fact["survey_response_count"].fillna(0).gt(0)
    ship_dates = pd.to_datetime(fact["ship_date"], errors="coerce")
    delivered = fact["shipment_status"].astype("string").str.upper().eq("DELIVERED")
    unknown_customer = (
        fact["customer_key"].isna()
        | fact["customer_key"].astype("string").str.upper().eq("UNKNOWN")
    )

    return {
        "total_shipments": len(fact),
        "otd_eligible_shipments": int(otd_eligible.sum()),
        "otif_eligible_shipments": int(otif_eligible.sum()),
        "fill_measured_shipments": int(fill_measured.sum()),
        "full_fill_shipments": int(
            (fill_measured & fact["shipment_fill_rate"].ge(1)).sum()
        ),
        "full_fill_rate": safe_ratio(
            (fill_measured & fact["shipment_fill_rate"].ge(1)).sum(),
            fill_measured.sum(),
        ),
        "underfilled_rate": safe_ratio(
            (fill_measured & fact["shipment_fill_rate"].lt(1)).sum(),
            fill_measured.sum(),
        ),
        "otif_failure_shipments": int(otif_failures.sum()),
        "on_time_underfilled_shipments": int(on_time_underfilled.sum()),
        "on_time_underfilled_share_of_otif_failures": safe_ratio(
            on_time_underfilled.sum(), otif_failures.sum()
        ),
        "surveyed_shipments": int(surveyed.sum()),
        "survey_response_coverage": safe_ratio(surveyed.sum(), len(fact)),
        "first_ship_date": ship_dates.min(),
        "last_ship_date": ship_dates.max(),
        "missing_ship_date_shipments": int(ship_dates.isna().sum()),
        "missing_otd_result_shipments": int((official & ~otd_eligible).sum()),
        "missing_otif_result_shipments": int((official & ~otif_eligible).sum()),
        "unknown_customer_shipments": int(unknown_customer.sum()),
        "delivered_missing_delivery_date_shipments": int(
            (delivered & fact["actual_delivery_date"].isna()).sum()
        ),
    }


def build_executive_summary(
    executive: pd.Series, context: dict[str, object]
) -> pd.DataFrame:
    metrics = [
        ("Total shipments", executive["total_shipments"], format_number),
        (
            "Official KPI shipments",
            executive["official_kpi_shipments"],
            format_number,
        ),
        (
            "OTD eligible shipments",
            context["otd_eligible_shipments"],
            format_number,
        ),
        (
            "On-time delivery rate",
            executive["on_time_delivery_rate"],
            format_percent,
        ),
        (
            "OTIF eligible shipments",
            context["otif_eligible_shipments"],
            format_number,
        ),
        ("OTIF rate", executive["otif_rate"], format_percent),
        ("Average fill rate", executive["average_fill_rate"], format_percent),
        ("Full-fill rate", context["full_fill_rate"], format_percent),
        (
            "Average days late",
            executive["average_days_late"],
            lambda value: f"{value:,.2f}",
        ),
        (
            "Customer revenue",
            executive["customer_revenue_usd"],
            format_currency,
        ),
        ("Gross margin", executive["gross_margin_usd"], format_currency),
        (
            "Gross margin rate",
            executive["gross_margin_percentage"],
            format_percent,
        ),
        ("Complaint rate", executive["complaint_rate"], format_percent),
        ("Claim rate", executive["claim_rate"], format_percent),
        (
            "Survey response coverage",
            context["survey_response_coverage"],
            format_percent,
        ),
        (
            "Average CSAT",
            executive["average_csat_score"],
            lambda value: f"{value:,.2f} / 5",
        ),
        (
            "Net promoter score",
            executive["net_promoter_score"],
            lambda value: f"{value:,.1f}",
        ),
    ]
    return pd.DataFrame(
        {
            "metric": [metric for metric, _, _ in metrics],
            "value": [value for _, value, _ in metrics],
            "formatted_value": [formatter(value) for _, value, formatter in metrics],
        }
    )


def build_delivery_impact(fact: pd.DataFrame) -> pd.DataFrame:
    official = fact["official_kpi_eligible_flag"].fillna(False).astype(bool)
    eligible = fact.loc[official & fact["final_on_time_flag"].notna()].copy()
    csat_count_column = (
        "valid_csat_response_count"
        if "valid_csat_response_count" in eligible.columns
        else "survey_response_count"
    )
    eligible["csat_weight"] = (
        eligible[csat_count_column]
        .fillna(0)
        .where(eligible["average_csat_score"].notna(), 0)
    )
    eligible["weighted_csat_score"] = (
        eligible["average_csat_score"].fillna(0)
        * eligible["csat_weight"]
    )

    grouped = (
        eligible.groupby("final_on_time_flag", dropna=False)
        .agg(
            shipments=("shipment_key", "size"),
            complaint_rate=("complaint_flag", "mean"),
            claim_rate=("claim_flag", "mean"),
            csat_observations=("csat_weight", "sum"),
            weighted_csat_score=("weighted_csat_score", "sum"),
            average_days_late=("days_late", "mean"),
        )
        .reset_index()
    )
    grouped["average_csat"] = grouped.apply(
        lambda row: safe_ratio(
            row["weighted_csat_score"], row["csat_observations"]
        ),
        axis=1,
    )
    grouped["delivery_status"] = grouped["final_on_time_flag"].map(
        {True: "On time", False: "Late"}
    )
    return grouped[
        [
            "delivery_status",
            "shipments",
            "complaint_rate",
            "claim_rate",
            "csat_observations",
            "average_csat",
            "average_days_late",
        ]
    ].sort_values("delivery_status")


def add_eligibility_counts(
    scorecard: pd.DataFrame, fact: pd.DataFrame, key: str
) -> pd.DataFrame:
    """Attach exact rate denominators to a SQL scorecard."""
    working = fact[
        [key, "official_kpi_eligible_flag", "final_on_time_flag", "otif_flag"]
    ].copy()
    official = working["official_kpi_eligible_flag"].fillna(False).astype(bool)
    working["otd_eligible_row"] = (
        official & working["final_on_time_flag"].notna()
    ).astype(int)
    working["on_time_row"] = (
        official & working["final_on_time_flag"].eq(True)
    ).astype(int)
    working["otif_eligible_row"] = (
        official & working["otif_flag"].notna()
    ).astype(int)
    working["otif_row"] = (official & working["otif_flag"].eq(True)).astype(int)

    denominators = (
        working.groupby(key, dropna=False)
        .agg(
            otd_eligible_shipments=("otd_eligible_row", "sum"),
            on_time_shipments=("on_time_row", "sum"),
            otif_eligible_shipments=("otif_eligible_row", "sum"),
            otif_shipments=("otif_row", "sum"),
        )
        .reset_index()
    )
    # Current KPI views expose these governed numerators and denominators.
    # Dropping them here keeps this helper compatible with both refreshed
    # extracts and older exports that predate the explicit fields.
    governed_columns = [
        "otd_eligible_shipments",
        "on_time_shipments",
        "otif_eligible_shipments",
        "otif_shipments",
    ]
    scorecard = scorecard.drop(
        columns=[column for column in governed_columns if column in scorecard.columns]
    )
    return scorecard.merge(denominators, on=key, how="left", validate="one_to_one")


def prepare_opportunity_tables(
    fact: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    carriers = read_model_table(
        "vw_carrier_scorecard",
        {
            "carrier_key",
            "carrier_legal_name",
            "primary_mode",
            "official_kpi_shipments",
            "late_shipments",
            "on_time_delivery_rate",
            "otif_rate",
            "claim_rate",
            "gross_margin_percentage",
        },
    )
    carriers = add_eligibility_counts(carriers, fact, "carrier_key")
    carriers = (
        carriers.loc[
            carriers["otd_eligible_shipments"] >= MIN_CARRIER_OTD_ELIGIBLE
        ]
        .dropna(subset=["on_time_delivery_rate"])
        .sort_values(
            ["on_time_delivery_rate", "late_shipments"],
            ascending=[True, False],
        )
        .head(10)
        .reset_index(drop=True)
    )
    carriers.insert(0, "rate_rank", range(1, len(carriers) + 1))

    lanes = read_model_table(
        "vw_lane_scorecard",
        {
            "lane_key",
            "origin_warehouse_name",
            "destination_city",
            "destination_state",
            "official_kpi_shipments",
            "late_shipments",
            "on_time_delivery_rate",
            "otif_rate",
            "gross_margin_percentage",
        },
    )
    lanes = add_eligibility_counts(lanes, fact, "lane_key")
    lanes = (
        lanes.loc[lanes["otif_eligible_shipments"] >= MIN_LANE_OTIF_ELIGIBLE]
        .dropna(subset=["otif_rate"])
        .sort_values(["otif_rate", "late_shipments"], ascending=[True, False])
        .head(15)
        .reset_index(drop=True)
    )
    lanes.insert(0, "rate_rank", range(1, len(lanes) + 1))

    customers = read_model_table(
        "vw_customer_scorecard",
        {
            "legal_name",
            "industry",
            "customer_status",
            "total_shipments",
            "gross_margin_percentage",
            "complaint_rate",
            "average_csat_score",
        },
    )
    active = customers["customer_status"].astype("string").str.upper().eq("ACTIVE")
    customers = (
        customers.loc[
            active & (customers["total_shipments"] >= MIN_ACTIVE_CUSTOMER_SHIPMENTS)
        ]
        .dropna(subset=["gross_margin_percentage"])
        .sort_values(
            ["gross_margin_percentage", "total_shipments"],
            ascending=[True, False],
        )
        .head(10)
        .reset_index(drop=True)
    )
    customers.insert(0, "margin_rate_rank", range(1, len(customers) + 1))
    return carriers, lanes, customers


def context_dataframe(context: dict[str, object]) -> pd.DataFrame:
    values = []
    for metric, value in context.items():
        if isinstance(value, pd.Timestamp):
            value = value.date().isoformat()
        values.append({"metric": metric, "value": value})
    return pd.DataFrame(values)


def build_markdown_report(
    executive: pd.Series,
    context: dict[str, object],
    delivery_impact: pd.DataFrame,
    carriers: pd.DataFrame,
    lanes: pd.DataFrame,
    customers: pd.DataFrame,
) -> str:
    impact = delivery_impact.set_index("delivery_status")
    late = impact.loc["Late"]
    on_time = impact.loc["On time"]
    complaint_multiplier = safe_ratio(
        late["complaint_rate"], on_time["complaint_rate"]
    )
    claim_multiplier = safe_ratio(late["claim_rate"], on_time["claim_rate"])
    csat_gap = on_time["average_csat"] - late["average_csat"]

    carrier = carriers.iloc[0]
    lane = lanes.iloc[0]
    customer = customers.iloc[0]

    carrier_display = carriers.head(5)[
        [
            "rate_rank",
            "carrier_legal_name",
            "primary_mode",
            "otd_eligible_shipments",
            "late_shipments",
            "on_time_delivery_rate",
            "otif_rate",
        ]
    ].copy()
    carrier_display.columns = [
        "Rank",
        "Carrier",
        "Mode",
        "OTD eligible",
        "Late",
        "OTD",
        "OTIF",
    ]
    for column in ["OTD eligible", "Late"]:
        carrier_display[column] = carrier_display[column].map(format_number)
    carrier_display["OTD"] = carrier_display["OTD"].map(format_percent)
    carrier_display["OTIF"] = carrier_display["OTIF"].map(format_percent)

    lane_display = lanes.head(5)[
        [
            "rate_rank",
            "origin_warehouse_name",
            "destination_city",
            "destination_state",
            "otif_eligible_shipments",
            "otif_shipments",
            "otif_rate",
        ]
    ].copy()
    lane_display["Destination"] = (
        lane_display["destination_city"] + ", " + lane_display["destination_state"]
    )
    lane_display = lane_display[
        [
            "rate_rank",
            "origin_warehouse_name",
            "Destination",
            "otif_eligible_shipments",
            "otif_shipments",
            "otif_rate",
        ]
    ]
    lane_display.columns = [
        "Rank",
        "Origin",
        "Destination",
        "OTIF eligible",
        "OTIF shipments",
        "OTIF",
    ]
    for column in ["OTIF eligible", "OTIF shipments"]:
        lane_display[column] = lane_display[column].map(format_number)
    lane_display["OTIF"] = lane_display["OTIF"].map(format_percent)

    first_date = context["first_ship_date"].strftime("%B %d, %Y")
    last_date = context["last_ship_date"].strftime("%B %d, %Y")

    return f"""# Logistics Control Tower: business findings

Generated from the curated Power BI model by `python/11_generate_business_insights.py`.
The source is a production-like synthetic dataset; these findings demonstrate
the analysis workflow and are not claims about a real company.

## Scope and coverage

- The model contains **{format_number(executive['total_shipments'])} final-live,
  non-test shipments**. Dated shipments span **{first_date} to {last_date}**;
  **{format_number(context['missing_ship_date_shipments'])}** shipments have no
  shipment date and appear only in unfiltered totals.
- Official KPI status applies to
  **{format_number(executive['official_kpi_shipments'])}** shipments. OTD has
  **{format_number(context['otd_eligible_shipments'])}** resolved results and
  OTIF has **{format_number(context['otif_eligible_shipments'])}** resolved
  results. Rate cards must display these denominators.
- Only **{format_number(context['surveyed_shipments'])} shipments
  ({format_percent(context['survey_response_coverage'])})** have a survey
  response. CSAT and NPS are directional signals subject to non-response bias.

## Executive readout

- **On-time delivery is {format_percent(executive['on_time_delivery_rate'])}**:
  {format_number(executive['on_time_shipments'])} of
  {format_number(context['otd_eligible_shipments'])} OTD-eligible shipments.
  **{format_number(context['missing_otd_result_shipments'])}** official KPI
  shipments lack a resolved OTD result.
- **OTIF is {format_percent(executive['otif_rate'])}**:
  {format_number(executive['otif_shipments'])} of
  {format_number(context['otif_eligible_shipments'])} OTIF-eligible shipments.
  The average fill rate is {format_percent(executive['average_fill_rate'])}, but
  the more decision-useful full-fill rate is only
  **{format_percent(context['full_fill_rate'])}**. There are
  **{format_number(context['on_time_underfilled_shipments'])}** on-time but
  underfilled shipments, representing
  **{format_percent(context['on_time_underfilled_share_of_otif_failures'])}** of
  known OTIF failures.
- The network generated **{format_currency(executive['customer_revenue_usd'])}**
  in revenue and **{format_currency(executive['gross_margin_usd'])}** in gross
  margin, a **{format_percent(executive['gross_margin_percentage'])}** aggregate
  margin rate.
- Surveyed shipments average **{executive['average_csat_score']:.2f}/5 CSAT** and
  **{executive['net_promoter_score']:.1f} NPS**. The low
  {format_percent(context['survey_response_coverage'])} response coverage means
  these scores should not be generalized to all shipments without follow-up.

## What changes when a shipment is late

For official KPI shipments with a resolved OTD result:

- Complaints occur on **{format_percent(late['complaint_rate'])}** of late
  shipments versus **{format_percent(on_time['complaint_rate'])}** of on-time
  shipments—a **{format_multiple(complaint_multiplier)}** association.
- The claim rate rises from **{format_percent(on_time['claim_rate'])}** to
  **{format_percent(late['claim_rate'])}**
  (**{format_multiple(claim_multiplier)}**).
- Average CSAT falls from **{on_time['average_csat']:.2f}** across
  **{format_number(on_time['csat_observations'])} responses** to
  **{late['average_csat']:.2f}** across
  **{format_number(late['csat_observations'])} responses**, a
  **{csat_gap:.2f}-point** gap.

These are associations, not causal estimates. They make service-failure
prevention a strong hypothesis to test while keeping survey-selection bias in
view.

## Lowest-performing segments by rate

These are volume-guarded rate rankings, not estimates of recoverable financial
impact. Use late counts and cost/margin measures to sequence action.

**Carrier OTD.** Among carriers with at least
{format_number(MIN_CARRIER_OTD_ELIGIBLE)} OTD-eligible shipments,
**{carrier['carrier_legal_name']}** has the lowest OTD at
**{format_percent(carrier['on_time_delivery_rate'])}**
({format_number(carrier['on_time_shipments'])} of
{format_number(carrier['otd_eligible_shipments'])}), with
**{format_number(carrier['late_shipments'])} late shipments**.

{markdown_table(carrier_display)}

**Lane OTIF.** Among lanes with at least
{format_number(MIN_LANE_OTIF_ELIGIBLE)} OTIF-eligible shipments, the lowest OTIF
lane is **{lane['origin_warehouse_name']} to {lane['destination_city']},
{lane['destination_state']}** at **{format_percent(lane['otif_rate'])}**
({format_number(lane['otif_shipments'])} of
{format_number(lane['otif_eligible_shipments'])}). Drill through by carrier,
warehouse, and service before assigning root cause.

{markdown_table(lane_display)}

**Active-customer profitability.** Among active customers with at least
{format_number(MIN_ACTIVE_CUSTOMER_SHIPMENTS)} shipments,
**{customer['legal_name']}** has the lowest aggregate gross-margin rate at
**{format_percent(customer['gross_margin_percentage'])}**. Validate accessorial
recovery, contracted rates, service mix, and claims before repricing.

## Data-quality action queue

1. Resolve the **{format_number(context['delivered_missing_delivery_date_shipments'])}**
   delivered fact rows without an actual delivery date; this is the largest OTD
   coverage issue.
2. Investigate the **{format_number(context['missing_otif_result_shipments'])}**
   official shipments without a resolved OTIF result, separating missing OTD from
   missing line/fill data.
3. Preserve the controlled customer fallback logic: only
   **{format_number(context['unknown_customer_shipments'])}** modeled shipments
   remain on the Unknown customer member after reconciliation.

## Recommended 30/60/90-day actions

1. **30 days:** assign owners to OTD/OTIF completeness, delivery timestamps, and
   full-fill exceptions; publish eligible counts beside every rate.
2. **60 days:** review high-volume carrier/lane combinations using rate, failure
   count, cost, claims, and complaints together—not rate alone.
3. **90 days:** pilot routing-guide, service-level, or fulfillment changes on a
   small set of underperforming segments and evaluate pre/post service, cost,
   claims, and customer feedback before scaling.

## Interpretation notes

- Ranking thresholds are analytical guardrails, not business policy:
  {format_number(MIN_CARRIER_OTD_ELIGIBLE)} OTD-eligible carrier shipments,
  {format_number(MIN_LANE_OTIF_ELIGIBLE)} OTIF-eligible lane shipments, and
  {format_number(MIN_ACTIVE_CUSTOMER_SHIPMENTS)} active-customer shipments.
- Full-fill means `shipment_fill_rate >= 1`; average fill rate alone can hide a
  meaningful number of partially filled shipments.
- Gross-margin rate is calculated from aggregate revenue and margin, not by
  averaging shipment-level percentages.
"""


def generate_business_insights() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    executive_table = read_model_table(
        "vw_executive_kpis",
        {
            "total_shipments",
            "official_kpi_shipments",
            "on_time_shipments",
            "on_time_delivery_rate",
            "otif_shipments",
            "otif_rate",
            "average_fill_rate",
            "average_days_late",
            "customer_revenue_usd",
            "gross_margin_usd",
            "gross_margin_percentage",
            "complaint_rate",
            "claim_rate",
            "average_csat_score",
            "net_promoter_score",
        },
    )
    if len(executive_table) != 1:
        raise ValueError("vw_executive_kpis must contain exactly one row.")
    executive = executive_table.iloc[0]

    fact = read_model_table(
        "fact_shipment",
        {
            "shipment_key",
            "customer_key",
            "carrier_key",
            "lane_key",
            "ship_date",
            "actual_delivery_date",
            "shipment_status",
            "official_kpi_eligible_flag",
            "final_on_time_flag",
            "otif_flag",
            "shipment_fill_rate",
            "complaint_flag",
            "claim_flag",
            "survey_response_count",
            "valid_csat_response_count",
            "average_csat_score",
            "days_late",
        },
    )
    context = build_analysis_context(fact)
    delivery_impact = build_delivery_impact(fact)
    carriers, lanes, customers = prepare_opportunity_tables(fact)

    if set(delivery_impact["delivery_status"]) != {"Late", "On time"}:
        raise ValueError("Both late and on-time comparison groups are required.")
    if carriers.empty or lanes.empty or customers.empty:
        raise ValueError("One or more volume-guarded opportunity tables are empty.")

    executive_summary = build_executive_summary(executive, context)
    executive_summary.to_csv(REPORT_DIR / "executive_summary.csv", index=False)
    context_dataframe(context).to_csv(
        REPORT_DIR / "analysis_context.csv", index=False
    )
    delivery_impact.to_csv(
        REPORT_DIR / "customer_impact_by_delivery_status.csv", index=False
    )
    carriers.to_csv(REPORT_DIR / "carrier_opportunities.csv", index=False)
    lanes.to_csv(REPORT_DIR / "lane_opportunities.csv", index=False)
    customers.to_csv(
        REPORT_DIR / "customer_profitability_opportunities.csv", index=False
    )

    report = build_markdown_report(
        executive, context, delivery_impact, carriers, lanes, customers
    )
    report_path = REPORT_DIR / "business_insights.md"
    report_path.write_text(report, encoding="utf-8")

    print("Business insight outputs created:")
    for name in (
        "executive_summary.csv",
        "analysis_context.csv",
        "customer_impact_by_delivery_status.csv",
        "carrier_opportunities.csv",
        "lane_opportunities.csv",
        "customer_profitability_opportunities.csv",
        "business_insights.md",
    ):
        print(f"  {(REPORT_DIR / name).relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    generate_business_insights()
