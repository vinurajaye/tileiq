"""End-to-end build: scrape -> normalise -> audit prices -> analyse -> export.

    python -m tileiq.pipeline              # rebuild from cached pages
    python -m tileiq.pipeline --refresh    # re-fetch every source first

Everything in the output comes from a public web page, and every price carries
its source URL, the raw text it was read from, and how its unit was resolved.
Nothing is generated, estimated or filled in. Where a number cannot be verified,
it is excluded from comparisons and reported in the audit.

Internal SAP data, when supplied in data/input/, adds the discount-guardrail
models on top; without it those sections simply report that they need it.
"""
from __future__ import annotations

import argparse
import json
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import audit, engine, export_site, images, market, promo, taxonomy
from .scrapers import buyrocell, marketing, mascons, rocell, tileshop, woocommerce

ROOT = Path(__file__).resolve().parents[1]
INPUT, OUT = ROOT / "data" / "input", ROOT / "data" / "processed"

# Sources that carry a price we can audit, and sources that are design-only.
SCRAPED_SOURCES = ["rocell", "rocell+buyrocell", "buyrocell", "lankatiles", "macktiles",
                   "mascons", "tileshop"]


def _read_any(stem: str) -> pd.DataFrame | None:
    for ext, reader in ((".csv", pd.read_csv), (".xlsx", pd.read_excel)):
        p = INPUT / f"{stem}{ext}"
        if p.exists():
            return reader(p)
    return None


def _map_sap(df: pd.DataFrame, section: str) -> pd.DataFrame:
    mapping = yaml.safe_load((ROOT / "config" / "sap_columns.yaml").read_text(encoding="utf-8"))[section]
    return df.rename(columns={v: k for k, v in mapping.items() if v in df.columns})


def build_catalog(refresh: bool, prices_only: bool = False) -> pd.DataFrame:
    """refresh re-fetches everything; prices_only re-fetches just the price sources.

    Prices move weekly, catalogues rarely. A nightly price refresh is a few hundred
    pages; a full catalogue refresh is several thousand, so they run on different
    schedules.
    """
    if prices_only:
        for mod in (buyrocell, mascons):
            mod.scrape(refresh=True)
    elif refresh:
        for mod in (rocell, buyrocell, tileshop, mascons):
            mod.scrape(refresh=True)

    # Rocell: full catalogue from rocell.com, prices from BuyRocell joined on product code.
    rocell_rows = {r["attributes"]["code"]: r for r in rocell.parse_cached() if r["attributes"]["code"]}

    def _key(name: str, size_text: str):
        base = re.sub(r"\(.*?\)|\d+\s*[xX]\s*\d+\s*(mm|cm)?|[-|]", " ", name.lower())
        return " ".join(base.split()), taxonomy.parse_size(size_text)

    by_name = {_key(r["name"], r["attributes"]["size"]): r for r in rocell_rows.values()}
    priced_only = []
    for b in buyrocell.parse_cached():
        target = rocell_rows.get(b["attributes"].get("code")) or by_name.get(_key(b["name"], b["attributes"]["size"]))
        if target:
            target.update({k: b[k] for k in ("list_price", "sell_price", "price_basis", "observed_on")})
            target["price_url"] = b["url"]          # the page the price came from
            target["attributes"]["size"] = target["attributes"]["size"] or b["attributes"]["size"]
            target["source"] = "rocell+buyrocell"
        else:
            priced_only.append(b)

    rows = (woocommerce.scrape("macktiles", refresh) + woocommerce.scrape("lankatiles", refresh)
            + list(rocell_rows.values()) + priced_only + mascons.parse_cached()
            + tileshop.parse_cached())
    (OUT / "catalog_raw.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    recs = []
    for raw in rows:
        rec = taxonomy.normalise(raw)
        rec["price_url"] = raw.get("price_url") or raw.get("url")
        recs.append(rec)
    cat = pd.DataFrame([r for r in recs if taxonomy.is_tile(r)])
    cat["size_class"] = [taxonomy.size_class((s, l) if pd.notna(s) else None)
                         for s, l in zip(cat["size_short"], cat["size_long"])]
    cat["group"] = cat["group"].fillna("Competitor")
    cat["data_quality"] = np.where(cat["source"].isin(SCRAPED_SOURCES), "Scraped", "Unknown source")
    return cat.drop_duplicates("product_id")


def run(refresh: bool = False, spot_check_n: int = 10, prices_only: bool = False) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)

    print("1/7 catalogue")
    cat = build_catalog(refresh, prices_only)

    print("2/7 price audit")
    cat, unit_evidence = audit.resolve_prices(cat)
    # Only audited, in-range prices are used anywhere downstream.
    usable = cat["price_per_sqm"].notna() & cat["price_confidence"].isin(["high", "medium"])
    cat["price_ref"] = np.where(usable, cat["price_per_sqm"], np.nan)
    cat["list_price_sqm"] = cat["price_ref"]
    findings = audit.run_checks(cat)

    print("3/7 fair-price model + comparables")
    priced = cat[cat["price_ref"].notna()].assign(list_price=lambda d: d["price_ref"])
    fair = engine.train_fair_price(priced) if len(priced) >= 30 else None
    comps = engine.Comparables(cat, fair)

    print("4/7 price position")
    pos = engine.price_position(cat, comps) if fair is not None else pd.DataFrame()

    print("5/7 market intelligence")
    trends = {by: market.global_trends(cat, by=by) for by in ("look", "size_mm", "finish", "body")}
    disc = market.discount_intelligence(cat, pos, fair)
    gaps = engine.assortment_gaps(cat, None)

    # SAP is optional: with it, the discount guardrails switch on; without it they stay off.
    billing_raw, quotes_raw = _read_any("sap_billing"), _read_any("sap_quotes")
    has_sap = billing_raw is not None
    curves, ceilings, leak, rec = pd.DataFrame(), {}, pd.DataFrame(), pd.DataFrame()
    if has_sap:
        print("     SAP data found - building discount guardrails")
        billing_path = OUT / "sap_billing_mapped.csv"
        _map_sap(billing_raw, "billing").to_csv(billing_path, index=False)
        billing = engine.load_billing(billing_path)
        if quotes_raw is not None:
            quotes = _map_sap(quotes_raw, "quotes")
            curves, ceilings = engine.win_curves(quotes)
            leak = engine.discount_leakage(billing, ceilings)
            rec = engine.recommend(pos, ceilings)
            quotes.to_parquet(OUT / "quotes.parquet")
        leak.to_parquet(OUT / "billing_scored.parquet") if len(leak) else None

    print("6/8 marketing footprint")
    mk_rows = marketing.scrape(refresh=refresh or prices_only)
    mk_score, mk_matrix = promo.build(mk_rows, cat)
    mk_headlines = promo.headlines(mk_score, mk_matrix)

    print("7/8 live spot check")
    spot = audit.spot_check(cat, n=spot_check_n) if spot_check_n else pd.DataFrame()

    print("8/8 thumbnails")
    images.prefetch(cat["image"].dropna().tolist(), label="thumbnails")

    cat.to_parquet(OUT / "catalog.parquet")
    pos.to_parquet(OUT / "price_position.parquet")
    gaps.to_parquet(OUT / "gaps.parquet")
    disc.to_parquet(OUT / "discount_intel.parquet")
    unit_evidence.to_parquet(OUT / "unit_evidence.parquet")
    if len(mk_score):
        mk_score.to_parquet(OUT / "marketing_score.parquet")
        mk_matrix.to_parquet(OUT / "marketing_features.parquet")
        (OUT / "marketing_headlines.json").write_text(json.dumps(mk_headlines, default=str), encoding="utf-8")
    findings.to_parquet(OUT / "audit_findings.parquet")
    if len(spot):
        spot.to_parquet(OUT / "spot_check.parquet")
    for by, df in trends.items():
        df.to_parquet(OUT / f"trends_{by}.parquet")
    if len(curves):
        curves.to_parquet(OUT / "win_curves.parquet")
    if len(rec):
        rec.to_parquet(OUT / "recommendations.parquet")
    if fair is not None:
        with open(OUT / "models.pkl", "wb") as f:
            pickle.dump({"fair": fair}, f)

    meta = {
        "built_at": pd.Timestamp.now().isoformat(timespec="minutes"),
        "products": int(len(cat)),
        "priced_products": int(cat["price_ref"].notna().sum()),
        "unresolved_prices": int((cat["list_price"].notna() & cat["price_ref"].isna()).sum()),
        "n_global": int((cat["group"] == "Global").sum()),
        "has_sap": has_sap,
        "fair_r2": getattr(fair, "r2", None),
        "fair_n": getattr(fair, "n", None),
        "ceilings": ceilings,
        "spot_check": {"checked": int(len(spot)),
                       "matched": int((spot["result"] == "match").sum()) if len(spot) else 0},
        "sources": cat.groupby("source").agg(products=("product_id", "count"),
                                             priced=("price_ref", lambda s: int(s.notna().sum()))
                                             ).reset_index().to_dict("records"),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print("   exporting site data")
    export_site.run()

    print(json.dumps({k: v for k, v in meta.items() if k not in ("sources", "ceilings")}, indent=1, default=str))
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch every source before rebuilding")
    ap.add_argument("--refresh-prices", action="store_true",
                    help="re-fetch only the sources that publish prices (fast, for nightly runs)")
    ap.add_argument("--spot-check", type=int, default=10, help="how many live pages to re-verify")
    a = ap.parse_args()
    run(a.refresh, a.spot_check, a.refresh_prices)
