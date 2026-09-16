Updated portfolio release: demo runs isolate their source workbook and reports under data/raw/demo/ and reports/demo/; Python 3.11–3.13 are supported in CI. The reviewed PBIX remains excluded from the source tree.

## Full-size benchmark reproduction

Logistical_Data.xlsx is the unchanged, full-size synthetic source workbook for rebuilding the benchmark analytical model. Download it alongside Logistics_Control_Tower.pbix and place it at data/raw/Logistical_Data.xlsx, then run `python python/run_pipeline.py`.

Workbook SHA256: `28f1058eebcd4fbfc8359e598e5a15211c916deb17b1578e32322cc8bbba1946` (86,163,870 bytes).

The benchmark headline is $72,336,827.17 revenue, 76.5% OTD (59,986 / 78,452), and 62.4% OTIF (46,321 / 74,198). Its 66.8% gross margin reflects optimistic synthetic financial assumptions. These values are distinct from the smaller deterministic demo and the live Streamlit snapshot. The existing logistics_dashboard_data.zip is a demo-scale convenience export, not the benchmark source.

[Reproduction, testing, and dashboard build instructions](https://github.com/Akshith597/logistics-control-tower/blob/main/documentation/REPRODUCING.md). The pipeline rebuilds analytical data; it does not generate the manually authored PBIX layout.
