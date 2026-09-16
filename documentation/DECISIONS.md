# Three decisions and dollar-impact scenarios

These calculations describe the full-size synthetic benchmark, not the smaller live demo. They are sensitivity examples for choosing pilots, not causal estimates, booked savings, or forecasts. All dollar impacts cover the entire benchmark period (dated shipments span January 2024–December 2025, with undated records in unfiltered totals); none is annualized.

| Pilot | Observed baseline | Assumption | Calculation | Scenario result |
|---|---|---|---|---:|
| Routing-guide improvement | 78,452 OTD-eligible shipments minus 59,986 on time = 18,466 late | Prevent 10% of late shipments; $25 net benefit per avoided failure after intervention cost | 18,466 × 10% × $25 | $46,165 |
| Full-fill exception prevention | 10,434 on-time but underfilled shipments, among resolved OTIF-eligible shipments | Prevent 10%; $25 net benefit per avoided exception after intervention cost | 10,434 × 10% × $25 | $26,085 |
| Pricing/accessorial recovery audit | $72,336,827.17 customer revenue | Additional recovery equals 1% of baseline billed revenue, with no incremental cost | $72,336,827.17 × 1% | $723,368.27 |

The 10%, $25, and 1% inputs are analyst-selected assumptions. The model does not measure the cost of a service failure, willingness to pay, contractual recoverability, or a causal effect of rerouting. At half the assumed improvement or recovery, each result halves. Do not add these estimates: rollout scope, overlapping interventions, and customer responses can change the benefits.

## How to act on the evidence

1. **Routing:** prioritize failure volume alongside cost, mode, and lane, rather than selecting the lowest rate alone. StoneBridge Freight has 72.7% OTD (2,554 / 3,511) and 957 late shipments; BlueArrow Logistics has 2,117 late shipments. Pilot matched carrier/lane changes and measure incremental carrier cost, claims, complaints, and OTD against a comparison group.
2. **Fulfillment:** on-time underfills account for 37.4% of known OTIF failures (10,434 / 27,877). Drill into warehouse, SKU/line coverage, and service before assigning cause. Measure full-fill and OTIF improvement plus the actual cost of exception handling.
3. **Commercial terms:** Harbor Home Goods Co has the lowest aggregate margin rate among active customers with at least 1,000 shipments (63.7%). Audit contracted prices, service mix, accessorial recovery, and paid claims before repricing. The benchmark's 66.8% network margin is an optimistic synthetic assumption, not evidence of realistic commercial economics.

Late shipments have a 6.0% complaint rate versus 2.5% on time; this is an association. Survey coverage is only 3.4%, so customer feedback is directional.

## Reproduce the evidence

Follow [the benchmark rebuild](REPRODUCING.md), then run:

```powershell
python documentation/verify_benchmark.py
```

This checks the headline reconciliation targets and prints executive totals and all three scenarios directly from the rebuilt mart. Generated `reports/business_insights.md` includes carrier, lane, customer, and coverage findings; [portfolio SQL](../sql/08_portfolio_analysis.sql) exposes segment analysis.
