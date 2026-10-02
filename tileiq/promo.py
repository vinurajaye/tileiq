"""Marketing intelligence: the same treatment prices get, applied to promotion.

Reads the public marketing footprint (tileiq/scrapers/marketing.py) and turns it
into four comparable measures per brand:

  reach       audience on channels that publish their numbers (LinkedIn, YouTube)
  content     how much editorial the brand publishes and how fresh it is
  experience  which digital features the site actually offers
  promotion   how heavily the brand discounts in public, from our own price data

Every score is a plain ratio against the global leaders, so "we are behind" is
always expressed as a multiple a reader can check, never a black-box index.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import OURS
from .scrapers.marketing import FEATURES

# Channels whose numbers are only visible behind a login, so we never guess them.
UNAVAILABLE = ["Facebook", "Instagram", "TikTok"]


def build(rows: list[dict], catalog: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (per-brand scorecard, feature matrix)."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df, pd.DataFrame()

    for col in ("linkedin_followers", "youtube_subscribers", "youtube_views", "pages_blog",
                "pages_inspiration", "pages_projects", "pages_total", "pages_updated_12m",
                "linkedin_employees", "feature_count"):
        if col not in df:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["content_pages"] = df[["pages_blog", "pages_inspiration", "pages_projects"]].sum(axis=1, min_count=1)
    df["audience"] = df[["linkedin_followers", "youtube_subscribers"]].sum(axis=1, min_count=1)

    # Public discounting, measured from the prices we already audit.
    if catalog is not None and len(catalog):
        ours = catalog[catalog["price_ref"].notna() & catalog["list_per_sqm"].notna()].copy()
        ours["disc"] = (1 - ours["price_ref"] / ours["list_per_sqm"]) * 100
        promo = ours.groupby("brand").agg(
            priced_skus=("product_id", "count"),
            on_offer_pct=("disc", lambda s: float((s > 1).mean() * 100)),
            avg_discount_pct=("disc", lambda s: float(s[s > 1].mean()) if (s > 1).any() else 0.0),
            deepest_discount_pct=("disc", "max")).reset_index()
        df = df.merge(promo, on="brand", how="left")
    else:
        for c in ("priced_skus", "on_offer_pct", "avg_discount_pct", "deepest_discount_pct"):
            df[c] = np.nan

    # Benchmarks: the global leaders' median on each measure.
    leaders = df[df["group"] == "Global"]
    bench = {
        "audience": leaders["audience"].median(),
        "youtube_views": leaders["youtube_views"].median(),
        "content_pages": leaders["content_pages"].median(),
        "feature_count": leaders["feature_count"].median(),
    }
    for key, value in bench.items():
        df[f"{key}_vs_leaders"] = (df[key] / value).round(2) if value and not np.isnan(value) else np.nan

    # A site that blocks automated reads is "unknown", not "has no features".
    unreadable = df["feature_count"].fillna(0).eq(0) & df["pages_total"].isna()
    df.loc[unreadable, ["feature_count", "feature_count_vs_leaders"]] = np.nan
    df["readable"] = ~unreadable

    df["is_ours"] = df["brand"].isin(OURS)
    return df.sort_values(["group", "audience"], ascending=[True, False]), feature_matrix(rows)


def feature_matrix(rows: list[dict]) -> pd.DataFrame:
    """Which digital features each brand offers, one row per feature."""
    out = []
    for feature in FEATURES:
        row = {"feature": feature}
        for r in rows:
            row[r["brand"]] = bool((r.get("features") or {}).get(feature))
        out.append(row)
    m = pd.DataFrame(out)
    ours = [r["brand"] for r in rows if r["brand"] in OURS]
    leaders = [r["brand"] for r in rows if r["group"] == "Global"]
    if ours and leaders:
        m["we_have"] = m[ours].any(axis=1)
        m["leaders_with"] = m[leaders].sum(axis=1)
        m["leader_share"] = (m["leaders_with"] / len(leaders) * 100).round(0)
        m["verdict"] = np.select(
            [(~m["we_have"]) & (m["leader_share"] >= 60),
             (~m["we_have"]) & (m["leader_share"] > 0),
             m["we_have"] & (m["leader_share"] < 40)],
            ["Missing — most global leaders offer it", "Missing — some leaders offer it",
             "We offer it and most leaders don't"], "Covered")
    return m


def headlines(score: pd.DataFrame, matrix: pd.DataFrame) -> list[dict]:
    """The few sentences a leadership reader should take away."""
    out = []
    if score.empty:
        return out
    ours = score[score["is_ours"]]
    leaders = score[score["group"] == "Global"]
    if len(ours) and len(leaders):
        best_ours = ours.loc[ours["audience"].idxmax()] if ours["audience"].notna().any() else None
        top = leaders.loc[leaders["audience"].idxmax()] if leaders["audience"].notna().any() else None
        if best_ours is not None and top is not None:
            out.append({
                "point": "Audience",
                "text": f"{top['brand']} reaches {int(top['audience']):,} followers across LinkedIn and YouTube; "
                        f"our strongest brand, {best_ours['brand']}, reaches {int(best_ours['audience']):,}.",
                "ratio": round(float(top["audience"]) / max(float(best_ours["audience"]), 1), 1)})
        if ours["youtube_views"].notna().any() and leaders["youtube_views"].notna().any():
            ov, lv = ours["youtube_views"].max(), leaders["youtube_views"].max()
            out.append({
                "point": "Video",
                "text": f"Lifetime video views: best global leader {int(lv):,} vs our {int(ov):,}.",
                "ratio": round(float(lv) / max(float(ov), 1), 1)})
        if ours["content_pages"].notna().any() and leaders["content_pages"].notna().any():
            oc, lc = ours["content_pages"].max(), leaders["content_pages"].median()
            out.append({
                "point": "Content",
                "text": f"Editorial pages published: our best is {int(oc):,}, the global leader median is {int(lc):,}.",
                "ratio": round(float(lc) / max(float(oc), 1), 2)})
    if len(matrix) and "verdict" in matrix:
        missing = matrix[matrix["verdict"].str.startswith("Missing — most")]["feature"].tolist()
        if missing:
            out.append({"point": "Website features",
                        "text": "Most global leaders offer these and we do not: " + ", ".join(missing) + ".",
                        "ratio": None})
    return out
