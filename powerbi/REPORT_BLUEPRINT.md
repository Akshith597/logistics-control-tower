# Logistics Control Tower Report Blueprint

## Report conventions

- Canvas: 16:9, light neutral background, 24 px outer margin, consistent 12–16 px gutters.
- Header: page title on the left; date range, active filter count, and last data date on the right.
- Navigation: Overview, Service, Warehouse, Profitability, Customer, Shipment Detail, Data Quality.
- Global slicers: shipment date, mode, customer, carrier, warehouse, and destination state. Keep the first two visible and place the rest in a collapsible filter panel.
- Status: show a text label or icon in addition to red/amber/green color.
- Tooltip pages: one carrier tooltip and one customer tooltip, each showing volume, OTD, OTIF, margin, claims, and complaints.

## Page 1 — Executive Overview

**Question:** Are service and profitability healthy, and where should leadership act first?

| Area | Visual | Fields / measures |
|---|---|---|
| KPI strip | Six cards | `Total Shipments`, `On-Time Delivery %`, `OTIF %`, `Full-Fill Rate`, `Gross Margin %`, `Complaints per 1,000 Shipments` |
| Target context | KPI or card | `On-Time Delivery Target`, `OTD Variance to Target (pp)`, `OTD Status` |
| Trend | Line and clustered column chart | Axis `Dim Date[year_month]`; columns `Total Shipments`; lines `On-Time Delivery %`, `OTIF %` |
| Profit trend | Line chart | Axis `Dim Date[year_month]`; `Gross Margin`, `Gross Margin %` |
| Risk ranking | Bar chart | Top 10 `Dim Carrier[carrier_legal_name]` by `Late Shipments`; tooltip adds OTD, cost, and claims |
| Action queue | Matrix | Warehouse > carrier; shipments, OTD, OTIF, margin, claims, complaints; conditional formatting from target measures |

Add a short dynamic narrative that states selected shipment volume, the OTD target gap, margin direction, and the largest late-shipment contributor. Keep it descriptive; do not claim causation.

## Page 2 — Carrier & Lane Performance

**Question:** Which transportation partners and lanes combine poor service with high cost?

| Area | Visual | Fields / measures |
|---|---|---|
| KPI strip | Cards | `Official KPI Shipments`, `On-Time Delivery %`, `Average Days Late`, `Carrier Cost per Shipment`, `Claim Rate` |
| Carrier portfolio | Scatter chart | X `Carrier Cost per Shipment`; Y `On-Time Delivery %`; size `Total Shipments`; detail carrier; legend primary mode |
| Lane risk | Matrix | Origin warehouse > destination state > lane label; shipments, OTD, average days late, cost/shipment, margin % |
| Trend | Small multiples line chart | Axis year-month; OTD; small multiple carrier, filtered to selected/top carriers |
| Exceptions | Bar chart | `Fact Shipment[exception_code]` by `Late Shipments` |

Use a minimum-volume filter on ranking visuals so a one-shipment carrier or lane does not appear as the headline underperformer.

## Page 3 — Warehouse Operations

**Question:** Are fulfillment speed, fill rate, or short picks associated with service failures?

| Area | Visual | Fields / measures |
|---|---|---|
| KPI strip | Cards | `Average Warehouse Cycle Hours`, `Average Pick-to-Pack Hours`, `Average Pack-to-Ship Hours`, `Full-Fill Rate`, `Short Pick Rate`, `Average Inventory Accuracy` |
| Warehouse scorecard | Matrix | Warehouse; shipments, OTD, fill rate, cycle hours, short-pick rate, inventory accuracy |
| Cycle/service relationship | Scatter chart | X warehouse cycle hours; Y OTD; size shipments; detail warehouse |
| Trend | Line chart | Year-month; cycle hours, fill rate, OTD |
| Root-cause view | Decomposition tree | Analyze `Late Shipments`; explain by warehouse, mode, service level, short-pick flag, exception code |

Treat the decomposition tree as exploratory evidence. Operational delay and late delivery may share causes; the visual alone does not establish that one caused the other.

## Page 4 — Profitability

**Question:** Which customers and lanes destroy value, and is service recovery cost material?

| Area | Visual | Fields / measures |
|---|---|---|
| KPI strip | Cards | `Customer Revenue`, `Carrier Cost`, `Claims Paid`, `Gross Margin`, `Gross Margin %`, `Margin per Shipment` |
| Margin bridge | Waterfall | Revenue, carrier cost, claims paid, gross margin using measures or a small disconnected bridge table |
| Customer portfolio | Scatter chart | X revenue; Y gross margin %; size shipments; detail customer; legend industry |
| Lane ranking | Bar chart | Bottom lanes by gross margin, minimum-volume filtered |
| Detail | Matrix | Customer > lane; revenue, carrier cost, accessorial cost, claims paid, gross margin, margin % |

Use whole-dollar display units on detailed tables and compact units on cards. Make negative margin visible with both a minus sign and the theme's bad color.

## Page 5 — Customer Experience & Claims

**Question:** Where do operational failures translate into complaints, claims, and poor sentiment?

| Area | Visual | Fields / measures |
|---|---|---|
| KPI strip | Cards | `Complaint Rate`, `Complaints per 1,000 Shipments`, `Claim Rate`, `Claims Paid`, `Average CSAT`, `Net Promoter Score` |
| Service vs complaints | Scatter chart | X OTD; Y complaints per 1,000; size shipments; detail customer |
| Claims | Stacked bar or matrix | Carrier/customer by claim count and claims paid |
| Voice of customer trend | Line chart | Year-month; average CSAT and NPS; include response coverage in tooltip |
| Ticket severity | Column chart | Severe tickets and complaint tickets by customer or destination state |

Always display `Survey Response Coverage %` beside CSAT/NPS so sparse survey data is not presented as if it represents all shipments.

## Page 6 — Shipment Detail (drillthrough)

**Question:** What happened on a specific shipment?

- Drillthrough fields: shipment key, customer, carrier, warehouse, and lane.
- Header cards: shipment ID, status, mode/service, promised date, actual date, days late.
- Milestone/operations cards: tracking exceptions, warehouse cycle, pick-to-pack, pack-to-ship, fill rate, short-pick flag.
- Financial/customer cards: revenue, carrier cost, claims paid, gross margin, ticket count, CSAT, shipment NPS.
- Detail table: shipment ID, sales order, PO, BOL, PRO, tracking number, destination, exception code.
- Add a back button and a “Copy shipment ID” affordance if the delivery environment supports it.

## Page 7 — Data Quality & Coverage

**Question:** How much confidence should the audience place in each part of the analysis?

| Area | Visual | Fields / measures |
|---|---|---|
| Match cards | Cards | `Customer Match Rate`, `Carrier Match Rate`, `Warehouse Match Rate`, `Invoice Match Rate`, `WMS Match Rate` |
| KPI coverage | Cards | `Ship Date Coverage %`, `Shipments Missing Ship Date`, `Revenue Missing Ship Date`, `Fill Rate Coverage %`, `Survey Response Coverage %`, `OTD Eligible Shipments`, `OTIF Eligible Shipments` |
| Unknowns | Matrix | Dimension and unknown shipment count, derived from total minus matched shipments |
| Coverage trend | Line chart | Monthly invoice/WMS/survey coverage |
| QA note | Text box | Data source, synthetic-data notice, shipment grain, refresh timestamp, official KPI eligibility rule |

This page should remain in the published portfolio. It demonstrates that the report communicates data limitations rather than hiding them.

Label date-axis visuals with the note: “Monthly trends include shipments with a known ship date; undated shipments are reported on the Data Quality page.” The missing-date measures intentionally ignore only the `Dim Date` filter, so they remain visible when a date slicer is active while continuing to respect customer, carrier, warehouse, service, and lane selections.

## Interaction and QA rules

- Slicers filter all visuals on a page; detail selections should highlight rather than unexpectedly clear unrelated visuals.
- Sync the global date and mode slicers across all analytical pages, not the drillthrough page.
- Disable interactions from ranking charts to target/definition text.
- Use carrier and customer tooltip pages for dense context instead of adding more visuals to the main canvas.
- Keep the QA tables out of the field list used by report visuals.
- Use bookmarks only for navigation or the filter panel; do not use them to preserve hidden analytical filters.
