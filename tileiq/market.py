"""Intelligence that needs only public web data - no SAP, no internal systems.

Three things live here:

1. global_trends()        what the world is launching and selling, vs what we stock
2. discount_intelligence() discount we give vs discount the market actually requires
3. location_variance()    the same tile priced differently by place of sale

(1) uses The Tile Shop's own best-seller / new-arrival flags as the demand
signal. (2) uses real published list and offer prices. (3) needs captured
prices that carry a location, so it stays empty until the field team logs them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import OURS

GLOBAL_GROUP = "Global"


# ---------------------------------------------------------------- 1. global trends
def global_trends(cat: pd.DataFrame, by: str = "look", min_skus: int = 8) -> pd.DataFrame:
    """Global demand and launch momentum per attribute value, vs our own range.

    demand_index  - best-seller share in this segment ÷ best-seller share overall
                    (>1 means the segment punches above its weight in what sells)
    launch_index  - same calculation for new arrivals: where the market is heading
    our_share     - share of V One SKUs in this segment
    """
    g = cat[cat["group"] == GLOBAL_GROUP]
    ours = cat[cat["brand"].isin(OURS)]
    if g.empty:
        return pd.DataFrame()

    base_bs = g["is_bestseller"].fillna(False).mean() or np.nan
    base_new = g["is_new_arrival"].fillna(False).mean() or np.nan

    rows = []
    for value, seg in g.groupby(by):
        if value in ("Unknown", "", None) or len(seg) < min_skus:
            continue
        own = ours[ours[by] == value]
        rows.append({
            by: value,
            "global_skus": len(seg),
            "global_share": len(seg) / len(g),
            "bestseller_share": seg["is_bestseller"].fillna(False).mean(),
            "new_arrival_share": seg["is_new_arrival"].fillna(False).mean(),
            "clearance_share": seg["is_clearance"].fillna(False).mean(),
            "demand_index": seg["is_bestseller"].fillna(False).mean() / base_bs if base_bs else np.nan,
            "launch_index": seg["is_new_arrival"].fillna(False).mean() / base_new if base_new else np.nan,
            "usd_sqm_median": seg["usd_per_sqm"].median(),
            "our_skus": len(own),
            "our_share": len(own) / max(len(ours), 1),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Where the world over-indexes and we under-index, ranked.
    out["coverage_ratio"] = out["our_share"] / out["global_share"]
    out["opportunity"] = ((out["demand_index"].fillna(0) + out["launch_index"].fillna(0)) / 2) / \
                         out["coverage_ratio"].replace(0, np.nan).fillna(0.05)
    out["verdict"] = np.select(
        [(out["coverage_ratio"] < 0.6) & (out["demand_index"] >= 1),
         (out["coverage_ratio"] < 0.6),
         (out["coverage_ratio"] > 1.6) & (out["demand_index"] < 1)],
        ["Under-served, selling well globally", "Under-served globally", "We over-index, world doesn't"],
        "In line with the market")
    return out.sort_values("opportunity", ascending=False)


def trending_examples(cat: pd.DataFrame, by: str, value: str, k: int = 8) -> pd.DataFrame:
    """Global best sellers / new arrivals in a segment, for the design team to look at."""
    g = cat[(cat["group"] == GLOBAL_GROUP) & (cat[by] == value)].copy()
    g["rank"] = g["is_bestseller"].fillna(False).astype(int) * 2 + g["is_new_arrival"].fillna(False).astype(int)
    return g.sort_values(["rank", "usd_per_sqm"], ascending=[False, False]).head(k)


# ---------------------------------------------------------------- 2. discount intelligence
def discount_intelligence(cat: pd.DataFrame, position: pd.DataFrame, fair=None) -> pd.DataFrame:
    """What we publish as a discount, and whether the resulting price still makes sense.

    Two reference points, both real:
      * `benchmark`  - a comparable competitor's published price, where one exists.
      * `fair_value` - what this specification is worth inside our own range,
                       from the hedonic model. This catches a tile discounted far
                       below what its own size/body/finish commands, which is the
                       common case when no competitor publishes a price.
    """
    ours = cat[cat["brand"].isin(OURS) & cat["price_ref"].notna() & cat["list_per_sqm"].notna()].copy()
    ours = ours[ours["list_per_sqm"] > 0]
    if ours.empty:
        return pd.DataFrame()

    out = pd.DataFrame({
        "product_id": ours["product_id"], "brand": ours["brand"], "name": ours["name"],
        "size_mm": ours["size_mm"], "body": ours["body"], "finish": ours["finish"], "look": ours["look"],
        "our_list": ours["list_per_sqm"], "our_sell": ours["price_ref"],
        "url": ours["price_url"].fillna(ours["url"]), "img": ours["image"],
    })
    out["discount_pct"] = ((1 - out["our_sell"] / out["our_list"]) * 100).round(1)

    if fair is not None:
        out["fair_value"] = np.round(fair.predict(ours), 0)
        out["vs_fair_pct"] = ((out["our_sell"] / out["fair_value"] - 1) * 100).round(1)
    else:
        out["fair_value"], out["vs_fair_pct"] = np.nan, np.nan

    # Competitor benchmark where one is published for a comparable tile.
    if len(position):
        bench = position.set_index("product_id")[["benchmark", "verified_comps"]]
        out = out.join(bench, on="product_id")
        out["needed_pct"] = ((1 - out["benchmark"] / out["our_list"]) * 100).clip(lower=0).round(1)
        out["excess_pct"] = (out["discount_pct"] - out["needed_pct"]).round(1)
        out["excess_lkr_sqm"] = (out["our_list"] * out["excess_pct"] / 100).round(0)
    else:
        for c in ("benchmark", "verified_comps", "needed_pct", "excess_pct", "excess_lkr_sqm"):
            out[c] = np.nan

    out["verdict"] = np.select(
        [out["excess_pct"] > 3,
         out["vs_fair_pct"] < -20,
         out["discount_pct"] >= 40],
        ["Discounted past the nearest published competitor price",
         "Selling well below what this specification commands in our own range",
         "Deep published discount"],
        "In line")
    out["give_away_lkr_sqm"] = np.where(
        out["excess_lkr_sqm"].notna(), out["excess_lkr_sqm"],
        np.where(out["vs_fair_pct"] < 0, (out["fair_value"] - out["our_sell"]).round(0), np.nan))
    return out.sort_values("give_away_lkr_sqm", ascending=False, na_position="last")


# ---------------------------------------------------------------- 3. price by location
def location_variance(field_prices: pd.DataFrame, cat: pd.DataFrame) -> pd.DataFrame:
    """Same product, different place of sale: is one branch or dealer pricing higher?

    Needs captured prices that carry a location (`where_seen` / `location`).
    """
    if field_prices is None or field_prices.empty:
        return pd.DataFrame()
    f = field_prices.copy()
    loc_col = next((c for c in ("location", "branch", "where_seen") if c in f), None)
    if loc_col is None:
        return pd.DataFrame()
    f["price"] = f.get("offer_price_lkr_sqm").fillna(f["list_price_lkr_sqm"]) if "offer_price_lkr_sqm" in f \
        else f["list_price_lkr_sqm"]
    g = f.groupby(["product_id", loc_col])["price"].mean().reset_index()
    stats = g.groupby("product_id")["price"].agg(["count", "min", "max", "mean"])
    stats = stats[stats["count"] >= 2]
    if stats.empty:
        return pd.DataFrame()
    stats["spread_pct"] = ((stats["max"] - stats["min"]) / stats["mean"] * 100).round(1)
    names = cat.set_index("product_id")[["brand", "name", "size_mm", "finish", "look"]]
    out = stats.join(names).reset_index().sort_values("spread_pct", ascending=False)
    cheapest = g.loc[g.groupby("product_id")["price"].idxmin()].set_index("product_id")[loc_col]
    dearest = g.loc[g.groupby("product_id")["price"].idxmax()].set_index("product_id")[loc_col]
    out["cheapest_at"] = out["product_id"].map(cheapest)
    out["dearest_at"] = out["product_id"].map(dearest)
    return out


# ---------------------------------------------------------------- head to head
def brand_matrix(cat: pd.DataFrame, rows: str = "look", cols: str = "size_mm",
                 brands: list[str] | None = None) -> pd.DataFrame:
    """SKU counts per brand for a rows x cols grid - who covers what."""
    c = cat[cat["group"] != GLOBAL_GROUP]
    if brands:
        c = c[c["brand"].isin(brands)]
    return c.pivot_table(index=rows, columns=[cols, "brand"], values="product_id", aggfunc="count", fill_value=0)


def head_to_head(cat: pd.DataFrame, size_mm: str | None = None, finish: str | None = None,
                 look: str | None = None, brands: list[str] | None = None, per_brand: int = 6) -> dict:
    """Matching products per brand for a spec, ready to show side by side."""
    c = cat.copy()
    for col, val in (("size_mm", size_mm), ("finish", finish), ("look", look)):
        if val and val != "Any":
            c = c[c[col] == val]
    out = {}
    for b in (brands or ["Rocell", "Lanka Tiles", "Macktiles"]):
        sel = c[c["brand"] == b].copy()
        sel = sel.sort_values(["price_ref", "name"], na_position="last")
        out[b] = sel.head(per_brand)
    return out
