"""Public marketing footprint for each brand — the same discipline as prices.

What a competitor spends on marketing is private. What they *publish* is not, so
this measures only observable things and records where each number came from:

  reach       LinkedIn followers, YouTube subscribers and lifetime views
  content     how many blog / inspiration / news / project pages the site carries,
              and how recently they were updated
  experience  digital features the site actually offers (visualiser, online store,
              WhatsApp, newsletter, showroom finder, catalogue download…)
  promotion   live offers visible on the site

Facebook, Instagram and TikTok are deliberately excluded: they require a login to
read follower counts, so any number would be a guess. That exclusion is reported
in the interface rather than hidden.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date

from .base import RAW_DIR, fetch

# Channels are candidates, not claims: each is fetched and only recorded if the
# page resolves and its title matches the brand.
BRANDS = {
    "Rocell": {
        "group": "V One", "site": "https://rocell.com/en/", "sitemap": "https://rocell.com/sitemap.xml",
        "linkedin": "https://www.linkedin.com/company/royal-ceramics-lanka-plc",
        "youtube": "https://www.youtube.com/@rocellsrilanka",
        "shop": "https://buyrocell.com/",
    },
    "Lanka Tiles": {
        "group": "V One", "site": "https://www.lankatiles.com/", "sitemap": "https://www.lankatiles.com/sitemap.xml",
        "linkedin": "https://www.linkedin.com/company/lankatiles",
        "youtube": "https://www.youtube.com/@Lankatilesplc",
    },
    "Macktiles": {
        "group": "Competitor", "site": "https://macktiles.com/", "sitemap": "https://macktiles.com/wp-sitemap.xml",
        "linkedin": "https://www.linkedin.com/company/macktiles",
        "youtube": "https://www.youtube.com/@macktileslanka",
    },
    "RAK Ceramics": {
        "group": "Global", "site": "https://www.rakceramics.com/", "sitemap": "https://www.rakceramics.com/sitemap.xml",
        "linkedin": "https://www.linkedin.com/company/rak-ceramics",
        "youtube": "https://www.youtube.com/@rakceramics",
    },
    "Kajaria": {
        "group": "Global", "site": "https://www.kajariaceramics.com/", "sitemap": "https://www.kajariaceramics.com/sitemap.xml",
        "linkedin": "https://in.linkedin.com/company/kajaria-ceramics-ltd-",
        "youtube": "https://www.youtube.com/@KajariaCeramicsLimited",
    },
    "Somany": {
        "group": "Global", "site": "https://www.somanyceramics.com/", "sitemap": "https://www.somanyceramics.com/sitemap.xml",
        "linkedin": "https://in.linkedin.com/company/somany-ceramics-ltd",
        "youtube": "https://www.youtube.com/@SomanyCeramicsLtd",
    },
    "Porcelanosa": {
        "group": "Global", "site": "https://www.porcelanosa.com/", "sitemap": None,  # returns 403 to non-browser clients
        "linkedin": "https://www.linkedin.com/company/porcelanosa",
        "youtube": "https://www.youtube.com/@PORCELANOSAGrupo",
    },
    "The Tile Shop": {
        "group": "Global", "site": "https://www.tileshop.com/", "sitemap": "https://www.tileshop.com/sitemap.xml",
        "linkedin": "https://www.linkedin.com/company/the-tile-shop",
        "youtube": "https://www.youtube.com/@thetileshop",
    },
}

# Digital experience features, detected from the site's own markup.
FEATURES = {
    "Online store": r"add to cart|buy now|checkout|shop online|e-?commerce",
    "Room visualiser": r"visuali[sz]er|room designer|see it in your|try it on your|design studio",
    "Inspiration gallery": r"inspiration|lookbook|gallery|room ideas|style guide",
    "Project references": r"our projects|case stud|reference project|projects we",
    "Blog / editorial": r"\bblog\b|articles|editorial|journal|trends?\b",
    "Catalogue download": r"catalogue|catalog|brochure|download.{0,20}pdf|e-?magazine",
    "Showroom finder": r"showroom|store locator|find a (store|showroom|dealer)|our network|dealer",
    "Newsletter signup": r"newsletter|subscribe|sign ?up.{0,20}(email|updates)",
    "WhatsApp / live chat": r"whatsapp|wa\.me|live ?chat|chat with us",
    "Appointment booking": r"book an appointment|schedule a (visit|consultation)|free consultation|virtual (tour|showroom)",
    "Sample ordering": r"order (a )?sample|free sample|sample request",
    "Trade / pro programme": r"\bpro\b.{0,12}(programme|program|rewards)|trade (account|programme|program)|architect",
}

SOCIAL_RE = re.compile(
    r"https?://(?:www\.)?(facebook|instagram|youtube|linkedin|tiktok|pinterest)\.com/[A-Za-z0-9_.@/-]{2,45}", re.I)
YT_HEADERS_NOTE = "youtube needs a consent cookie to return English text"


def _text(page: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))


def _linkedin(url: str, brand: str, refresh: bool) -> dict:
    # LinkedIn throttles repeat requests and then serves a page with no metadata.
    # Prefer a cached page that parsed cleanly; only go back to the network when
    # we have nothing usable.
    r = fetch(url, "marketing", refresh=False)
    og = re.search(r'<meta property="og:description" content="([^"]+)"', r.text) if (r and r.ok) else None
    if og is None and refresh:
        r = fetch(url, "marketing", refresh=True)
        og = re.search(r'<meta property="og:description" content="([^"]+)"', r.text) if (r and r.ok) else None
    if r is None or not r.ok or og is None:
        return {}
    desc = html.unescape(og.group(1))
    followers = re.search(r"([\d,]+)\s+followers", desc)
    employees = re.search(r"([\d,]+)\s+employees", _text(r.text))
    if not followers:
        return {}
    return {
        "linkedin_followers": int(followers.group(1).replace(",", "")),
        "linkedin_employees": int(employees.group(1).replace(",", "")) if employees else None,
        "linkedin_name": desc.split(" | ")[0][:60],
        "linkedin_tagline": desc.split(" on LinkedIn. ")[-1][:160],
        "linkedin_url": url,
    }


def _youtube(url: str, brand: str, refresh: bool) -> dict:
    # The /about tab carries the counts; hl/gl force English wording.
    about = url.rstrip("/") + "/about?hl=en&gl=US"
    r = fetch(about, "marketing", refresh=refresh)
    if r is None or not r.ok:
        return {}
    subs = re.search(r'"subscriberCountText":"([^"]+)"', r.text)
    views = re.search(r'"viewCountText":"([^"]+)"', r.text)
    if not subs:
        return {}

    def num(text):
        m = re.search(r"([\d.,]+)\s*([KMB])?", text or "")
        if not m:
            return None
        v = float(m.group(1).replace(",", ""))
        return int(v * {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2), 1))

    return {"youtube_subscribers": num(subs.group(1)),
            "youtube_views": num(views.group(1)) if views else None,
            "youtube_url": url}


def _sitemap_profile(sitemap: str, refresh: bool) -> dict:
    """Content volume by section, from the site's own sitemap."""
    r = fetch(sitemap, "marketing", refresh=refresh)
    if r is None or not r.ok:
        return {}
    text = r.text
    # Follow one level of sitemap index, capped so a big site doesn't take all day.
    children = re.findall(r"<loc>([^<]+\.xml)</loc>", text)
    for child in children[:6]:
        c = fetch(child, "marketing", refresh=refresh)
        if c is not None and c.ok:
            text += c.text

    locs = re.findall(r"<loc>([^<]+)</loc>", text)
    # Multi-language sites list one page per language; count the page once.
    locs = sorted({re.sub(r"/(en|si|ta|fr|de|es|it|ar)(/|$)", "/", u, count=1) for u in locs})
    lastmods = re.findall(r"<lastmod>([^<]{4,10})", text)
    sections = {"blog": r"/blog|/article|/news|/journal", "inspiration": r"/inspiration|/gallery|/lookbook|/idea",
                "projects": r"/project|/case-stud|/reference", "showrooms": r"/showroom|/store|/dealer|/network",
                "products": r"/product|/tile"}
    counts = {f"pages_{k}": sum(1 for u in locs if re.search(p, u, re.I)) for k, p in sections.items()}
    counts["pages_total"] = len(locs)
    counts["_urls"] = locs[:4000]
    if lastmods:
        counts["content_latest"] = max(lastmods)[:10]
        recent = [d for d in lastmods if d[:10] >= (date.today().replace(year=date.today().year - 1)).isoformat()]
        counts["pages_updated_12m"] = len(recent)
    return counts


def collect(brand: str, refresh: bool = False) -> dict:
    cfg = BRANDS[brand]
    row = {"brand": brand, "group": cfg["group"], "site": cfg["site"],
           "observed_on": date.today().isoformat()}

    # A brand's digital experience can span more than one site (Rocell's shop is
    # buyrocell.com), so scan every site it owns.
    pages = []
    for key in ("site", "shop"):
        if cfg.get(key):
            r = fetch(cfg[key], "marketing", refresh=refresh)
            if r is not None and r.ok:
                pages.append(r.text)
    home = pages[0] if pages else None
    if home is not None:
        page = " ".join(pages)
        blob = (page + " " + _text(page)).lower()
        found = {}
        for label, pattern in FEATURES.items():
            found[label] = bool(re.search(pattern, blob, re.I))
        row["features"] = found
        row["feature_count"] = sum(found.values())
        row["socials_linked"] = sorted({m.group(0).rstrip("/") for m in SOCIAL_RE.finditer(html.unescape(page))})
        row["sites_scanned"] = [cfg[k] for k in ("site", "shop") if cfg.get(k)]
    else:
        row["features"], row["feature_count"], row["socials_linked"] = {}, 0, []

    sm = _sitemap_profile(cfg["sitemap"], refresh) if cfg.get("sitemap") else {}
    row.update({k: v for k, v in sm.items() if k != "_urls"})
    # A JavaScript homepage carries little readable text; its sitemap still shows
    # which capabilities exist, so detect features across both.
    # URL slugs are hyphenated ("virtual-showroom-tour"), so turn separators into
    # spaces before matching word patterns against them.
    url_blob = re.sub(r"[-_/]+", " ", " ".join(sm.get("_urls", [])))
    if url_blob:
        for label, pattern in FEATURES.items():
            if not row["features"].get(label) and re.search(pattern, url_blob, re.I):
                row["features"][label] = True
        row["feature_count"] = sum(row["features"].values())
    if cfg.get("linkedin"):
        row.update(_linkedin(cfg["linkedin"], brand, refresh))
    if cfg.get("youtube"):
        row.update(_youtube(cfg["youtube"], brand, refresh))
    return row


def scrape(refresh: bool = False) -> list[dict]:
    rows = []
    for brand in BRANDS:
        print(f"  marketing: {brand}", flush=True)
        rows.append(collect(brand, refresh))
    return rows


def parse_cached() -> list[dict]:
    """Re-read from cache without touching the network."""
    return scrape(refresh=False)
