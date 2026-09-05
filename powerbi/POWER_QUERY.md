# Power Query Loader

Create the parameter, function, and queries below in Power Query. The query names must match the semantic model specification because the supplied DAX uses those names.

## Parameter: `pDataFolder`

Create a new text parameter named `pDataFolder` and set its current value to the absolute path of this repository's `data\powerbi` folder. The generated M should resemble:

```powerquery
"C:\path\to\logistics-control-tower\data\powerbi" meta
[
    IsParameterQuery = true,
    Type = "Text",
    IsParameterQueryRequired = true
]
```

Keeping the path in one parameter makes the PBIX portable between reviewers and machines.

## Function: `fnLoadPowerBIParquet`

Create a blank query, open Advanced Editor, paste this code, and name the query `fnLoadPowerBIParquet`:

```powerquery
(fileName as text) as table =>
let
    CleanRoot = Text.TrimEnd(pDataFolder, {"\", "/"}),
    FullPath = CleanRoot & "\" & fileName,
    Source = Parquet.Document(File.Contents(FullPath))
in
    Source
```

Disable load for the parameter and function.

## Model queries

Create one blank query for each entry, paste the expression, and use the exact query name.

| Query name | M expression |
|---|---|
| `Fact Shipment` | `= fnLoadPowerBIParquet("fact_shipment.parquet")` |
| `Dim Date` | `= fnLoadPowerBIParquet("dim_date.parquet")` |
| `Dim Customer` | `= fnLoadPowerBIParquet("dim_customer.parquet")` |
| `Dim Carrier` | `= fnLoadPowerBIParquet("dim_carrier.parquet")` |
| `Dim Warehouse` | `= fnLoadPowerBIParquet("dim_warehouse.parquet")` |
| `Dim Service` | `= fnLoadPowerBIParquet("dim_service.parquet")` |
| `Dim Lane` | `= fnLoadPowerBIParquet("dim_lane.parquet")` |

## QA queries

These queries are disconnected reconciliation assets. Load and hide them while developing; they can be disabled before a production publish after validation is complete.

| Query name | M expression |
|---|---|
| `QA Executive KPIs` | `= fnLoadPowerBIParquet("vw_executive_kpis.parquet")` |
| `QA Monthly Performance` | `= fnLoadPowerBIParquet("vw_monthly_performance.parquet")` |
| `QA Carrier Scorecard` | `= fnLoadPowerBIParquet("vw_carrier_scorecard.parquet")` |
| `QA Warehouse Scorecard` | `= fnLoadPowerBIParquet("vw_warehouse_scorecard.parquet")` |
| `QA Customer Scorecard` | `= fnLoadPowerBIParquet("vw_customer_scorecard.parquet")` |
| `QA Lane Scorecard` | `= fnLoadPowerBIParquet("vw_lane_scorecard.parquet")` |

## Refresh checks

After **Close & Apply**:

1. Verify every model query has rows and no conversion errors.
2. Verify all key columns are Text except `Dim Date[date_key]` and fact date keys, which must be Date.
3. Verify every flag column is True/False.
4. Verify rates are Decimal number and display as percentages only in the model; do not multiply the stored values by 100.
5. Verify postal codes and identifiers remain Text.
