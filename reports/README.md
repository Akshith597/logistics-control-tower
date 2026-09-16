# Generated reports

Generated CSVs and business findings are local outputs, not tracked portfolio
results. The legacy full-size benchmark used optimistic financial assumptions
and has been removed from the current Git tree. Existing local copies and Git
history are retained; no benchmark values were manually edited.

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
historical evidence, not a reconciliation target for the live app.
