"""Export the build as static JSON + images for the web interface.

The front end is a static site: no server, no query engine, no lag. Everything
it needs is written here as compact JSON, and the thumbnails are copied in, so
the whole thing can be hosted free on any static host.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import images

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
SITE = ROOT / "site"
SITE_DATA, SITE_IMG = SITE / "data", SITE / "img"


def _read(name: str) -> pd.DataFrame:
    f = OUT / f"{name}.parquet"
    return pd.read_parquet(f) if f.exists() else pd.DataFrame()


def _clean(records: list[dict]) -> list[dict]:
    """JSON-safe, and drop empty values to keep the payload small."""
    out = []
    for r in records:
        row = {}
        for k, v in r.items():
            if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
                continue
            # Lists and dicts (feature flags, social links) pass through as-is;
            # comparing them to "" would raise on numpy arrays.
            if isinstance(v, (list, tuple, dict, np.ndarray)):
                v = list(v) if isinstance(v, (tuple, np.ndarray)) else v
                if len(v):
                    row[k] = {kk: bool(vv) for kk, vv in v.items()} if isinstance(v, dict) else \
                        [x.item() if hasattr(x, "item") else x for x in v]
                continue
            if isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = round(float(v), 2)
            elif isinstance(v, (np.bool_,)):
                v = bool(v)
            elif isinstance(v, pd.Timestamp):
                v = v.isoformat()
            if v == "" or v == "Unknown":
                continue
            row[k] = v
        out.append(row)
    return out


def _write(name: str, payload) -> int:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    f = SITE_DATA / f"{name}.json"
    f.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return f.stat().st_size


def copy_images(cat: pd.DataFrame) -> int:
    """Copy cached thumbnails into the site folder (only the ones not already there)."""
    SITE_IMG.mkdir(parents=True, exist_ok=True)
    copied = 0
    for url in cat["image"].dropna().unique():
        src = images.path_for(url)
        if not src.exists():
            continue
        dst = SITE_IMG / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            copied += 1
    return copied


def img_name(url) -> str | None:
    if not isinstance(url, str) or not url.startswith("http"):
        return None
    p = images.path_for(url)
    return p.name if p.exists() else None


def run() -> dict:
    cat = _read("catalog")
    if cat.empty:
        raise SystemExit("No build found - run python -m tileiq.pipeline first.")
    meta = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))

    # ---- catalogue: short keys, only what the UI draws
    c = cat.copy()
    c["img"] = c["image"].map(img_name)
    cols = {
        "product_id": "id", "brand": "b", "group": "g", "name": "n", "size_mm": "sz", "body": "bd",
        "finish": "f", "look": "lk", "colour": "cl", "price_per_sqm": "p", "price_confidence": "pc",
        "price_unit": "pu", "unit_basis": "ub", "list_price": "lp", "price_raw_text": "praw",
        "url": "u", "price_url": "pu_url", "img": "img", "launched": "dt", "is_bestseller": "bs",
        "is_new_arrival": "new", "usd_per_sqm": "usd", "origin": "or", "thickness_mm": "th",
        "size_short": "ss", "size_long": "sl", "application": "ap",
    }
    cat_out = c[[k for k in cols if k in c]].rename(columns=cols)
    sizes = _write("catalog", _clean(cat_out.to_dict("records")))

    # ---- everything else
    payload_sizes = {"catalog": sizes}
    for name, df in (("position", _read("price_position")), ("discount", _read("discount_intel")),
                     ("gaps", _read("gaps")), ("audit", _read("audit_findings")),
                     ("units", _read("unit_evidence")), ("spot", _read("spot_check")),
                     ("recommendations", _read("recommendations")),
                     ("marketing", _read("marketing_score")),
                     ("marketing_features", _read("marketing_features"))):
        payload_sizes[name] = _write(name, _clean(df.to_dict("records")) if len(df) else [])

    trends = {by: _clean(_read(f"trends_{by}").to_dict("records")) for by in ("look", "size_mm", "finish", "body")}
    payload_sizes["trends"] = _write("trends", trends)

    # Fair-price attribute premiums, for the pricing view.
    premiums = []
    model_file = OUT / "models.pkl"
    if model_file.exists():
        import pickle
        fair = pickle.load(open(model_file, "rb"))["fair"]
        prem = fair.premiums
        prem = prem[prem["attribute"].isin(["body", "finish", "look", "brand"])]
        prem = prem[prem["value"].notna() & (prem["value"] != "Unknown")]
        premiums = _clean(prem[["attribute", "value", "premium_pct"]].to_dict("records"))
    payload_sizes["premiums"] = _write("premiums", premiums)

    # Cache-bust the assets so a rebuilt site is never served from a stale cache.
    stamp = str(int(pd.Timestamp.now().timestamp()))
    index = SITE / "index.html"
    if index.exists():
        html = re.sub(r'(app\.js|styles\.css)\?v=[^"]*', lambda m: f"{m.group(1)}?v={stamp}",
                      index.read_text(encoding="utf-8"))
        index.write_text(html, encoding="utf-8")

    hl = OUT / "marketing_headlines.json"
    payload_sizes["marketing_headlines"] = _write(
        "marketing_headlines", json.loads(hl.read_text(encoding="utf-8")) if hl.exists() else [])

    copied = copy_images(cat)
    meta["images_local"] = len(list(SITE_IMG.glob("*.jpg")))
    meta["payload_kb"] = {k: round(v / 1024) for k, v in payload_sizes.items()}
    _write("meta", meta)

    print(f"  site: {len(cat_out):,} products, {copied} new images, "
          f"{sum(payload_sizes.values()) / 1024:,.0f} KB of JSON")
    return meta


if __name__ == "__main__":
    run()
