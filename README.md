# TileIQ — Vallibel One tile intelligence

Market intelligence for Rocell and Lanka Tiles, built **entirely from public web pages**. It scrapes
the Sri Lankan and global tile market — images, specifications, designs and prices — maps every
product to one standard record, audits every price before using it, and publishes a fast static
interface.

**No demo data. No estimates presented as facts. Every price links to the page it came from.**

```bash
python -m pip install -r requirements.txt
python -m tileiq.pipeline            # build from cached pages
python -m http.server 8765 --directory site
```

Open `http://localhost:8765`. To put it online for free, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## The interface

| Page | What it shows |
|---|---|
| **Overview** | Range by brand, where price is leaking, global design demand, newest launches |
| **Catalogue** | Every tracked tile with its photograph, filterable and searchable instantly |
| **Head to head** | One specification across every brand that publishes it |
| **Pricing** | Published discounts, price vs specification value, price vs published competitors |
| **Marketing** | Audience, content output and website features versus global leaders |
| **Global demand** | What the world sells and launches versus our range |
| **Gaps** | Our share of the market's range, and the specifications we don't cover |
| **Price audit** | How every price's unit was established, automated checks, live re-verification |
| **Sources** | Every source, what it gives, and what was checked and excluded |

It is a static site: about 60 KB of code, 1.7 MB of data, 3,000 thumbnails. No server, no database,
no per-query cost, and nothing to wait for.

## The price audit

This is the part that keeps the numbers honest. Tile sites publish a number and rarely say *per
what* — and guessing that unit is the easiest way for a comparison engine to lie.

1. **If the page states the unit**, use it.
2. **Otherwise infer it from that source's own data**: regress log(price) on log(tile area). A slope
   near 1 means price tracks the tile, so it is per piece; near 0 means it is already per sqm. The
   slope, R² and sample size are recorded and shown.
3. **Sanity gate**: whichever way the evidence points, the resulting per-sqm price must be plausible
   (LKR 1,500–80,000/sqm). If it isn't, the other reading is used, or the price is marked unresolved.
4. **Unresolved prices are excluded** from every comparison and reported as such — never converted,
   never quietly used.

Worked examples from the current build:

- **Rocell / BuyRocell** → per piece, from a slope of 1.39 (R² 0.98) across 199 products in 8 formats.
- **Mascons** → per piece, because reading it as per-sqm would imply LKR 1,050/sqm, below any real tile.

On top of that: automated checks for impossible prices, missing sizes, stale observations, duplicates
and peer-group outliers; plus a **live spot check** that re-fetches random source pages and confirms
the stored price still matches (currently 6/6).

## Sources

| Source | What we take | Prices |
|---|---|---|
| rocell.com | 801 Rocell tiles: type, finish, size, design family, colour, launch date, images | — |
| buyrocell.com | Live Rocell list and offer prices | ✔ audited |
| lankatiles.com | 321 Lanka Tiles products with images | none published |
| macktiles.com | 565 Macktiles products with images | none published |
| mascons.com | Importer/retailer range | ✔ audited |
| tileshop.com | 1,803 global designs with the retailer's own **best-seller / new-arrival flags**, full spec sheets, images | US retail, comparison only |

**Checked and excluded, with reasons:** ikman.lk and Daraz (prices exist but no listing states its
unit), davinciceramics.com (publishes neither prices nor sizes), naveen.lk (placeholder page),
stockpile.lk (no usable product feed).

A real finding in itself: **only two Sri Lankan tile sellers publish prices online.** Broad
competitor price coverage needs field capture by the sales team — real observed prices, which the
audit will treat the same way as any other source.

## Marketing benchmark

The same discipline applied to promotion: only what brands publish openly.

- **Audience** — LinkedIn followers and YouTube subscribers/lifetime views, the two channels that show
  their numbers without a login.
- **Content** — how many blog, inspiration and project pages each site carries, and how fresh they are.
- **Experience** — which digital features a site actually offers (online store, room visualiser,
  catalogue download, appointment booking, sample ordering, trade programme…), detected across every
  site a brand owns.
- **Promotion** — how heavily each brand discounts in public, measured from the audited prices.

Current read: **Kajaria reaches 588,000 followers and 229M lifetime video views; Rocell reaches 26,000
and 14M** — a 23× audience gap. On content we are ahead: **Rocell publishes 262 editorial pages against
a global-leader median of 108.**

Facebook, Instagram and TikTok require a login to read follower counts, so they are excluded rather
than estimated — and a site that blocks automated reads is reported as "not readable", never as zero.

## Global demand signal

The Tile Shop publishes its own `IsBestSeller`, `IsNewArrival` and `IsClearance` flags. That is
revealed demand, not a guess. Current read: **wood-look is roughly 2× over-represented among global
best sellers and ~3.6× among new launches, while it is about 8% of our range against 27% globally.**
US prices are shown for relative comparison only — never as a Sri Lankan price target.

## Keeping it current

| Command | Re-fetches | Time |
|---|---|---|
| `python -m tileiq.pipeline` | nothing; rebuilds from cache | ~2 min |
| `python -m tileiq.pipeline --refresh-prices` | only sources that publish prices | ~10 min |
| `python -m tileiq.pipeline --refresh` | every catalogue and the global benchmark | 2–3 hrs |

Scheduling for free (Windows Task Scheduler or GitHub Actions) is in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Rebuilds cache-bust the site automatically.

## Adding SAP later

Phase 1 deliberately needs no internal data. When SAP is connected, the discount-guardrail models
switch on automatically — drop the exports in `data/input/` with columns mapped in
`config/sap_columns.yaml`.

- [docs/SAP_DATA_REQUIREMENTS.md](docs/SAP_DATA_REQUIREMENTS.md) — field-level specification
- [docs/PHASE2.md](docs/PHASE2.md) — the sales forecast and "what to sell, how to sell it" engine,
  including the public Sri Lankan construction indicators that drive tile demand

## Known limitations

- **Macktiles design attribution** is inferred: their names are codes and the site's only design
  attribute is "Nature". Image classification or their PDF catalogue would fix it.
- **Competitor price coverage is thin** (see Sources). The 12 SKUs with a comparable published price
  compare premium Rocell tiles against a budget importer, so read that ratio as a spread, not a
  like-for-like premium.
- **"Specification value"** comes from a model fitted on our own audited prices, so it measures
  internal consistency, not an external market price. It is labelled that way in the interface.
- **Lanka Tiles publishes no prices**, so it appears in range and design analysis but not pricing.

## Layout

```
tileiq/scrapers/   polite cached fetching per source (rocell, buyrocell, woocommerce, mascons, tileshop)
tileiq/taxonomy.py standard tile record: size / body / finish / look / application
tileiq/audit.py    price unit resolution, automated checks, live spot check
tileiq/engine.py   fair-price model, comparables, price position, gaps, landed-cost calculator
tileiq/market.py   global demand trends and discount intelligence
tileiq/export_site.py  builds the static site payload
site/              the interface
docs/              deployment, SAP requirements, Phase 2
```

Scraping conduct: public pages only, robots.txt respected, one request per second, every response
cached, every price stored with its source URL, raw text and observation date.
