#!/usr/bin/env python3
"""
Render docs/preview.png — a matplotlib mock-up of how the
BeerBeer dashboard will look once spec.yaml is materialised in
Superset. Same seed-data logic as data/sql/02_seed.sql, same
metric definitions as dashboard/spec.yaml, same brand palette
as superset_config/superset_config.py.

This is a *preview*, not a Superset screenshot — useful for
PR review and design iteration before standing the stack up.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "docs" / "preview.png"
OUT.parent.mkdir(exist_ok=True)

# Brand palette (matches superset_config.py) -------------------
BRAND   = ["#F2A900", "#5C3A21", "#C73E1D", "#1B998B",
           "#2E294E", "#E0CA3C", "#7B2D26", "#A0C1B9"]
INK     = "#1B1B1F"
MUTED   = "#6B6B73"
PANEL   = "#FFFFFF"
CANVAS  = "#F4F1EC"
GRID    = "#E6E1D8"
UP_GRN  = "#1B998B"
DN_RED  = "#C73E1D"


# --- Synthetic warehouse (mirrors 02_seed.sql) ----------------

rng = np.random.default_rng(42)
TODAY = date.today()
DAYS  = pd.date_range(TODAY - timedelta(days=179), TODAY, freq="D")

beers = pd.DataFrame([
    ("BB-IPA-330", "Hop Highway IPA",     "IPA",      330, 28.0),
    ("BB-IPA-500", "Hop Highway IPA",     "IPA",      500, 38.0),
    ("BB-NEI-330", "Cloud Surfer NEIPA",  "NEIPA",    330, 32.0),
    ("BB-STO-330", "Midnight Oats Stout", "Stout",    330, 30.0),
    ("BB-STO-750", "Midnight Oats Stout", "Stout",    750, 68.0),
    ("BB-LAG-330", "Pearl Lager",         "Lager",    330, 18.0),
    ("BB-LAG-500", "Pearl Lager",         "Lager",    500, 24.0),
    ("BB-PIL-330", "Tsing Pilsner",       "Pilsner",  330, 20.0),
    ("BB-SOU-330", "Plum Sour",           "Sour",     330, 34.0),
    ("BB-WIT-330", "Garden Witbier",      "Witbier",  330, 26.0),
    ("BB-SAI-750", "Farmhouse Saison",    "Saison",   750, 72.0),
    ("BB-PAL-330", "Daydream Pale Ale",   "Pale Ale", 330, 24.0),
], columns=["sku", "name", "style", "package_ml", "list_price"])

stores = pd.DataFrame([
    ("SH-TAP-01", "on-premise",  "华东"),
    ("SH-RET-02", "off-premise", "华东"),
    ("BJ-TAP-01", "on-premise",  "华北"),
    ("BJ-RET-02", "off-premise", "华北"),
    ("GZ-RET-01", "off-premise", "华南"),
    ("SZ-TAP-01", "on-premise",  "华南"),
    ("CD-RET-01", "off-premise", "西南"),
    ("ON-DTC-01", "online",      "海外"),
], columns=["store_code", "channel", "region"])

style_pop = {"IPA": 14, "NEIPA": 11, "Lager": 16, "Pilsner": 12,
             "Pale Ale": 10, "Stout": 7, "Witbier": 8, "Sour": 6, "Saison": 5}
chan_mult = {"on-premise": 1.0, "off-premise": 1.6, "online": 2.2}

# Build fact table the cheap way: join via cross-join
grid = (
    pd.MultiIndex.from_product([DAYS, beers.index, stores.index],
                               names=["sale_date", "b", "s"])
    .to_frame(index=False)
)
grid = grid.merge(beers, left_on="b", right_index=True) \
           .merge(stores, left_on="s", right_index=True)

is_weekend = grid.sale_date.dt.dayofweek >= 5
days_in    = (grid.sale_date - DAYS[0]).dt.days
base = (
    grid["style"].map(style_pop)
    * grid["channel"].map(chan_mult)
    * np.where(is_weekend & (grid["channel"] == "on-premise"), 1.8, 1.0)
    * (1.0 + 0.0014 * days_in)
    * rng.uniform(0.75, 1.25, len(grid))
)
grid["units"]    = np.maximum(0, base.round()).astype(int)
disc_rate        = np.where(rng.random(len(grid)) < 0.25, rng.uniform(0, 0.15, len(grid)), 0)
grid["gross"]    = grid.units * grid.list_price
grid["discount"] = grid.gross * disc_rate
grid["net"]      = grid.gross - grid.discount
grid["cogs"]     = grid.gross * 0.42
grid["profit"]   = grid.net - grid.cogs
grid = grid[grid.units > 0]

# --- Aggregations ---------------------------------------------

last_30   = grid[grid.sale_date >= pd.Timestamp(TODAY - timedelta(days=30))]
prev_30   = grid[(grid.sale_date < pd.Timestamp(TODAY - timedelta(days=30))) &
                 (grid.sale_date >= pd.Timestamp(TODAY - timedelta(days=60)))]

def kpi(df):
    return dict(
        net    = df.net.sum(),
        units  = df.units.sum(),
        margin = df.profit.sum() / df.net.sum(),
        aup    = df.net.sum() / df.units.sum(),
    )

cur, prv = kpi(last_30), kpi(prev_30)

daily = grid.groupby("sale_date", as_index=False).net.sum()
daily = daily[daily.sale_date >= pd.Timestamp(TODAY - timedelta(days=90))]
daily["ma7"] = daily.net.rolling(7, min_periods=1).mean()

top_sku = (last_30.groupby(["name", "package_ml"], as_index=False)
                  .net.sum().sort_values("net", ascending=False).head(10))
top_sku["label"] = top_sku.name + "  " + top_sku.package_ml.astype(str) + "ml"

style_mix = (last_30.groupby("style", as_index=False).net.sum()
                    .sort_values("net", ascending=False)
                    .rename(columns={"style": "style_name"}))

pivot = last_30.pivot_table(index="region", columns="channel",
                            values="net", aggfunc="sum", fill_value=0)
pivot["合计"] = pivot.sum(axis=1)
pivot = pivot.sort_values("合计", ascending=False)

heat = (grid[grid.sale_date >= pd.Timestamp(TODAY - timedelta(days=90))]
        .assign(dow=lambda d: d.sale_date.dt.dayofweek,
                wk=lambda d: d.sale_date.dt.isocalendar().week)
        .pivot_table(index="dow", columns="wk", values="net", aggfunc="sum",
                     fill_value=0))


# --- Render ---------------------------------------------------

plt.rcParams.update({
    "font.family":      ["WenQuanYi Zen Hei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "axes.edgecolor":   GRID,
    "axes.labelcolor":  MUTED,
    "axes.titleweight": "bold",
    "axes.titlecolor":  INK,
    "xtick.color":      MUTED,
    "ytick.color":      MUTED,
    "axes.grid":        True,
    "grid.color":       GRID,
    "grid.linewidth":   0.6,
})

fig = plt.figure(figsize=(18, 12), facecolor=CANVAS)
gs = GridSpec(5, 4, figure=fig,
              height_ratios=[0.55, 1.6, 2.2, 3.0, 3.0],
              hspace=0.55, wspace=0.28,
              left=0.04, right=0.98, top=0.96, bottom=0.04)

# Header banner
hdr = fig.add_subplot(gs[0, :])
hdr.axis("off")
hdr.text(0.0, 0.6, "BeerBeer 销售总览", fontsize=22,
         fontweight="bold", color=INK, transform=hdr.transAxes)
hdr.text(0.0, 0.05,
         f"数据源 warehouse.v_sales  ·  时间范围 近 30 天  ·  生成于 {TODAY.isoformat()}",
         fontsize=10, color=MUTED, transform=hdr.transAxes)
hdr.text(1.0, 0.05, "● 已发布   ⟳ 自动刷新 关闭",
         fontsize=10, color=MUTED, ha="right", transform=hdr.transAxes)


def kpi_panel(ax, title, value, delta_pct, fmt):
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    ax.grid(False)
    # rounded panel
    ax.add_patch(FancyBboxPatch((0.01, 0.04), 0.98, 0.92,
                                 boxstyle="round,pad=0.0,rounding_size=0.04",
                                 transform=ax.transAxes, facecolor=PANEL,
                                 edgecolor=GRID, linewidth=1))
    ax.text(0.06, 0.78, title, fontsize=11, color=MUTED, transform=ax.transAxes)
    ax.text(0.06, 0.34, fmt(value), fontsize=26, fontweight="bold",
            color=INK, transform=ax.transAxes)
    arrow = "▲" if delta_pct >= 0 else "▼"
    color = UP_GRN if delta_pct >= 0 else DN_RED
    ax.text(0.06, 0.12, f"{arrow} {abs(delta_pct):.1%}  vs 上 30 天",
            fontsize=10, color=color, transform=ax.transAxes)


kpi_panel(fig.add_subplot(gs[1, 0]), "净收入 (近 30 天)",
          cur["net"],    cur["net"]/prv["net"]-1,       lambda v: f"¥ {v:,.0f}")
kpi_panel(fig.add_subplot(gs[1, 1]), "销售件数 (近 30 天)",
          cur["units"],  cur["units"]/prv["units"]-1,   lambda v: f"{int(v):,}")
kpi_panel(fig.add_subplot(gs[1, 2]), "毛利率 (近 30 天)",
          cur["margin"], cur["margin"]-prv["margin"],   lambda v: f"{v:.1%}")
kpi_panel(fig.add_subplot(gs[1, 3]), "客单价 (近 30 天)",
          cur["aup"],    cur["aup"]/prv["aup"]-1,       lambda v: f"¥ {v:.2f}")

# Trend
ax = fig.add_subplot(gs[2, :]); ax.set_facecolor(PANEL)
ax.fill_between(daily.sale_date, daily.net, color=BRAND[0], alpha=0.18, linewidth=0)
ax.plot(daily.sale_date, daily.net,  color=BRAND[0], linewidth=1.4, label="日净收入")
ax.plot(daily.sale_date, daily.ma7,  color=BRAND[4], linewidth=2.2, label="7 日均线")
ax.set_title("净收入与 7 日均线 (近 90 天)", loc="left", pad=10, fontsize=13)
ax.legend(loc="upper left", frameon=False, fontsize=9)
ax.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(
    lambda v, _: f"¥{v/1e3:.0f}K"))
ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)

# Top SKU bar
ax = fig.add_subplot(gs[3, :2]); ax.set_facecolor(PANEL)
y = np.arange(len(top_sku))[::-1]
ax.barh(y, top_sku.net, color=BRAND[0], edgecolor="none", height=0.7)
ax.set_yticks(y); ax.set_yticklabels(top_sku.label, fontsize=9)
ax.set_title("Top 10 SKU(按净收入,近 30 天)", loc="left", pad=10, fontsize=13)
ax.xaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(
    lambda v, _: f"¥{v/1e3:.0f}K"))
for spine in ("top", "right", "left"): ax.spines[spine].set_visible(False)
ax.grid(axis="y", visible=False)

# Style donut
ax = fig.add_subplot(gs[3, 2:]); ax.set_facecolor(PANEL)
wedges, _ = ax.pie(style_mix.net, colors=BRAND[:len(style_mix)],
                   wedgeprops=dict(width=0.42, edgecolor=PANEL, linewidth=2),
                   startangle=90)
ax.set_title("风格销售占比 (近 30 天)", loc="left", pad=10, fontsize=13)
total = style_mix.net.sum()
labels = [f"{s}  {n/total:.0%}" for s, n in zip(style_mix["style_name"], style_mix["net"])]
ax.legend(wedges, labels, loc="center left",
          bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=9)
ax.text(0, 0.05, "净收入", ha="center", fontsize=10, color=MUTED)
ax.text(0, -0.15, f"¥{total/1e3:.0f}K", ha="center", fontsize=18,
        fontweight="bold", color=INK)

# Region × channel pivot
ax = fig.add_subplot(gs[4, :2]); ax.set_facecolor(PANEL); ax.axis("off")
ax.set_title("区域 × 渠道净收入 (近 30 天)", loc="left", pad=10, fontsize=13,
             color=INK, fontweight="bold")
cell_text = [[f"¥{v/1e3:.0f}K" for v in row] for row in pivot.values]
tbl = ax.table(cellText=cell_text,
               rowLabels=pivot.index.tolist(),
               colLabels=pivot.columns.tolist(),
               cellLoc="right", rowLoc="center", loc="center",
               colWidths=[0.18]*len(pivot.columns))
tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.6)
for (r, c), cell in tbl.get_celld().items():
    cell.set_edgecolor(GRID)
    if r == 0:                             cell.set_facecolor("#FAF7F1"); cell.set_text_props(weight="bold", color=INK)
    elif c == -1:                          cell.set_text_props(weight="bold", color=INK)
    elif pivot.columns[c] == "合计":       cell.set_text_props(weight="bold", color=INK); cell.set_facecolor("#FAF7F1")

# Heatmap
ax = fig.add_subplot(gs[4, 2:]); ax.set_facecolor(PANEL)
im = ax.imshow(heat.values, aspect="auto", cmap="YlOrBr")
ax.set_yticks(range(7))
ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], fontsize=9)
xt = list(heat.columns)
ax.set_xticks(range(0, len(xt), max(1, len(xt)//8)))
ax.set_xticklabels([f"W{xt[i]}" for i in range(0, len(xt), max(1, len(xt)//8))],
                   fontsize=8)
ax.set_title("星期 × 周次销售热力 (近 90 天)", loc="left", pad=10, fontsize=13)
ax.grid(False)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
cb.outline.set_visible(False); cb.ax.tick_params(labelsize=8)

fig.savefig(OUT, dpi=130, facecolor=CANVAS, bbox_inches="tight")
print(f"wrote {OUT}")
