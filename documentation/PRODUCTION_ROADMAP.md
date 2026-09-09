# Productionization roadmap

The repository is intentionally a local, full-refresh portfolio case study.
That scope makes the joins, KPI definitions, validation SQL, and Power BI
handoff inspectable from a clean checkout. The next production increments are
explicit rather than implied:

## Current foundation

- Ordered pipeline steps with `--start-at` and `--stop-after` controls.
- Transaction-wrapped DuckDB transformations and source-lineage fingerprints.
- Deterministic demo data, stable output contracts, SQL validation, and CI
  rebuilds across Python 3.11, 3.12, and 3.13.
- Shipment-grain star schema with aggregate-before-join protections and
  business-facing KPI denominators.

## Production increments

1. **Orchestration and scheduling:** package the step graph as a Dagster,
   Prefect, or Airflow job with retries, dependency-aware scheduling, run
   metadata, alerting, and backfills. The current numbered runner is the clear
   development-mode equivalent of that graph.
2. **Incremental and CDC ingestion:** land source snapshots or change events in
   object storage, track source watermarks and batch IDs, and `MERGE` changed
   shipment/customer/financial records into partitioned warehouse tables. Keep
   late-arriving events and corrections idempotent.
3. **dbt semantic layer:** move the staging, mart, and KPI SQL into dbt models
   with explicit `ref()` lineage, source freshness checks, schema tests, model
   documentation, and generated lineage artifacts. Preserve the current SQL
   validation queries as decision-level tests.
4. **Warehouse and serving layer:** replace local DuckDB files with a managed
   warehouse plus object storage for raw and curated data; publish a certified
   Power BI dataset through a deployment pipeline with environment-specific
   parameters and refresh monitoring.
5. **Observability and governance:** add run-level metrics, row-count and
   freshness SLAs, data-quality incident routing, PII classification, RBAC,
   audit logs, and a documented retention policy.

This roadmap is intentionally specific about what is not claimed by the local
portfolio build: it demonstrates the data-modeling and validation foundation,
not a production scheduler, CDC service, or deployed warehouse.
