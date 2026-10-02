"""Price scraper for BuyRocell (Rocell's own online store).

This is the only local tile site found so far that publishes prices. Category
listings render in JavaScript, so we crawl product pages instead: seed from the
sitemap and deals pages, then follow the "more from this collection" and
"related products" links that each product page carries.
"""
from __future__ import annotations

import html
import re
from collections import deque
from datetime import date

from .base import fetch

BASE = "https://buyrocell.com"
SEEDS = [f"{BASE}/sitemap.xml", f"{BASE}/today-deals/tiles", f"{BASE}/today-deals", BASE]
PRODUCT_RE = re.compile(r"https://buyrocell\.com/products/[a-z0-9\-]+")
MONEY_RE = re.compile(r"LKR\.\s*([\d,]+\.\d{2})")
# Words that mark a page as bathware/accessories rather than tiles.
NON_TILE = re.compile(r"closet|basin|faucet|mixer|shower|sink|seat cover|cistern|urinal|bidet|"
                      r"grout|mortar|adhesive|bundle|package|tap\b|pedestal|bath\b", re.I)


def _text(page: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return re.sub(r"\n\s*\n+", "\n", t)


def _parse_product(url: str, page: str) -> dict | None:
    text = _text(page)
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    name_m = re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S)
    name = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip() if name_m else (
        html.unescape(title.group(1)).split("|")[0].strip() if title else url.rsplit("/", 1)[-1])

    size = re.search(r"Size\s*:\s*([^\n]+)", text)
    finish = re.search(r"Finish Type\s*:\s*([^\n]+)", text)
    code = re.search(r"Product Code\s*:?\s*\n?\s*([A-Z0-9][A-Z0-9.\-]+)", text)
    if not size or NON_TILE.search(name):
        return None
    # The body type ("Glazed Vitrified Tile", "Wall Tile") sits on the line just
    # above "Finish Type"; towel racks and basins also carry a "Size :" line but not this.
    tile_type = re.search(r"\n([^\n]*(?:Tile|Porcelain|Vitrified|Slab|Mosaic)[^\n]*)\nFinish Type", text, re.I)
    if not tile_type:
        return None

    # Prices of the main product are the first two LKR amounts after the finish/size block.
    tail = text[text.find("Size :"):]
    prices = [float(p.replace(",", "")) for p in MONEY_RE.findall(tail[:400])]
    if not prices:
        return None
    list_price = prices[0]
    sell_price = prices[1] if len(prices) > 1 and prices[1] < prices[0] else prices[0]

    return {
        "source": "buyrocell",
        "brand": "Rocell",
        "group": "V One",
        "product_id": f"buyrocell:{url.rsplit('/', 1)[-1]}",
        "name": name,
        "url": url,
        "categories": tile_type.group(1).strip(),
        "attributes": {"size": size.group(1).strip(),
                       "finish": finish.group(1).strip() if finish else "",
                       "type": tile_type.group(1).strip(),
                       "code": code.group(1) if code else ""},
        "description": "",
        "image": (re.search(r'https://[a-z0-9]+\.cloudfront\.net/images/products/[^"\']+', page) or [""])[0],
        "list_price": list_price,
        "sell_price": sell_price,
        # The page states no unit. Recorded verbatim; tileiq/audit.py resolves the
        # unit from the data and records the evidence.
        "price_basis": "unit not stated by source",
        "price_raw_text": f"LKR. {list_price:,.2f}",
        "observed_on": date.today().isoformat(),
    }


def scrape(refresh: bool = False, max_pages: int = 800) -> list[dict]:
    queue, seen, rows = deque(), set(), {}
    for seed in SEEDS:
        resp = fetch(seed, "buyrocell", refresh=refresh)
        if resp is not None and resp.ok:
            for u in PRODUCT_RE.findall(resp.text):
                if u not in seen:
                    seen.add(u)
                    queue.append(u)
    fetched = 0
    while queue and fetched < max_pages:
        url = queue.popleft()
        resp = fetch(url, "buyrocell", refresh=refresh)
        fetched += 1
        if resp is None or not resp.ok:
            continue
        row = _parse_product(url, resp.text)
        if row:
            rows[row["product_id"]] = row
            # Only expand from tile pages, so we don't wander through bathware.
            for u in PRODUCT_RE.findall(resp.text):
                if u not in seen:
                    seen.add(u)
                    queue.append(u)
        if fetched % 50 == 0:
            print(f"  buyrocell: {fetched} pages fetched, {len(rows)} tiles, {len(queue)} queued")
    print(f"  buyrocell: done, {fetched} pages, {len(rows)} tiles")
    return list(rows.values())


def parse_cached() -> list[dict]:
    """Re-parse every cached product page without touching the network."""
    import json
    from .base import RAW_DIR
    rows = {}
    for meta_path in (RAW_DIR / "buyrocell").glob("*.json"):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if "/products/" not in meta["url"] or meta["status"] != 200:
            continue
        page = meta_path.with_suffix(".body").read_text(encoding="utf-8", errors="ignore")
        row = _parse_product(meta["url"], page)
        if row:
            rows[row["product_id"]] = row
    return list(rows.values())
