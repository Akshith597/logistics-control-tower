# Logistics Control Tower: business findings

Generated from the curated Power BI model by `python/11_generate_business_insights.py`.
The source is a production-like synthetic dataset; these findings demonstrate
the analysis workflow and are not claims about a real company.

## Scope and coverage

- The model contains **98,595 final-live,
  non-test shipments**. Dated shipments span **January 02, 2024 to December 15, 2025**;
  **11,976** shipments have no
  shipment date and appear only in unfiltered totals.
- Official KPI status applies to
  **86,473** shipments. OTD has
  **78,452** resolved results and
  OTIF has **74,198** resolved
  results. Rate cards must display these denominators.
- Only **3,320 shipments
  (3.4%)** have a survey
  response. CSAT and NPS are directional signals subject to non-response bias.

## Executive readout

- **On-time delivery is 76.5%**:
  59,986 of
  78,452 OTD-eligible shipments.
  **8,021** official KPI
  shipments lack a resolved OTD result.
- **OTIF is 62.4%**:
  46,321 of
  74,198 OTIF-eligible shipments.
  The average fill rate is 98.7%, but
  the more decision-useful full-fill rate is only
  **81.4%**. There are
  **10,434** on-time but
  underfilled shipments, representing
  **37.4%** of
  known OTIF failures.
- The network generated **$72.3M**
  in revenue and **$48.3M** in gross
  margin, a **66.8%** aggregate
  margin rate.
- Surveyed shipments average **3.32/5 CSAT** and
  **-18.8 NPS**. The low
  3.4% response coverage means
  these scores should not be generalized to all shipments without follow-up.

## What changes when a shipment is late

For official KPI shipments with a resolved OTD result:

- Complaints occur on **6.0%** of late
  shipments versus **2.5%** of on-time
  shipments—a **2.4x** association.
- The claim rate rises from **1.2%** to
  **1.8%**
  (**1.5x**).
- Average CSAT falls from **3.66** across
  **2,231 responses** to
  **2.24** across
  **688 responses**, a
  **1.42-point** gap.

These are associations, not causal estimates. They make service-failure
prevention a strong hypothesis to test while keeping survey-selection bias in
view.

## Lowest-performing segments by rate

These are volume-guarded rate rankings, not estimates of recoverable financial
impact. Use late counts and cost/margin measures to sequence action.

**Carrier OTD.** Among carriers with at least
1,000 OTD-eligible shipments,
**StoneBridge Freight** has the lowest OTD at
**72.7%**
(2,554 of
3,511), with
**957 late shipments**.

| Rank | Carrier | Mode | OTD eligible | Late | OTD | OTIF |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | StoneBridge Freight | LTL | 3,511 | 957 | 72.7% | 58.6% |
| 2 | PriorityJet Cargo | AIR | 3,975 | 1,072 | 73.0% | 61.7% |
| 3 | NorthWind Carriers | LTL | 4,119 | 1,091 | 73.5% | 58.9% |
| 4 | Coastal Bridge Shipping | LTL | 5,093 | 1,340 | 73.7% | 58.2% |
| 5 | BlueArrow Logistics | LTL | 8,072 | 2,117 | 73.8% | 58.8% |

**Lane OTIF.** Among lanes with at least
250 OTIF-eligible shipments, the lowest OTIF
lane is **New Jersey Metro to Salt Lake City,
UT** at **55.6%**
(229 of
412). Drill through by carrier,
warehouse, and service before assigning root cause.

| Rank | Origin | Destination | OTIF eligible | OTIF shipments | OTIF |
| --- | --- | --- | --- | --- | --- |
| 1 | New Jersey Metro | Salt Lake City, UT | 412 | 229 | 55.6% |
| 2 | Los Angeles Inland | Denver, CO | 431 | 241 | 55.9% |
| 3 | Atlanta East | Miami, FL | 633 | 360 | 56.9% |
| 4 | Chicago Central | Indianapolis, IN | 461 | 264 | 57.3% |
| 5 | Dallas South | Charlotte, NC | 494 | 284 | 57.5% |

**Active-customer profitability.** Among active customers with at least
1,000 shipments,
**Harbor Home Goods Co** has the lowest aggregate gross-margin rate at
**63.7%**. Validate accessorial
recovery, contracted rates, service mix, and claims before repricing.

## Data-quality action queue

1. Resolve the **4,531**
   delivered fact rows without an actual delivery date; this is the largest OTD
   coverage issue.
2. Investigate the **12,275**
   official shipments without a resolved OTIF result, separating missing OTD from
   missing line/fill data.
3. Preserve the controlled customer fallback logic: only
   **7** modeled shipments
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
  1,000 OTD-eligible carrier shipments,
  250 OTIF-eligible lane shipments, and
  1,000 active-customer shipments.
- Full-fill means `shipment_fill_rate >= 1`; average fill rate alone can hide a
  meaningful number of partially filled shipments.
- Gross-margin rate is calculated from aggregate revenue and margin, not by
  averaging shipment-level percentages.
