# Report provenance

The tracked files in this directory are the full-size benchmark outputs used
by the headline findings in the root README. They were generated from the
ignored source workbook `data/raw/Logistical_Data.xlsx`, which is intentionally
not committed because it is a large local artifact.

Reviewers without that workbook can still run the complete pipeline:

```powershell
python python/run_pipeline.py --generate-demo-data
```

The demo command creates its source workbook under `data/raw/demo/` and writes
all generated report files under `reports/demo/`. Those paths are ignored by
Git, so a demo run cannot overwrite the tracked full-size benchmark reports.
The default demo fixture contains 7,200 source shipments and produces
demo-scale KPI values; it is a pipeline and data-contract fixture, not a
reproduction of the full-size benchmark numbers.

To reproduce the exact headline numbers, obtain the reviewed full-size source
workbook or use the PBIX attached to the public release. The source workbook
is synthetic and contains no production or personal data.
