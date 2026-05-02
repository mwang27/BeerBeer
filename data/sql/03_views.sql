-- =============================================================
-- Semantic layer
--
-- Best practice: define business logic ONCE, in a view that
-- Superset binds to as a "physical" dataset. The dashboard then
-- consumes pre-joined, pre-named columns. Charts stay simple
-- (no SQL Lab queries scattered around), and a metric change
-- only requires editing one view.
-- =============================================================

SET search_path TO warehouse, public;

-- Wide sales view: every fact row joined to its dimensions ----
CREATE OR REPLACE VIEW v_sales AS
SELECT
    f.sale_date,
    d.day_of_week,
    d.day_name,
    d.is_weekend,
    d.week_of_year,
    d.month_num,
    d.month_name,
    d.quarter,
    d.year,
    b.beer_id,
    b.sku,
    b.name           AS beer_name,
    b.style,
    b.abv_pct,
    b.package_ml,
    s.store_id,
    s.store_code,
    s.name           AS store_name,
    s.channel,
    s.region,
    s.city,
    f.units,
    f.gross_revenue,
    f.discount,
    f.gross_revenue - f.discount               AS net_revenue,
    f.cogs,
    f.gross_revenue - f.discount - f.cogs      AS gross_profit
FROM fact_sales f
JOIN dim_date  d ON d.date_key = f.sale_date
JOIN dim_beer  b ON b.beer_id  = f.beer_id
JOIN dim_store s ON s.store_id = f.store_id;

COMMENT ON VIEW v_sales IS
  'One row per (date, sku, store). Bind this in Superset as the primary dataset.';

-- Pre-aggregated daily KPIs (cheap for trend lines) -----------
CREATE OR REPLACE VIEW v_kpi_daily AS
SELECT
    sale_date,
    SUM(net_revenue)                     AS net_revenue,
    SUM(units)                           AS units,
    SUM(gross_profit)                    AS gross_profit,
    SUM(gross_profit) / NULLIF(SUM(net_revenue), 0) AS gross_margin_pct,
    SUM(net_revenue) / NULLIF(SUM(units), 0)        AS avg_unit_price
FROM v_sales
GROUP BY sale_date;

COMMENT ON VIEW v_kpi_daily IS
  'Daily KPI rollup. Use for trend charts and big-number comparisons.';
