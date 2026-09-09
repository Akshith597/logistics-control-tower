# Power BI QA Results

Reviewed against the locally authored `powerbi/Logistics_Control_Tower.pbix` on
2026-09-09. The report was opened in Power BI Desktop after the Data Quality
measures and note were updated, then returned to the Executive Overview landing
page.

## Manual interaction

- **Executive Overview cross-filter:** selecting a monthly bar changed the KPI
  cards from the full-report view (about 95K shipments) to the selected month
  (about 3K shipments); selecting the same bar again restored the full-report
  totals.
- **Page navigation:** Executive Overview and Carrier & Lane Performance both
  opened successfully, with the expected page titles, KPI cards, date range,
  transportation-mode control, and carrier service/cost visual visible.
- **Model view:** the star-schema model was opened and captured. The screenshot
  shows the shipment fact, six dimensions, measure tables, and relationships.
- **Reset state:** the report was left with no temporary month selection and
  Executive Overview active.

## Performance Analyzer

Power BI Performance Analyzer recorded a full visual refresh on Executive
Overview. The visible visual durations were:

| Visual group | Duration observed |
| --- | ---: |
| Transportation Mode | 137 ms |
| Top Carriers by Late Shipments | 314 ms |
| Monthly Shipment and Service Performance | 318 ms |
| Shipment Date | 353 ms |
| Monthly Gross Margin Performance | 349 ms |
| KPI cards | 390–536 ms |

No visible visual exceeded 2 seconds and no unexplained outlier appeared in the
recorded list. This is an observed Desktop refresh sample, not a substitute for
service-side performance monitoring after publication.

## Accessibility review

The report was visually reviewed for readable titles, labels, page-level
structure, and the Data Quality disclosure note. A static scan of the saved PBIX
definition found 97 visuals and explicit `altText` properties on only 4 of them.
That is a material accessibility gap: the report should not be described as
WCAG-complete or accessibility-complete until meaningful alt text and a logical
keyboard/tab order are added to the remaining visuals.

## Automated evidence

- `python -m unittest discover -s tests -v`: **57 tests passed**.
- `python -m ruff check .`: **passed**.
- `python python/10_export_powerbi_parquet.py`: **13 exports completed**.
- `python python/validate_pipeline.py`: **passed** with 98,595 fact shipments.
- PDF export: **7 pages**, visually readable in the repository preview.
- Repository evidence: four page screenshots plus one model-view screenshot are
  present under `images/`.

## Release decision

The project is portfolio-ready for a reviewer who can inspect the PDF,
screenshots, source model, and documented findings. It is not yet an
accessibility-complete release. Before presenting accessibility as a strength,
add descriptive alt text and verify tab order for all meaningful visuals, then
rerun the static scan and this manual checklist.
