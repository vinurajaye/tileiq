"""Mascons Ltd (mascons.com) — Colombo importer/retailer that publishes prices.

WooCommerce, but without the Store API, so products come from the product
sitemap and are parsed out of the page. Prices are published in LKR with no
stated unit; the unit is inferred downstream (see tileiq/audit.py) from how
price moves with tile area, and the evidence is recorded rather than assumed.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date

from .base import RAW_DIR, fetch

SITEMAP = "https://www.mascons.com/product-sitemap.xml"
LOC_RE = re.compile(r"<loc>(https://www\.mascons\.com/product/[^<]+)</loc>")
PRICE_RE = re.compile(r"Rs\s*([\d,]+\.\d{2})")
TILE_CAT = re.compile(r"tile", re.I)
SKIP = re.compile(r"decking|d\.i\.y|roofing|ceiling|cement|fencing|door|sink|hollow|window|pipe|paint|ladder|lock|"
                  r"scaffold|safety net|wheel barrow|machinery|shade|steel|gutter|blade|adhesive|grout",
                  re.I)


def _text(page: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return re.sub(r"\n\s*\n+", "\n", t)


def _record(url: str, page: str) -> dict | None:
    text = _text(page)
    name_m = (re.search(r'<meta property="og:title" content="([^"]+)"', page)
              or re.search(r"<title>(.*?)</title>", page, re.S))
    name = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).split("-")[0].strip() if name_m else ""
    cat_m = re.search(r"Category:\s*\n([^\n]+)", text)
    category = cat_m.group(1).strip() if cat_m else ""
    if not TILE_CAT.search(category) or SKIP.search(category):
        return None

    # Description block holds the size and the tile type.
    desc_m = re.search(r"Description\n(.*?)(?:\n\s*Reviews|\Z)", text, re.S)
    desc = " ".join((desc_m.group(1) if desc_m else "").split())[:400]
    size_m = re.search(r"Size\s*:?\s*([\d]+\s*mm\s*[xX×]\s*[\d]+\s*mm|[\d]+\s*[xX×]\s*[\d]+\s*(?:mm|cm)?)", desc)

    # Cart totals ("Rs 0.00") appear before the product price; take the first non-zero.
    raw_prices = [m for m in PRICE_RE.finditer(text) if float(m.group(1).replace(",", "")) > 0]
    if not raw_prices:
        return None
    price = float(raw_prices[0].group(1).replace(",", ""))
    raw_text = re.sub(r"\s+", " ", raw_prices[0].group(0))

    sku_m = re.search(r"SKU:\s*\n([^\n]+)", text)
    # og:image is the product shot; the inline <img> fallback is often the site logo.
    img_m = re.search(r'<meta property="og:image" content="([^"]+)"', page)
    image = img_m.group(1) if img_m else ""
    if "logo" in image.lower():
        alt = re.search(r'(https://www\.mascons\.com/wp-content/uploads/[^"\']+?\.(?:jpg|jpeg|png|webp))', page)
        image = alt.group(1) if alt and "logo" not in alt.group(1).lower() else ""

    return {
        "source": "mascons",
        "brand": "Mascons (importer)",
        "group": "Competitor",
        "product_id": f"mascons:{sku_m.group(1).strip() if sku_m else url.rstrip('/').rsplit('/', 1)[-1]}",
        "name": name,
        "url": url,
        "categories": category,
        "attributes": {"size": size_m.group(1) if size_m else "", "finish": "", "type": desc,
                       "code": sku_m.group(1).strip() if sku_m else ""},
        "description": desc,
        "image": image,
        "list_price": price,
        "sell_price": price,
        # No unit is stated on the page. Recorded verbatim; resolved by audit.infer_unit().
        "price_basis": "unit not stated by source",
        "price_raw_text": raw_text,
        "observed_on": date.today().isoformat(),
    }


def product_urls(refresh: bool = False) -> list[str]:
    resp = fetch(SITEMAP, "mascons", refresh=refresh)
    if resp is None or not resp.ok:
        return []
    return sorted(set(LOC_RE.findall(resp.text)))


def scrape(refresh: bool = False, limit: int | None = None) -> list[dict]:
    urls = product_urls(refresh)[:limit]
    rows = []
    for i, url in enumerate(urls, 1):
        r = fetch(url, "mascons", refresh=refresh)
        if r is not None and r.ok:
            rec = _record(url, r.text)
            if rec:
                rows.append(rec)
        if i % 100 == 0:
            print(f"  mascons: {i}/{len(urls)} pages, {len(rows)} tiles", flush=True)
    print(f"  mascons: done, {len(rows)} tiles with prices", flush=True)
    return rows


def parse_cached() -> list[dict]:
    rows = {}
    for meta_path in (RAW_DIR / "mascons").glob("*.json"):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if "/product/" not in meta["url"] or meta["status"] != 200:
            continue
        rec = _record(meta["url"], meta_path.with_suffix(".body").read_text(encoding="utf-8", errors="ignore"))
        if rec:
            rows[rec["product_id"]] = rec
    return list(rows.values())
