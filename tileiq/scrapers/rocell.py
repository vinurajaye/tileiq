"""Full Rocell tile catalogue from rocell.com.

Each product page embeds its record as JSON (Inertia `data-page`), with tile
type, finish, size, concept (look), colours and launch date. No prices here;
prices come from BuyRocell and are joined on product code.
"""
from __future__ import annotations

import html
import json
import re

from .base import RAW_DIR, fetch

SITEMAP = "https://rocell.com/sitemap.xml"
PRODUCT_RE = re.compile(r"<loc>(https://rocell\.com/en/tiles/product/[^<]+)</loc>")


def _record(url: str, page: str) -> dict | None:
    m = re.search(r'data-page="(.*?)"', page, re.S)
    if not m:
        return None
    try:
        p = json.loads(html.unescape(m.group(1)))["props"]["product"]
    except (KeyError, json.JSONDecodeError):
        return None
    if not p:
        return None
    g = lambda *path: _dig(p, path)
    return {
        "source": "rocell",
        "brand": "Rocell",
        "group": "V One",
        "product_id": f"rocell:{p.get('product_code') or p['id']}",
        "name": p.get("name_en", "").strip(),
        "url": url,
        "categories": " ".join(filter(None, [g("category", "name_en"), g("tile_type", "name_en")])),
        "attributes": {
            "size": g("size", "size") or "",
            "finish": g("finish_type", "title") or "",
            "type": g("tile_type", "name_en") or "",
            "collection": " ".join(filter(None, [g("concept", "name_en"), g("collection", "name_en")])),
            "colors": g("primary_color", "title") or "",
            "code": p.get("product_code") or "",
            "launched": (p.get("created_at") or "")[:10],
        },
        "description": (p.get("description_en") or "")[:600],
        "image": g("main_image", "url") or g("thumbnail_image", "url") or "",
        "image_hi": g("high_res_image", "url") or "",
        "list_price": None,
        "sell_price": None,
        "price_basis": None,
        "observed_on": None,
    }


def _dig(obj, path):
    for k in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def scrape(refresh: bool = False, limit: int | None = None) -> list[dict]:
    resp = fetch(SITEMAP, "rocell", refresh=refresh)
    if resp is None or not resp.ok:
        return []
    urls = sorted(set(PRODUCT_RE.findall(resp.text)))[:limit]
    rows = []
    for i, url in enumerate(urls, 1):
        r = fetch(url, "rocell", refresh=refresh)
        if r is not None and r.ok:
            rec = _record(url, r.text)
            if rec:
                rows.append(rec)
        if i % 100 == 0:
            print(f"  rocell: {i}/{len(urls)} pages, {len(rows)} tiles", flush=True)
    return rows


def parse_cached() -> list[dict]:
    rows = {}
    for meta_path in (RAW_DIR / "rocell").glob("*.json"):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if "/tiles/product/" not in meta["url"] or meta["status"] != 200:
            continue
        rec = _record(meta["url"], meta_path.with_suffix(".body").read_text(encoding="utf-8", errors="ignore"))
        if rec:
            rows[rec["product_id"]] = rec
    return list(rows.values())
