# Generated reports

Generated CSVs and business findings are local outputs, not tracked portfolio
results. The full-size benchmark uses optimistic financial assumptions;
its generated outputs remain outside the current Git tree. Reviewers can now
download its synthetic source workbook alongside the PBIX and rebuild the
findings using [the reproduction guide](../documentation/REPRODUCING.md).

Reviewers can generate the demo reports by running the complete pipeline:

```powershell
python python/run_pipeline.py --generate-demo-data
```

The demo command creates its source workbook under `data/raw/demo/` and writes
all generated report files under `reports/demo/`. Those paths are ignored by
Git, so a demo run cannot overwrite local full-size benchmark reports.
The default demo fixture contains 7,200 source shipments and produces
demo-scale KPI values; it is a pipeline and data-contract fixture, not a
reproduction of the full-size benchmark numbers.

Inspect `reports/demo/executive_summary.csv` and `reports/demo/business_insights.md`
after the run. The live app reads the tracked `data/public_dashboard/` snapshot;
the README scorecard describes that demo. The older downloadable PBIX is separate
benchmark evidence, not a reconciliation target for the live app.
