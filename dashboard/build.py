#!/usr/bin/env python3
"""
Materialise dashboard/spec.yaml against a running Superset.

Idempotent: re-running with the same spec updates existing
objects in place (matched by name) instead of creating
duplicates. Run it from CI on every merge to main, or locally
via `make build-dashboard`.

Required env:
  SUPERSET_URL        e.g. http://localhost:8088
  SUPERSET_USERNAME   admin user
  SUPERSET_PASSWORD
  WAREHOUSE_URL       SQLAlchemy URI, e.g.
                      postgresql+psycopg2://superset:superset@postgres:5432/beerbeer
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
import yaml

SPEC_FILE = Path(__file__).parent / "spec.yaml"


# --- HTTP client ---------------------------------------------

class Superset:
    def __init__(self, base_url: str, username: str, password: str):
        self.base = base_url.rstrip("/")
        self.s = requests.Session()
        self._login(username, password)

    def _login(self, username: str, password: str) -> None:
        r = self.s.post(
            f"{self.base}/api/v1/security/login",
            json={"username": username, "password": password,
                  "provider": "db", "refresh": True},
            timeout=15,
        )
        r.raise_for_status()
        self.s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        # CSRF token required for write endpoints
        r = self.s.get(f"{self.base}/api/v1/security/csrf_token/", timeout=15)
        r.raise_for_status()
        self.s.headers["X-CSRFToken"] = r.json()["result"]
        self.s.headers["Referer"] = self.base

    # CRUD helpers ------------------------------------------------

    def find(self, resource: str, filter_col: str, value: str) -> dict | None:
        q = json.dumps({"filters": [{"col": filter_col, "opr": "eq", "value": value}]})
        r = self.s.get(f"{self.base}/api/v1/{resource}/?q={q}", timeout=15)
        r.raise_for_status()
        items = r.json().get("result", [])
        return items[0] if items else None

    def upsert(self, resource: str, key_col: str, key_val: str,
               payload: dict[str, Any]) -> int:
        existing = self.find(resource, key_col, key_val)
        if existing:
            rid = existing["id"]
            r = self.s.put(f"{self.base}/api/v1/{resource}/{rid}",
                           json=payload, timeout=30)
        else:
            r = self.s.post(f"{self.base}/api/v1/{resource}/",
                            json=payload, timeout=30)
        r.raise_for_status()
        return existing["id"] if existing else r.json()["id"]


# --- Builders -------------------------------------------------

def build_database(api: Superset, spec: dict, warehouse_url: str) -> int:
    db = spec["database"]
    return api.upsert("database", "database_name", db["name"], {
        "database_name": db["name"],
        "sqlalchemy_uri": warehouse_url,
        "expose_in_sqllab": db.get("expose_in_sqllab", True),
        "allow_run_async": db.get("allow_run_async", True),
        "cache_timeout": db.get("cache_timeout"),
    })


def build_dataset(api: Superset, db_id: int, ds: dict) -> int:
    ds_id = api.upsert("dataset", "table_name", ds["name"], {
        "database": db_id,
        "schema": ds.get("schema"),
        "table_name": ds["name"],
        "main_dttm_col": ds.get("main_dttm_col"),
        "description": ds.get("description", ""),
        "cache_timeout": ds.get("cache_timeout"),
    })
    # Metrics are managed via /api/v1/dataset/<id>/metric — but the
    # simplest portable path is PUT with the full metric list.
    if "metrics" in ds:
        api.s.put(
            f"{api.base}/api/v1/dataset/{ds_id}",
            json={"metrics": [
                {
                    "metric_name":  m["name"],
                    "verbose_name": m.get("verbose_name", m["name"]),
                    "expression":   m["expression"],
                    "d3format":     m.get("d3format"),
                    "description":  m.get("description", ""),
                }
                for m in ds["metrics"]
            ]},
            timeout=30,
        ).raise_for_status()
    return ds_id


def chart_params(c: dict) -> dict:
    """Translate spec-level chart fields into Superset's params blob.

    Superset stores viz config as a JSON string under `params`.
    We only set the knobs the spec actually uses; everything
    else falls back to viz defaults.
    """
    p: dict[str, Any] = {
        "viz_type":    c["viz"],
        "time_range":  c.get("time_range", "No filter"),
        "row_limit":   c.get("row_limit", 10000),
        "color_scheme": c.get("color_scheme", "beerbeerBrand"),
    }
    if "metric" in c:
        p["metric"] = c["metric"]
    if "metrics" in c:
        p["metrics"] = c["metrics"]
    if "groupby" in c:
        p["groupby"] = c["groupby"]
    if "rows" in c:
        p["groupbyRows"] = c["rows"]
    if "columns" in c:
        p["groupbyColumns"] = c["columns"]
    if c["viz"] == "big_number_total":
        p["compare_lag"]    = c.get("compare_lag", 30)
        p["compare_suffix"] = c.get("compare_suffix", "")
    if c["viz"] == "line" and c.get("rolling_type"):
        p["rolling_type"]    = c["rolling_type"]
        p["rolling_periods"] = c["rolling_periods"]
    if c["viz"] == "pie":
        p["donut"]      = c.get("donut", False)
        p["label_type"] = c.get("label_type", "key")
    if c["viz"] == "heatmap":
        p["x_axis"] = c["x_axis"]
        p["y_axis"] = c["y_axis"]
    if c["viz"] == "pivot_table_v2":
        p["row_total"]    = c.get("row_totals", True)
        p["column_total"] = c.get("col_totals", True)
    return p


def build_chart(api: Superset, ds_ids: dict[str, int], c: dict) -> int:
    return api.upsert("chart", "slice_name", c["title"], {
        "slice_name":     c["title"],
        "viz_type":       c["viz"],
        "datasource_id":   ds_ids[c["dataset"]],
        "datasource_type": "table",
        "params":         json.dumps(chart_params(c)),
    })


def build_layout(layout_rows: list, chart_ids: dict[str, int]) -> dict:
    """Produce Superset's position_json grid (12-column rows)."""
    pos: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
    }
    for row in layout_rows:
        keys = row["row"] if isinstance(row, dict) else row
        row_id = f"ROW-{uuid4().hex[:8]}"
        col_w = max(1, 12 // len(keys))
        children: list[str] = []
        for key in keys:
            chart_node = f"CHART-{uuid4().hex[:8]}"
            pos[chart_node] = {
                "type":     "CHART",
                "id":       chart_node,
                "children": [],
                "parents":  ["ROOT_ID", "GRID_ID", row_id],
                "meta": {
                    "chartId": chart_ids[key],
                    "width":   col_w,
                    "height":  50,
                },
            }
            children.append(chart_node)
        pos[row_id] = {
            "type":     "ROW",
            "id":       row_id,
            "children": children,
            "parents":  ["ROOT_ID", "GRID_ID"],
            "meta":     {"background": "BACKGROUND_TRANSPARENT"},
        }
        pos["GRID_ID"]["children"].append(row_id)
    return pos


def build_dashboard(api: Superset, spec: dict, chart_ids: dict[str, int]) -> int:
    d = spec["dashboard"]
    metadata = {
        "color_scheme":          d.get("color_scheme", "supersetColors"),
        "refresh_frequency":     d.get("refresh_frequency_sec", 0),
        "cross_filters_enabled": d.get("cross_filters_enabled", True),
        "native_filter_configuration": [
            {
                "id":           f"NATIVE_FILTER-{uuid4().hex[:8]}",
                "name":         f["name"],
                "filterType":   f["type"],
                "targets":      [{"column": {"name": f.get("column")}}] if f.get("column") else [],
                "defaultDataMask": {"filterState": {"value": f.get("default")}} if f.get("default") else {},
                "controlValues": {"multiSelect": f.get("multiple", False)},
            }
            for f in spec.get("filters", [])
        ],
    }
    return api.upsert("dashboard", "slug", d["slug"], {
        "dashboard_title": d["title"],
        "slug":            d["slug"],
        "position_json":   json.dumps(build_layout(d["layout"], chart_ids)),
        "json_metadata":   json.dumps(metadata),
        "css":             d.get("css", ""),
        "published":       True,
    })


# --- main -----------------------------------------------------

def main() -> int:
    try:
        base = os.environ["SUPERSET_URL"]
        user = os.environ["SUPERSET_USERNAME"]
        pwd  = os.environ["SUPERSET_PASSWORD"]
        whu  = os.environ["WAREHOUSE_URL"]
    except KeyError as e:
        sys.exit(f"missing required env: {e.args[0]}")

    spec = yaml.safe_load(SPEC_FILE.read_text())
    api  = Superset(base, user, pwd)

    db_id = build_database(api, spec, whu)
    print(f"  database  ✓  id={db_id}")

    ds_ids = {ds["name"]: build_dataset(api, db_id, ds) for ds in spec["datasets"]}
    for n, i in ds_ids.items():
        print(f"  dataset   ✓  {n} (id={i})")

    chart_ids = {c["key"]: build_chart(api, ds_ids, c) for c in spec["charts"]}
    for k, i in chart_ids.items():
        print(f"  chart     ✓  {k} (id={i})")

    dash_id = build_dashboard(api, spec, chart_ids)
    print(f"  dashboard ✓  id={dash_id}  →  {base}/superset/dashboard/{spec['dashboard']['slug']}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
