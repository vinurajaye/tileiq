"""Catalogue scraper for WooCommerce sites via the public Store API.

Macktiles and Lanka Tiles both run WooCommerce and expose
/wp-json/wc/store/v1/products, which returns structured product attributes
(size, finish, surface, application, collection). Neither publishes prices
there, so these rows feed assortment coverage and matching, not price.
"""
from __future__ import annotations

import html
import re
from datetime import date

from .base import fetch

SITES = {
    "macktiles": {"brand": "Macktiles", "group": "Competitor", "base": "https://macktiles.com"},
    "lankatiles": {"brand": "Lanka Tiles", "group": "V One", "base": "https://www.lankatiles.com"},
}


def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def scrape(site: str, refresh: bool = False) -> list[dict]:
    cfg = SITES[site]
    rows, page = [], 1
    while True:
        url = f"{cfg['base']}/wp-json/wc/store/v1/products?per_page=100&page={page}"
        resp = fetch(url, site, refresh=refresh)
        if resp is None or resp.status_code != 200:
            break
        items = resp.json()
        if not items:
            break
        for p in items:
            attrs = {a["name"].strip().lower(): ", ".join(t["name"] for t in a.get("terms", []))
                     for a in p.get("attributes", [])}
            price = int(p["prices"].get("price") or 0) / 10 ** p["prices"].get("currency_minor_unit", 2)
            rows.append({
                "source": site,
                "brand": cfg["brand"],
                "group": cfg["group"],
                "product_id": f"{site}:{p['id']}",
                "name": _clean(p["name"]),
                "url": p["permalink"],
                "categories": ", ".join(c["name"] for c in p.get("categories", [])),
                "attributes": attrs,
                "description": _clean(p.get("short_description", "") + " " + p.get("description", ""))[:600],
                "image": (p.get("images") or [{}])[0].get("src", ""),
                "list_price": price or None,
                "sell_price": None,
                "price_basis": None,
                "observed_on": date.today().isoformat(),
            })
        total_pages = int(resp.headers.get("X-WP-TotalPages", page))
        print(f"  {site}: page {page}/{total_pages} ({len(rows)} products)")
        if page >= total_pages:
            break
        page += 1
    return rows
