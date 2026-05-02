-- =============================================================
-- BeerBeer warehouse schema (star schema)
--
-- One narrow fact, three conformed dimensions. Keep dim grain
-- explicit and immutable; if a beer is repackaged, mint a new
-- beer_id rather than mutating in place (Type-2 SCD lite).
-- =============================================================

CREATE SCHEMA IF NOT EXISTS warehouse;
SET search_path TO warehouse, public;

-- Dimensions ---------------------------------------------------

CREATE TABLE dim_date (
    date_key      DATE PRIMARY KEY,
    day_of_week   SMALLINT NOT NULL,        -- 0=Mon
    day_name      TEXT     NOT NULL,
    week_of_year  SMALLINT NOT NULL,
    month_num     SMALLINT NOT NULL,
    month_name    TEXT     NOT NULL,
    quarter       SMALLINT NOT NULL,
    year          SMALLINT NOT NULL,
    is_weekend    BOOLEAN  NOT NULL
);

CREATE TABLE dim_beer (
    beer_id        SERIAL PRIMARY KEY,
    sku            TEXT    NOT NULL UNIQUE,
    name           TEXT    NOT NULL,
    style          TEXT    NOT NULL,        -- IPA / Stout / Lager / Sour ...
    abv_pct        NUMERIC(4,2) NOT NULL,
    brewery        TEXT    NOT NULL,
    package_ml     INT     NOT NULL,        -- 330 / 500 / 750
    list_price_cny NUMERIC(8,2) NOT NULL,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE dim_store (
    store_id   SERIAL PRIMARY KEY,
    store_code TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    channel    TEXT NOT NULL,               -- on-premise / off-premise / online
    region     TEXT NOT NULL,               -- 华东 / 华南 / 华北 / 西南 / 海外
    city       TEXT NOT NULL,
    opened_on  DATE NOT NULL
);

-- Fact ---------------------------------------------------------
-- Grain: one row per (sale_date, beer_id, store_id). Aggregating
-- transactions to daily level keeps the warehouse small while
-- supporting every chart on the dashboard.

CREATE TABLE fact_sales (
    sale_date     DATE    NOT NULL REFERENCES dim_date(date_key),
    beer_id       INT     NOT NULL REFERENCES dim_beer(beer_id),
    store_id      INT     NOT NULL REFERENCES dim_store(store_id),
    units         INT     NOT NULL CHECK (units >= 0),
    gross_revenue NUMERIC(12,2) NOT NULL,
    discount      NUMERIC(12,2) NOT NULL DEFAULT 0,
    cogs          NUMERIC(12,2) NOT NULL,
    PRIMARY KEY (sale_date, beer_id, store_id)
);

CREATE INDEX idx_fact_sales_date    ON fact_sales(sale_date);
CREATE INDEX idx_fact_sales_beer    ON fact_sales(beer_id);
CREATE INDEX idx_fact_sales_store   ON fact_sales(store_id);
