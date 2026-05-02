BeerBeer Superset Dashboard — Reference Implementation
=======================================================

A production-shaped reference for building an Apache Superset dashboard
**as code**: star-schema warehouse, semantic views, declarative dashboard
spec, and an idempotent build script that materialises everything through
Superset's REST API.

业务场景:精酿啤酒销售总览(销售额、毛利、Top SKU、区域 × 渠道、
风格分布、星期热力)。

```
BeerBeer/
├── data/
│   ├── init.sh                  Postgres entrypoint hook
│   └── sql/
│       ├── 01_schema.sql        Star schema DDL
│       ├── 02_seed.sql          120 days of synthetic sales
│       └── 03_views.sql         Semantic layer (v_sales, v_kpi_daily)
├── superset_config/
│   └── superset_config.py       Caching, RLS, brand palette
├── dashboard/
│   ├── spec.yaml                Declarative dashboard spec  ← edit this
│   ├── build.py                 Materialise spec via Superset API
│   └── requirements.txt
├── docker-compose.yml           Postgres + Redis + Superset
├── Makefile                     One-command operations
└── .env.example
```

## Quick start

```bash
cp .env.example .env
make up                 # starts containers, seeds warehouse, waits for /health
make build-dashboard    # creates DB, datasets, charts, dashboard via API
open http://localhost:8088/superset/dashboard/beer-sales-overview/
```

Default login is `admin / admin` (change in `.env`).

## Design principles

The choices in this repo encode opinions worth carrying into other
Superset projects:

### 1. Star schema, narrow fact

`fact_sales` has one row per (date, sku, store) — pre-aggregated to daily
grain. Three dimensions (`dim_date`, `dim_beer`, `dim_store`) hang off it.
Wide flattened tables are tempting but make slowly-changing attributes
(price, brewery, store region) painful. Keep the fact narrow; let
dimensions absorb the changes.

### 2. Semantic layer in views, not chart SQL

Every chart binds to `v_sales` or `v_kpi_daily`, never to raw `fact_sales`.
Business definitions like "net revenue = gross − discount" live in the
view. Change them once, every chart updates. SQL Lab queries scattered
inside chart definitions are a maintenance trap — avoid.

### 3. Metrics defined on datasets, not charts

`net_revenue`, `units_sold`, `gross_margin_pct`, `avg_unit_price` are
declared as dataset metrics in `spec.yaml`. Charts reference them by
name. A formula change propagates automatically; a new chart picks the
same definition for free. This is your dashboard's contract — treat
metric renames like API breaking changes.

### 4. Layout follows the eye

Reading order is **F-pattern**: KPIs at the top, trend below, breakdowns
at the bottom. The user's first glance answers "are we up or down?"
before they ever scroll.

```
┌────────────────────────────────────────────────────────────────┐
│  净收入 │ 件数 │ 毛利率 │ 客单价         (period-over-period)   │
├────────────────────────────────────────────────────────────────┤
│  净收入与 7 日均线 (90 天)                                      │
├──────────────────────────────┬─────────────────────────────────┤
│  Top 10 SKU                  │  风格销售占比 (donut)            │
├──────────────────────────────┼─────────────────────────────────┤
│  区域 × 渠道 透视             │  星期 × 周次 热力               │
└──────────────────────────────┴─────────────────────────────────┘
```

### 5. Native filters for high-cardinality, cross-filters for the rest

Date range, region, channel, style → native filters at the dashboard
top. Clicking a slice on the donut already filters the rest of the
charts via cross-filters; don't duplicate that as a native filter.

### 6. One brand palette

`EXTRA_CATEGORICAL_COLOR_SCHEMES` registers `beerbeerBrand` and the
dashboard pins it. Every chart looks like part of one product. Avoid
per-chart custom colors — they drift over time and become unmaintainable.

### 7. Caching has two layers

- **Per-dataset** (`cache_timeout` on the dataset): how stale a chart
  result can be before re-querying. 30 min works for daily-grain data.
- **Per-database** (`cache_timeout` on the connection): catches anything
  unset on the dataset. 10 min default.

Redis backs both. Without caching, the same dashboard re-renders the
same SQL on every page load — punishing for the warehouse.

### 8. RLS templates live in code

`superset_config.py` documents an example regional-manager rule.
Manage these through `superset import-rls` so role boundaries are
reviewable in PRs, not buried in the UI.

### 9. Dashboard as code

`build.py` is idempotent: it matches by name/slug and updates in place.
Re-run it on every CI build. The spec is the source of truth — anyone
editing in the UI knows their changes will be overwritten unless they
also edit `spec.yaml`.

### 10. Synthetic but believable seed data

`02_seed.sql` generates ~150k rows with realistic shape: weekend
boost on-premise, channel mix, gradual growth, jitter. Demos look
honest, screenshots stay stable across deploys.

## Adding a chart

1. Add a `metric` to `v_sales` in `spec.yaml` if needed.
2. Append a new entry under `charts:`.
3. Slot it into `dashboard.layout`.
4. `make build-dashboard`.

## Promoting to staging / prod

The same `spec.yaml` runs against any Superset by switching env vars:

```bash
SUPERSET_URL=https://superset.staging.beerbeer.io \
SUPERSET_USERNAME=ci_bot \
SUPERSET_PASSWORD=$STAGING_BOT_PASSWORD \
WAREHOUSE_URL=$STAGING_WAREHOUSE_URL \
python3 dashboard/build.py
```

Wire that into CI behind branch protection on `dashboard/spec.yaml` and
your dashboard is reviewable, reproducible, and recoverable.

## What this example deliberately omits

- **Celery worker / async queries** — single-node sync queries are fine
  up to a few thousand rows per chart. Add `superset-worker` and flip
  `GLOBAL_ASYNC_QUERIES` once you outgrow that.
- **Alerts & reports** — feature flag is on; configure SMTP and a
  Chrome driver container when you actually need scheduled emails.
- **Embedded SDK** — flag is on. Generate a guest token from `build.py`
  if you need to embed the dashboard in another app.
- **dbt** — for a real warehouse, replace `03_views.sql` with a dbt
  project. The Superset side of the contract (dataset names + metric
  expressions) doesn't change.
