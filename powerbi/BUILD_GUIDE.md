# Power BI Build Guide

This guide turns the files in `data/powerbi/` into a portfolio-ready Logistics Control Tower report. The semantic model is built from the shipment fact and six dimensions. The aggregate views are validation assets, not alternate facts.

## 1. Refresh the exported data

From the project root, run the pipeline through the Power BI export step:

```powershell
python python/run_pipeline.py --stop-after export
```

If the source workbook is unavailable, generate the deterministic demo data:

```powershell
python python/run_pipeline.py --generate-demo-data --stop-after export
```

Use `python python/10_export_powerbi_parquet.py` only when the DuckDB model has
already been refreshed. The export step validates every source-to-Parquet row
count before replacing the prior file. Confirm that all 13 files are present in
`data/powerbi/`.

## 2. Create the report

1. Open Power BI Desktop and create a blank report.
2. In Power Query, create the `pDataFolder` parameter and `fnLoadPowerBIParquet` function from [POWER_QUERY.md](POWER_QUERY.md).
3. Create the seven model queries and rename them exactly as shown below.
4. Create the six QA queries only after the core model refreshes successfully.
5. Set the QA queries to **Enable load = On**, hide them from Report view, and leave them disconnected. They are small reconciliation tables.

| Parquet file | Power BI query | Purpose |
|---|---|---|
| `fact_shipment.parquet` | `Fact Shipment` | Shipment-grain analytical fact |
| `dim_date.parquet` | `Dim Date` | Calendar and role-playing date dimension |
| `dim_customer.parquet` | `Dim Customer` | Customer attributes |
| `dim_carrier.parquet` | `Dim Carrier` | Carrier attributes |
| `dim_warehouse.parquet` | `Dim Warehouse` | Origin warehouse attributes |
| `dim_service.parquet` | `Dim Service` | Mode and service level |
| `dim_lane.parquet` | `Dim Lane` | Origin-to-destination lane |
| `vw_executive_kpis.parquet` | `QA Executive KPIs` | One-row KPI reconciliation |
| `vw_monthly_performance.parquet` | `QA Monthly Performance` | Monthly trend reconciliation |
| `vw_carrier_scorecard.parquet` | `QA Carrier Scorecard` | Carrier reconciliation |
| `vw_warehouse_scorecard.parquet` | `QA Warehouse Scorecard` | Warehouse reconciliation |
| `vw_customer_scorecard.parquet` | `QA Customer Scorecard` | Customer reconciliation |
| `vw_lane_scorecard.parquet` | `QA Lane Scorecard` | Lane reconciliation |

Do not relate a QA table to the model. Its metrics are already aggregated and cannot safely respond to arbitrary dimension filters.

## 3. Configure the semantic model

Build the relationships in [MODEL_SPEC.md](MODEL_SPEC.md). Use one-to-many cardinality and single-direction filtering from each dimension to `Fact Shipment`.

Then apply these model settings:

- Mark `Dim Date` as the date table using `date_key`.
- Sort `month_name` by `month_number` and `day_name` by `day_of_week_number`.
- Add the calculated columns in [CALCULATED_COLUMNS.dax](CALCULATED_COLUMNS.dax), then sort `year_month` by `year_month_sort`.
- Hide technical keys, raw foreign keys, and columns replaced by measures.
- Set key and ID columns to **Do not summarize**.
- Format currency as `$#,##0`; whole-number counts as `#,##0`; rates as `0.0%`; hours and days as `0.0`; NPS as `0.0`.
- Set default summarization to **None** for numeric attributes such as ZIP codes, latitude, longitude, planned transit days, and capacity.
- Create the `_Measures` and `KPI Targets` tables from [CALCULATED_TABLES.dax](CALCULATED_TABLES.dax). Hide `_Measures[Placeholder]`.
- Create the measures in [MEASURES.dax](MEASURES.dax) on the `_Measures` table and organize them into display folders matching the section names in that file.

The target values supplied in `KPI Targets` are portfolio demonstration assumptions. Replace them with approved business targets before presenting the report as an operational scorecard.

## 4. Apply presentation assets

1. Import [logistics-control-tower-theme.json](logistics-control-tower-theme.json) from **View > Themes > Browse for themes**.
2. Build the pages and interactions in [REPORT_BLUEPRINT.md](REPORT_BLUEPRINT.md).
3. Use a 16:9 canvas, consistent page navigation, and a maximum of six primary visuals per page.
4. Add a “Data through” subtitle using the `Data Through Date` measure. It reads the latest `Fact Shipment[ship_date]` and intentionally ignores only `Dim Date` filters, so a date slicer cannot make the dataset appear older than it is.
5. Add descriptive alt text to every non-decorative visual and do not use color as the only status signal.

## 5. Validate before publishing

Follow [POWER_BI_VALIDATION.md](../documentation/POWER_BI_VALIDATION.md). At minimum:

- reconcile the executive measures to `QA Executive KPIs` with no page filters;
- verify one carrier, warehouse, customer, lane, and month against its QA table;
- verify that filters from every dimension reduce `Total Shipments` as expected;
- verify that selecting a shipment date does not unintentionally constrain promised- or actual-date measures;
- run Performance Analyzer and remove avoidable high-cardinality fields from visuals.

## 6. Save the portfolio artifact

Save the authored report as `powerbi/Logistics_Control_Tower.pbix`. Export a PDF and capture at least the Executive Overview, Carrier & Lane, Profitability, and Data Quality pages into `images/` for a repository reviewer who does not have Power BI Desktop.

The repository currently supplies the complete build specification but a `.pbix` must still be authored and visually reviewed in Power BI Desktop.
