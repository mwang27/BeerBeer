"""
Superset config overrides for the BeerBeer reference deployment.

Mounted into the container at /app/pythonpath/superset_config.py.
Keep this file minimal — only knobs that meaningfully affect
dashboard behaviour or security belong here.
"""
import os

# --- Secrets --------------------------------------------------
# In real deployments, source from secrets manager.
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

# --- Metadata DB ----------------------------------------------
SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]

# --- Caching --------------------------------------------------
# Two layers: chart-level (CACHE_CONFIG) and per-dataset
# (set on the dataset itself). Both back onto Redis.
REDIS_URL = f"redis://{os.environ.get('REDIS_HOST', 'redis')}:6379"

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 60 * 10,           # 10 min
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_URL": f"{REDIS_URL}/1",
}
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 60 * 60 * 4,       # 4 h
    "CACHE_KEY_PREFIX": "superset_results_",
    "CACHE_REDIS_URL": f"{REDIS_URL}/2",
}
FILTER_STATE_CACHE_CONFIG = {**CACHE_CONFIG, "CACHE_KEY_PREFIX": "superset_filter_"}
EXPLORE_FORM_DATA_CACHE_CONFIG = {**CACHE_CONFIG, "CACHE_KEY_PREFIX": "superset_form_"}

# --- Feature flags --------------------------------------------
FEATURE_FLAGS = {
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
    "DASHBOARD_RBAC": True,
    "ALERT_REPORTS": True,
    "EMBEDDED_SUPERSET": True,
    "ENABLE_TEMPLATE_PROCESSING": True,        # Jinja in SQL
    "GLOBAL_ASYNC_QUERIES": False,             # set True with celery
    "ROW_LEVEL_SECURITY": True,
}

# --- Branding -------------------------------------------------
APP_NAME = "BeerBeer Analytics"
APP_ICON = "/static/assets/images/superset-logo-horiz.png"

# Pin a single brand palette so every chart looks consistent.
EXTRA_CATEGORICAL_COLOR_SCHEMES = [
    {
        "id": "beerbeerBrand",
        "description": "BeerBeer house palette",
        "label": "BeerBeer",
        "isDefault": True,
        "colors": [
            "#F2A900",  # amber
            "#5C3A21",  # malt
            "#C73E1D",  # red ale
            "#1B998B",  # hop green
            "#2E294E",  # midnight stout
            "#E0CA3C",  # straw lager
            "#7B2D26",
            "#A0C1B9",
        ],
    }
]

# --- Time-zone & locale ---------------------------------------
DEFAULT_FEATURE_FLAGS = {"BABEL_DEFAULT_LOCALE": "zh"}
BABEL_DEFAULT_LOCALE = "zh"
DRUID_TZ = "Asia/Shanghai"

# --- Sample row-level security policy -------------------------
# Demonstrates how to scope a "regional manager" role to its
# own region. Created here as a template; activate via the UI
# or `superset import-rls`.
#
#   RLS rule:
#     filter_type: regular
#     tables:      [v_sales, v_kpi_daily]
#     roles:       [RegionalManager_HuaDong]
#     clause:      region = '华东'
