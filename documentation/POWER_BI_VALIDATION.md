# Power BI Validation and Portfolio Acceptance

Use this checklist before treating `Logistics_Control_Tower.pbix` as complete. It validates the semantic model, business definitions, interactions, performance, and portfolio presentation.

## 1. Refresh and model integrity

- [ ] All seven core Parquet queries refresh without errors.
- [ ] The six QA queries refresh, remain disconnected, and are hidden from report authors.
- [ ] `Fact Shipment[shipment_key]` contains no blanks or duplicates.
- [ ] Every dimension key on the one side is unique and nonblank.
- [ ] All eight relationships in `powerbi/MODEL_SPEC.md` exist with the intended active state.
- [ ] Cross-filter direction is single from dimension to fact.
- [ ] `Dim Date` is marked as the date table and covers the full fact date range.
- [ ] `Data Through Date` equals the latest `Fact Shipment[ship_date]` when the date slicer changes; it does not use the later calendar ceiling from `Dim Date`.
- [ ] Technical keys are hidden and IDs use **Do not summarize**.
- [ ] Rates are decimals formatted as percentages; they were not multiplied by 100 in Power Query.

The database-side control totals are available in `quality.star_schema_summary`. Refresh the database and exports before investigating any report mismatch.

## 2. Executive KPI reconciliation

With all report filters cleared, compare the DAX measures to the single row in `QA Executive KPIs`.

| DAX measure | QA column | Expected comparison |
|---|---|---|
| `Total Shipments` | `total_shipments` | Exact integer |
| `Official KPI Shipments` | `official_kpi_shipments` | Exact integer |
| `OTD Eligible Shipments` | `otd_eligible_shipments` | Exact integer |
| `On-Time Shipments` | `on_time_shipments` | Exact integer |
| `Late Shipments` | `late_shipments` | Exact integer |
| `On-Time Delivery %` | `on_time_delivery_rate` | Equal within 0.000001 |
| `OTIF Eligible Shipments` | `otif_eligible_shipments` | Exact integer |
| `OTIF Shipments` | `otif_shipments` | Exact integer |
| `OTIF %` | `otif_rate` | Equal within 0.000001 |
| `Average Fill Rate` | `average_fill_rate` | Equal within 0.000001 |
| `Full-Fill Eligible Shipments` | `full_fill_eligible_shipments` | Exact integer |
| `Full-Fill Shipments` | `full_fill_shipments` | Exact integer |
| `Full-Fill Rate` | `full_fill_rate` | Equal within 0.000001 |
| `Average Days Late` | `average_days_late` | Equal within 0.000001 |
| `Average Warehouse Cycle Hours` | `average_warehouse_cycle_hours` | Equal within 0.000001 |
| `Customer Revenue` | `customer_revenue_usd` | Equal within $0.01 |
| `Carrier Cost` | `carrier_cost_usd` | Equal within $0.01 |
| `Accessorial Cost` | `accessorial_cost_usd` | Equal within $0.01 |
| `Claims Paid` | `claims_paid_usd` | Equal within $0.01 |
| `Gross Margin` | `gross_margin_usd` | Equal within $0.01 |
| `Gross Margin %` | `gross_margin_percentage` | Equal within 0.000001 |
| `Shipments with Complaints` | `shipments_with_complaints` | Exact integer |
| `Complaint Rate` | `complaint_rate` | Equal within 0.000001 |
| `Shipments with Claims` | `shipments_with_claims` | Exact integer |
| `Claim Rate` | `claim_rate` | Equal within 0.000001 |
| `Average CSAT` | `average_csat_score` | Equal within 0.000001 |
| `Net Promoter Score` | `net_promoter_score` | Equal within 0.000001 |

`Average CSAT` must be response-weighted with
`valid_csat_response_count`; a simple average of shipment-level averages will
diverge when a shipment has more than one valid response. Survey coverage
continues to use `survey_response_count`.

If a value differs, first check filters, relationship direction, date role, and blank-denominator handling. Do not “fix” a discrepancy by changing a format or rounding the measure.

## 3. Slice-level reconciliation

Create a temporary QA page and perform these spot checks:

1. Select a month and compare volume, OTD, OTIF, fill rate, margin, complaint rate, claim rate, CSAT, and NPS to `QA Monthly Performance`.
2. Select one high-volume carrier and compare to `QA Carrier Scorecard`.
3. Select one warehouse and compare to `QA Warehouse Scorecard`.
4. Select one customer and compare to `QA Customer Scorecard`.
5. Select one lane and compare to `QA Lane Scorecard`.
6. Repeat one check for an `UNKNOWN` member if present.

Exact agreement is expected for the metrics present in each QA table. Differences usually indicate a missing official-KPI filter or an aggregate table accidentally connected to the model.

## 4. Behavioral tests

- [ ] A customer selection filters shipment, service, finance, claim, and experience measures together.
- [ ] A carrier selection does not remove the carrier's Unknown customer shipments unless a customer filter is also applied.
- [ ] The main date slicer uses shipment date.
- [ ] `Delivered Shipments (Actual Date)` and `Promised Shipments (Promised Date)` respond through their inactive relationships.
- [ ] Month names and year-month labels sort chronologically.
- [ ] A zero denominator returns blank, not infinity or an error.
- [ ] Selecting a visual does not silently retain a bookmark filter after Reset Filters.
- [ ] Drillthrough opens the intended shipment/customer/carrier context and the back button works.
- [ ] Minimum-volume filters are visible in subtitles or filter summaries on ranking visuals.

## 5. Data-quality communication

- [ ] The Data Quality page is included in the published report.
- [ ] Customer, carrier, warehouse, invoice, and WMS match rates are shown.
- [ ] Fill-rate and survey coverage are shown beside KPIs that depend on them.
- [ ] The synthetic-data notice is visible in the report information panel.
- [ ] The report states that official service KPIs use `official_kpi_eligible_flag`.
- [ ] CSAT and NPS are not described as representative of all shipments without reference to response coverage.
- [ ] Exploratory correlations are not phrased as causal findings.

## 6. Visual, accessibility, and performance review

- [ ] No page has more than six primary visuals, excluding slicers and navigation.
- [ ] Titles state the metric, comparison, unit, and date context where useful.
- [ ] Currency, percent, count, duration, and NPS formats are consistent.
- [ ] Negative margin and missed targets use a label/icon as well as color.
- [ ] All meaningful visuals have alt text and a logical tab order.
- [ ] Text and essential marks meet reasonable contrast on the imported theme.
- [ ] Matrix columns fit without horizontal scrolling on the default canvas when practical.
- [ ] Performance Analyzer shows no unexplained slow visual; inspect any visual over two seconds.
- [ ] High-cardinality shipment identifiers appear only on drillthrough/detail visuals.
- [ ] Auto date/time is disabled and unused fields are hidden.

## 7. Portfolio evidence package

A strong repository handoff includes all of the following:

- [ ] `powerbi/Logistics_Control_Tower.pbix`
- [ ] A PDF export of the report
- [ ] Four or more readable page screenshots in `images/`
- [ ] A model-view screenshot showing the star schema
- [ ] A short findings section with quantified insights and carefully scoped recommendations
- [ ] A root README section linking the PBIX/PDF/screenshots and explaining how to refresh the data
- [ ] A note listing the Power BI Desktop version used for final validation

The text assets in `powerbi/` make the model reproducible, but they do not substitute for an authored PBIX, final screenshots, or a human visual QA pass in Power BI Desktop.
