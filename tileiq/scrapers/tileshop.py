"""Global design benchmark: The Tile Shop (US).

Why this source: every product page embeds a `productData` block with the full
spec sheet (material, body type, finish, colour, thickness, rectified edge,
shade variation, face count), a price with its coverage, an image, and two
demand flags the retailer sets itself:

    IsBestSeller  - what is actually selling
    IsNewArrival  - what the market is launching
    IsClearance   - what is being cleared out

Those flags are the closest thing to real demand data available publicly, and
they are what the global benchmark is built on. Prices are US retail, so they
are used for relative comparison (which looks carry a premium), never as a
price target for Sri Lanka.
"""
from __future__ import annotations

import json
import re
from datetime import date

from .base import RAW_DIR, fetch

SITEMAP = "https://www.tileshop.com/sitemap.xml"
PRODUCT_RE = re.compile(r"<loc>(https://www\.tileshop\.com/products/[^<]+)</loc>")
# Accessories, tools and sample chips are not tiles.
SKIP = re.compile(r"sample|trim|bullnose|pencil|liner|grout|mortar|sealer|caulk|wedi|schluter|tool|"
                  r"blade|spacer|trowel|underlayment|accessor|threshold|corner|profile|adhesive|cleaner|"
                  r"membrane|shower-kit|niche|drain", re.I)
KEEP = re.compile(r"tile|mosaic|slab", re.I)


def product_urls(refresh: bool = False) -> list[str]:
    resp = fetch(SITEMAP, "tileshop", refresh=refresh)
    if resp is None or not resp.ok:
        return []
    # Match on the slug only - the domain itself contains "tile".
    urls = [u for u in PRODUCT_RE.findall(resp.text)
            if KEEP.search(u.rsplit("/products/", 1)[-1]) and not SKIP.search(u.rsplit("/products/", 1)[-1])]
    # A few sitemap entries carry unicode dashes that 404; skip them.
    # Skip malformed sitemap entries (unicode dashes, unencoded spaces) - they 404.
    return sorted({u for u in urls if u.isascii() and " " not in u})


def _record(url: str, page: str) -> dict | None:
    i = page.find('"productData":')
    if i < 0:
        return None
    try:
        d, _ = json.JSONDecoder().raw_decode(page[i + len('"productData":'):])
    except json.JSONDecodeError:
        return None
    if not d.get("ProductName"):
        return None

    # The spec sheet lands under "Specifications" on most pages and "Attributes"
    # on others; both are {group: [{Key, Value}, ...]}.
    spec = {}
    for block in (d.get("Specifications"), d.get("Attributes")):
        if not isinstance(block, dict):
            continue
        for group in block.values():
            for kv in group or []:
                spec[kv.get("Key", "").replace("PDPInfo_", "")] = kv.get("Value", "")

    # Price per sqft -> per sqm. CV = coverage (box), EA = each.
    price, coverage = d.get("Price") or 0, d.get("CoveragePerBox") or 0
    usd_sqm = round(price / coverage * 10.7639, 2) if price and coverage else None

    if not (spec.get("ActualSize") or spec.get("ApproximateSize") or d.get("ActualSizeIN")):
        return None  # tools and accessories carry no tile dimensions

    return {
        "source": "tileshop",
        "brand": "Global - The Tile Shop (US)",
        "group": "Global",
        "product_id": f"tileshop:{d.get('ProductCode')}",
        "name": d["ProductName"].split(" - ")[0].strip(),
        "url": url,
        "categories": " ".join(filter(None, [spec.get("MaterialType", ""), spec.get("BodyType", "")])),
        "attributes": {
            "size": spec.get("ActualSize") or spec.get("ApproximateSize") or d.get("ActualSizeIN", ""),
            "finish": spec.get("Finish", ""),
            "type": " ".join(filter(None, [spec.get("MaterialType", ""), spec.get("BodyType", "")])),
            "collection": spec.get("Collection", ""),
            "colors": spec.get("Color", ""),
            "thickness": spec.get("Thickness", ""),
            "rectified": "yes" if "rectif" in spec.get("EdgeType", "").lower() else "",
            "shade_variation": spec.get("ShadeVariation", ""),
            "faces": spec.get("Faces", ""),
            "application": spec.get("Applications", ""),
            "room": spec.get("Room", ""),
            "style": spec.get("Style", ""),
            "origin": spec.get("CountryOfOrigin", ""),
        },
        "description": (d.get("ProductDescription") or "")[:400],
        "image": (d.get("ImageLink") or "").split("?")[0],
        # US retail price, kept in USD; never mixed into the Sri Lanka benchmark.
        "list_price": None,
        "sell_price": None,
        "price_basis": None,
        "usd_per_sqm": usd_sqm,
        "is_bestseller": bool(d.get("IsBestSeller")),
        "is_new_arrival": bool(d.get("IsNewArrival")),
        "is_clearance": bool(d.get("IsClearance")),
        "observed_on": date.today().isoformat(),
    }


def scrape(refresh: bool = False, limit: int | None = None) -> list[dict]:
    urls = product_urls(refresh)[:limit]
    rows = []
    for i, url in enumerate(urls, 1):
        r = fetch(url, "tileshop", refresh=refresh)
        if r is not None and r.ok:
            rec = _record(url, r.text)
            if rec:
                rows.append(rec)
        if i % 100 == 0:
            print(f"  tileshop: {i}/{len(urls)} pages, {len(rows)} tiles", flush=True)
    return rows


def parse_cached() -> list[dict]:
    rows = {}
    for meta_path in (RAW_DIR / "tileshop").glob("*.json"):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if "/products/" not in meta["url"] or meta["status"] != 200:
            continue
        rec = _record(meta["url"], meta_path.with_suffix(".body").read_text(encoding="utf-8", errors="ignore"))
        if rec:
            rows[rec["product_id"]] = rec
    return list(rows.values())
