-- =============================================================
-- Seed data: 120 days of synthetic sales across 12 SKUs and 8
-- stores. Generated deterministically so the dashboard looks the
-- same on every fresh deploy (helpful for demos and screenshots).
-- =============================================================

SET search_path TO warehouse, public;

-- dim_date: rolling 180 days ending today --------------------
INSERT INTO dim_date
SELECT  d::DATE,
        EXTRACT(ISODOW FROM d)::INT - 1,
        TO_CHAR(d, 'Dy'),
        EXTRACT(WEEK FROM d)::INT,
        EXTRACT(MONTH FROM d)::INT,
        TO_CHAR(d, 'Mon'),
        EXTRACT(QUARTER FROM d)::INT,
        EXTRACT(YEAR FROM d)::INT,
        EXTRACT(ISODOW FROM d) IN (6,7)
FROM    generate_series(CURRENT_DATE - INTERVAL '179 days',
                        CURRENT_DATE,
                        INTERVAL '1 day') d;

-- dim_beer ---------------------------------------------------
INSERT INTO dim_beer (sku, name, style, abv_pct, brewery, package_ml, list_price_cny) VALUES
  ('BB-IPA-330',  'Hop Highway IPA',     'IPA',          6.5, 'BeerBeer',     330, 28.00),
  ('BB-IPA-500',  'Hop Highway IPA',     'IPA',          6.5, 'BeerBeer',     500, 38.00),
  ('BB-NEI-330',  'Cloud Surfer NEIPA',  'NEIPA',        6.8, 'BeerBeer',     330, 32.00),
  ('BB-STO-330',  'Midnight Oats Stout', 'Stout',        7.2, 'BeerBeer',     330, 30.00),
  ('BB-STO-750',  'Midnight Oats Stout', 'Stout',        7.2, 'BeerBeer',     750, 68.00),
  ('BB-LAG-330',  'Pearl Lager',         'Lager',        4.8, 'BeerBeer',     330, 18.00),
  ('BB-LAG-500',  'Pearl Lager',         'Lager',        4.8, 'BeerBeer',     500, 24.00),
  ('BB-PIL-330',  'Tsing Pilsner',       'Pilsner',      5.0, 'BeerBeer',     330, 20.00),
  ('BB-SOU-330',  'Plum Sour',           'Sour',         4.5, 'BeerBeer',     330, 34.00),
  ('BB-WIT-330',  'Garden Witbier',      'Witbier',      5.2, 'BeerBeer',     330, 26.00),
  ('BB-SAI-750',  'Farmhouse Saison',    'Saison',       6.0, 'BeerBeer',     750, 72.00),
  ('BB-PAL-330',  'Daydream Pale Ale',   'Pale Ale',     5.5, 'BeerBeer',     330, 24.00);

-- dim_store --------------------------------------------------
INSERT INTO dim_store (store_code, name, channel, region, city, opened_on) VALUES
  ('SH-TAP-01', 'BeerBeer Taproom 静安',   'on-premise',  '华东', '上海', '2022-03-01'),
  ('SH-RET-02', '盒马鲜生 浦东金桥',        'off-premise', '华东', '上海', '2021-06-15'),
  ('BJ-TAP-01', 'BeerBeer Taproom 三里屯', 'on-premise',  '华北', '北京', '2022-09-10'),
  ('BJ-RET-02', '永辉超市 朝阳大悦城',      'off-premise', '华北', '北京', '2020-11-20'),
  ('GZ-RET-01', '山姆会员店 番禺',          'off-premise', '华南', '广州', '2021-04-05'),
  ('SZ-TAP-01', 'BeerBeer Taproom 南山',   'on-premise',  '华南', '深圳', '2023-02-18'),
  ('CD-RET-01', '伊藤洋华堂 春熙路',        'off-premise', '西南', '成都', '2021-12-01'),
  ('ON-DTC-01', 'BeerBeer 天猫旗舰店',      'online',      '海外', '杭州', '2020-05-10');

-- fact_sales: cross-join days × beers × stores, then perturb --
-- Volume model:
--   base = popularity(beer) * traffic(store)
--   weekday boost on Fri/Sat/Sun
--   gentle upward trend over the window (growth)
--   per-row jitter
INSERT INTO fact_sales (sale_date, beer_id, store_id, units, gross_revenue, discount, cogs)
SELECT
    d.date_key,
    b.beer_id,
    s.store_id,
    units,
    ROUND(units * b.list_price_cny, 2)              AS gross_revenue,
    ROUND(units * b.list_price_cny * disc_rate, 2)  AS discount,
    ROUND(units * b.list_price_cny * 0.42, 2)       AS cogs
FROM dim_date d
CROSS JOIN dim_beer b
CROSS JOIN dim_store s
CROSS JOIN LATERAL (
    SELECT
        GREATEST(0, ROUND(
            -- popularity by style (IPA / Lager sell more)
            CASE b.style WHEN 'IPA' THEN 14 WHEN 'NEIPA' THEN 11
                         WHEN 'Lager' THEN 16 WHEN 'Pilsner' THEN 12
                         WHEN 'Pale Ale' THEN 10 WHEN 'Stout' THEN 7
                         WHEN 'Witbier' THEN 8 WHEN 'Sour' THEN 6
                         ELSE 5 END
            -- channel multiplier
          * CASE s.channel WHEN 'off-premise' THEN 1.6
                           WHEN 'online' THEN 2.2
                           ELSE 1.0 END
            -- weekend boost on-premise
          * CASE WHEN d.is_weekend AND s.channel = 'on-premise' THEN 1.8 ELSE 1.0 END
            -- linear growth (0% at start → ~25% at end)
          * (1.0 + 0.0014 * (d.date_key - (CURRENT_DATE - 179)))
            -- jitter ±25%
          * (0.75 + (random() * 0.5))
        ))::INT AS units,
        -- 0–15% discount, off-premise & online run more promos
        CASE WHEN random() < 0.25
             THEN ROUND((random() * 0.15)::NUMERIC, 3)
             ELSE 0 END                              AS disc_rate
) calc
WHERE units > 0;

-- Sanity check ------------------------------------------------
ANALYZE;
