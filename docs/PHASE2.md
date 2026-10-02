# Phase 2 — from a market mirror to a "what to sell, how to sell it" engine

Phase 1 answers *what the market offers and what it charges*. It is built only on public data, so it
can describe the outside world but knows nothing about our own trade: what we actually sold, at what
realised price, to whom, and what we failed to sell.

Phase 2 adds that, and with it three capabilities that are impossible today.

---

## The three things Phase 2 makes possible

### 1. A sales forecast that is actually about tiles

Not a generic time-series on total revenue. Tile demand is driven by construction activity, and the
useful forecast is **by product family** (size × body × finish × look), because that is what
production and import planning consume.

**Model shape.** A hierarchical forecast: total → brand → family → SKU, reconciled so the parts sum
to the whole. SKU-level history is too sparse and too affected by introductions and discontinuations
to forecast directly; family level is stable, and SKU shares within a family move slowly.

**Internal drivers** (from SAP): last 24–36 months of volume by family and channel, price and
discount history, promotion periods, new-listing and discontinuation dates, stock-outs (critical —
a month with no stock is not a month with no demand).

**External drivers**, all publicly available in Sri Lanka:

| Driver | Why it matters | Source |
|---|---|---|
| Cement production and sales volumes | The single best construction proxy; tiles follow cement by roughly 6–9 months | CBSL monthly indicators |
| Building material price index / construction cost index | Affordability and project timing | Department of Census & Statistics |
| Construction sector GDP and activity index | Overall demand cycle | CBSL quarterly |
| Building approvals / plan submissions | Leads floor tile demand by about 2–4 quarters | Municipal councils, UDA |
| Housing loans and interest rates (AWPLR) | Retail renovation demand is credit-sensitive | CBSL weekly |
| Worker remittances | A major funder of home building and renovation in Sri Lanka | CBSL monthly |
| Tourism arrivals and hotel project pipeline | Drives commercial and large-format demand | SLTDA monthly |
| USD/LKR and import duty changes | Shifts the import-vs-local balance | CBSL, Customs |
| Tile import volumes under HS 6907 | Direct measure of competing supply | Sri Lanka Customs / trade data |
| Monsoon and construction seasonality | Concrete and tiling slow in heavy rain | Met Department |
| Festive and new-year cycles | Retail renovation peaks before April | calendar |

**Approach.** Start simple and measurable: a gradient-boosted regression per family on lagged
volume, price, discount, stock availability and the external drivers above, with explicit lag
selection (cement at 6–9 months, approvals at 2–4 quarters). Compare against a seasonal-naive
baseline on a rolling backtest — if it cannot beat "same month last year, adjusted for trend", it
does not ship. Report a prediction interval, never a single number, and report *which drivers moved
the forecast* so a planner can argue with it.

**Honest expectation:** with 24 months of history, expect a usable family-level forecast at monthly
granularity with meaningful error bars. Anyone promising SKU-level monthly accuracy from this data
is selling something.

### 2. "What to sell" — the assortment and launch engine

Today the gap map says what the market offers that we don't. With internal data it becomes a ranked
investment case:

- **Demand evidence**: lost quotes marked "not available", stock-out periods, sample requests that
  never converted, search terms on our own site.
- **Substitution**: when a customer could not get X, what did they buy instead, and at what margin?
  This is what decides whether a gap is worth filling or is already covered by a substitute.
- **Cannibalisation**: a new 600×1200 marble matte will take share from existing 600×1200 marble.
  Net gain, not gross, is the number that matters.
- **Profitability**: gap volume × achievable price × contribution margin, minus the cost to produce
  or import, with the landed-cost model already built for the import route.
- **Global design lead**: the launch index from the global benchmark, which today tells us wood-look
  is over-represented among global best sellers while thin in our range.

Output: a ranked list of specifications to add, each with expected volume, price, margin, and the
evidence behind it.

### 3. "How to sell it" — the deal and channel engine

- **Win-probability model** on quote outcomes: how the chance of winning moves with price, discount,
  customer type, order size and competitor presence.
- **Margin-optimal discount ceilings** per channel and customer segment (the mechanism is already
  built; it needs real quote data to be true).
- **Next-best-product** for a customer: given what this dealer or contractor buys, what else moves at
  good margin for similar customers.
- **Churn and share-of-wallet**: dealers whose order frequency or mix is deteriorating, before they
  leave.
- **Price-pack architecture**: which sizes and grades should exist at which price points, so the range
  ladders properly instead of competing with itself.

---

## Data needed for Phase 2

Everything in `SAP_DATA_REQUIREMENTS.md` remains the foundation. On top of it, Phase 2 specifically needs:

### From SAP / internal systems

| Data | Used by | Why it is essential |
|---|---|---|
| Monthly volume by SKU and family, 24–36 months | Forecast | The dependent variable |
| **Stock-out and availability history** | Forecast, gaps | Separates "no demand" from "no supply"; without it the forecast learns our supply limits, not the market's demand |
| Promotion calendar (what was discounted, when, how deep) | Forecast, pricing | Otherwise the model reads a promo spike as underlying demand |
| New listing and discontinuation dates | Forecast, cannibalisation | Prevents phantom "declines" when a SKU was simply withdrawn |
| Quote outcomes with rejection reasons | Win model, gaps | The only record of what we lost and why |
| Customer master with segment and region | All three | Projects behave nothing like showroom retail |
| Standard cost per SKU | Assortment, pricing | No margin, no investment case |
| Production capacity and changeover constraints by line | Assortment | A gap we cannot make is a sourcing decision, not a production one |
| Import landed costs actually paid | Assortment | Replaces the modelled estimate with fact |
| Sample issues and showroom enquiries | Gaps, forecast | Early demand signal, 1–3 months ahead of orders |

### From public sources (we can add these without anyone's permission)

The external drivers table above. Practically: CBSL publishes monthly indicators, DCS publishes the
construction cost index, SLTDA publishes arrivals, Customs publishes trade data. These are
scrapeable on the same cadence as the existing sources, and I would add them in Phase 2 as
`tileiq/scrapers/macro.py` so the forecast's drivers refresh automatically alongside prices.

### From the field (cheap, high value)

- Competitor prices with a location, captured by the sales team — the one thing that would most
  improve Phase 1 today, since only two Sri Lankan sellers publish prices online.
- Won/lost reasons on project tenders, including the price that won.

---

## Sequencing

| Stage | Needs | Delivers |
|---|---|---|
| **2a** | SAP billing + material master + cost | Real price realisation, margin by SKU, true discount leakage |
| **2b** | Quote outcomes | Win model, defensible discount ceilings |
| **2c** | Stock-outs + macro drivers | Family-level demand forecast with drivers |
| **2d** | 2a–2c combined | Assortment investment cases, next-best-product, channel strategy |

2a alone changes the pricing conversation, and it is the extract with the fewest dependencies. I
would not attempt the forecast (2c) before stock-out history exists — without it the model is
trained on our own supply constraints and will confidently under-forecast exactly the products worth
adding.
