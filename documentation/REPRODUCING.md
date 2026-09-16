# Reproduce, test, and build

Run commands from the repository root using Python 3.11–3.13. Power BI Desktop is required only to author or refresh the PBIX.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS/Linux, activate with `source .venv/bin/activate`.

## Full-size synthetic benchmark

Download [Logistical_Data.xlsx](https://github.com/Akshith597/logistics-control-tower/releases/download/v1.1.0/Logistical_Data.xlsx) from the same release as the [reviewed PBIX](https://github.com/Akshith597/logistics-control-tower/releases/download/v1.1.0/Logistics_Control_Tower.pbix). Place the unchanged workbook at `data/raw/Logistical_Data.xlsx`. It stays gitignored to keep the source tree small. The workbook contains synthetic data only.

Verify the download in PowerShell:

```powershell
Get-FileHash data/raw/Logistical_Data.xlsx -Algorithm SHA256
```

Expected SHA256: `28f1058eebcd4fbfc8359e598e5a15211c916deb17b1578e32322cc8bbba1946` (86,163,870 bytes).

```powershell
python python/run_pipeline.py
python documentation/verify_benchmark.py
```

The pipeline extracts all 12 sheets, profiles and stages the data, builds the shipment-grain mart, exports 13 Parquet files, validates, and generates findings. Allow several minutes for the full workbook. Inspect `reports/executive_summary.csv` and `reports/business_insights.md`.

| Reconciliation target | Expected benchmark value |
|---|---:|
| Final live, non-test shipments | 98,595 |
| Customer revenue | $72,336,827.17 |
| OTD | 59,986 / 78,452 = 76.5% |
| OTIF | 46,321 / 74,198 = 62.4% |
| Gross margin | $48,315,921.99 / 66.8% |

These are unfiltered model totals. Screenshot cards can differ with date filters and unresolved dates. Benchmark margin assumptions are optimistic; this is not a real company's financial performance. The PBIX is manually authored, so the Python pipeline reproduces its analytical data rather than generating its report layout.

Verified on 2026-09-16: all 12 pipeline steps completed from the release workbook,
all 89 pipeline validation checks passed, and `verify_benchmark.py` reconciled
the targets above. The uploaded workbook's GitHub SHA256 matches the local source.

## Deterministic demo and Streamlit

```powershell
python python/run_pipeline.py --generate-demo-data
streamlit run streamlit_app.py
```

The demo generates 7,200 source shipments and yields 6,968 final live, non-test shipments: $7,851,265.84 revenue, 71.4% OTD, 65.9% OTIF, and 20.0% gross margin. Source data and reports are isolated under `data/raw/demo/` and `reports/demo/`; the benchmark source and reports are preserved. **Both modes replace the shared local warehouse and `data/powerbi/` exports.** Rebuild the benchmark before refreshing its PBIX or running benchmark verification.

The hosted app uses the tracked `data/public_dashboard/` demo snapshot. The local app reads that same snapshot; pipeline exports do not automatically replace it. Use `--force-demo-data` with `--generate-demo-data` only to regenerate the isolated fixture.

## Tests and quality checks

```powershell
python -m unittest discover -s tests -v
python python/validate_pipeline.py
python -m pip install -r requirements-dev.txt
python -m ruff check .
```

[CI](../.github/workflows/portfolio-quality.yml) runs lint, tests, deterministic rebuilds, and critical SQL checks on Python 3.11–3.13. [Validation SQL](../sql/07_validate_model.sql) checks grain, relationships, and reconciliation. Generated outputs remain ignored; [report provenance](../reports/README.md) explains their locations.

## Architecture and dashboard build

Child records (lines, events, invoices, WMS, claims, support, surveys) are aggregated before joining the shipment fact. Explicit eligible denominators and visible data-quality gaps keep rates inspectable.

- [Python pipeline](../python/run_pipeline.py) and [SQL transformations](../sql/)
- [Power BI build guide](../powerbi/BUILD_GUIDE.md), [Power Query setup](../powerbi/POWER_QUERY.md), and [semantic model](../powerbi/MODEL_SPEC.md)
- [Report blueprint](../powerbi/REPORT_BLUEPRINT.md), [validation protocol](POWER_BI_VALIDATION.md), and [reviewed QA results](POWER_BI_QA_RESULTS.md)
- [Carrier/lane](../images/Carrier_Lane_Performance.png), [profitability](../images/Profitability.png), [data quality](../images/Data_Quality_Coverage.png), and [PDF preview](../images/Logistics_Control_Tower.pdf)
- [Production roadmap](PRODUCTION_ROADMAP.md) for CDC, orchestration, observability, and lineage
