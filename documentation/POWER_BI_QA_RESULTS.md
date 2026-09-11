# Power BI QA Results

Reviewed against the locally authored `powerbi/Logistics_Control_Tower.pbix` on
2026-09-09. The report was opened in Power BI Desktop after the Data Quality
measures and note were updated, then returned to the Executive Overview landing
page.

The recruiter-facing export contains five polished narrative pages. Shipment
Detail remains a hidden drillthrough page, and Data Quality remains a hidden
diagnostic page inside the PBIX.

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
- **KPI correction:** OTIF now divides OTIF shipments by OTIF-eligible shipments;
  the full-report card displays 62.4%.
- **Warehouse diagnostic:** the late-shipment decomposition tree is expanded by
  warehouse, replacing the previously empty-looking visual.

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

- `python -m unittest discover -s tests -v`: **59 tests passed**.
- `python -m ruff check .`: **passed**.
- `python python/10_export_powerbi_parquet.py`: **13 exports completed**.
- `python python/validate_pipeline.py`: **passed** with 98,595 fact shipments.
- PDF export: **5 recruiter-facing pages**, visually inspected after export.
- Repository evidence: four page screenshots plus one model-view screenshot are
  present under `images/`.

## Open finding: capture filter state

`images/Executive_Overview.png` shows Full-Fill Rate 81.3% and Gross Margin %
66.7%, while the tracked benchmark in `reports/executive_summary.csv` holds
0.813661 and 0.667930, which round to 81.4% and 66.8%. The same capture shows
the `Shipment Date` slicer ending before the reported last shipment date of
December 15, 2025, and its trend charts stop at 2025-11, so the cards were
evaluated in a narrowed filter context rather than over the full fact table.
On-Time Delivery % and OTIF % are unaffected at this precision, which is why the
gap is easy to miss.

The pipeline numbers are correct and unchanged; only the exported images carry
the narrowed context. The fix is to re-export the PNGs and the PDF under the
capture protocol now recorded in `powerbi/REPORT_BLUEPRINT.md`, which requires
Power BI Desktop. Until that re-export happens, the README states that
`reports/executive_summary.csv` is the authoritative reconciliation target.

Status: **open**, tracked, and disclosed rather than silently reconciled.

## Release decision

The project is portfolio-ready for a reviewer who can inspect the PDF,
screenshots, source model, and documented findings. It is not yet an
accessibility-complete release. Before presenting accessibility as a strength,
add descriptive alt text and verify tab order for all meaningful visuals, then
rerun the static scan and this manual checklist.
