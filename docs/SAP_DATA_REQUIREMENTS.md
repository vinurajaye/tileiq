# SAP data needed to turn TileIQ into a real intelligence engine

The web layer already answers *"what does the market offer and what does it charge?"*.
SAP answers the three questions the web can never answer:

1. **What did customers actually pay us, and what did we give away to get it?**
2. **What did we fail to sell, and why?**
3. **What does each product actually cost us, so a price can be judged?**

Everything below is grouped by priority. **Tier 1 is enough to build every model in this document.**
Tiers 2 and 3 improve accuracy and unlock extra models.

---

## Tier 1 — required

### 1.1 Billing (invoice) line items — the single most important extract

Source: `VBRK` (header) joined to `VBRP` (items), with pricing conditions from `PRCD_ELEMENTS`
(S/4HANA) or `KONV` (ECC).

| Field | SAP | Why it matters |
|---|---|---|
| Billing document, item | `VBELN`, `POSNR` | Line identity |
| Billing date | `FKDAT` | Time series, seasonality, price-change effects |
| Billing type | `FKART` | Separate invoices from credit/debit memos and returns |
| Sales org / channel / division | `VKORG`, `VTWEG`, `SPART` | Rocell vs Lanka Tiles, retail vs dealer vs project |
| Sales office / branch, sales group | `VKBUR`, `VKGRP` | **Branch-level price and discount comparison** |
| Sold-to, ship-to | `KUNAG`, `KUNNR` | Customer behaviour, dealer vs end customer |
| Material | `MATNR` | Joins to the tile attributes |
| Billed quantity + unit | `FKIMG`, `VRKME` | Volume. **Must be convertible to m²** |
| Gross value | `KZWI1` | List price × quantity, before discounts |
| Discount value | `KZWI2`…`KZWI6` (procedure-specific) | *Confirm which subtotal holds discounts* |
| Net value | `NETWR` | What we actually charged |
| Cost | `WAVWR` / `VPRS` condition | Margin per line — without it, no margin optimisation |
| Currency | `WAERK` | Mixed-currency safety |
| Sales employee | `PERNR` or partner function `VE` | Who discounts, and how much |
| Order reference | `AUBEL`, `AUPOS` | Links the invoice back to the order and quote |

**Condition-level detail (important).** One `NETWR` is not enough. We need each pricing condition
per line — condition type, rate, value — so discounts can be separated by *kind*:

| Condition kind | Examples | Why separately |
|---|---|---|
| List price | `PR00` | The reference every index is built on |
| Customer/product discount | `K007`, `K004`, `ZD01`… | The discretionary discount we are trying to govern |
| Quantity/volume discount | `K029`, scale-based | Earned, not discretionary — must not be counted as leakage |
| Project / special price | `ZPRJ`, manual conditions | Deal-specific pricing; the biggest leakage source in tiles |
| Freight, handling | `KF00`, `ZFRT` | Not price; must be excluded from the price index |
| Rebates / year-end | `BO01`…`BO03` | Off-invoice cost of sale; changes true realised price |

Also send a **mapping table of condition types to those categories**. Nobody outside the pricing
team can reliably infer which `Z` condition is which.

**Volume:** 24–36 months, line level, no aggregation. For a business this size expect a few
hundred thousand lines, which is comfortable.

### 1.2 Material master + tile attributes

| Field | SAP | Use |
|---|---|---|
| Material, description | `MARA`, `MAKT` | Identity |
| Material group, hierarchy | `MATKL`, `PRDHA` | Category roll-ups |
| Base + alternate UoM, conversions | `MARM` | **Boxes/pieces → m².** Without this, prices are not comparable |
| Plant data, status | `MARC` | Active vs discontinued, made vs traded |
| Sales views | `MVKE` | Sales status, distribution-chain-specific blocks |
| Standard / moving cost | `MBEW` (`STPRS`, `VERPR`) | Margin floors, walk-away prices |
| **Classification** | `CAWN` / `AUSP` characteristics | Size, finish, body, colour, collection, grade, rectified, PEI, slip rating, faces |
| Tile grade | usually a characteristic or a suffix | Premium vs commercial grade changes price legitimately |

The classification is what lets us compare our SKUs to competitors on equal terms. If tile
attributes live only in a PIM or in the product code structure, send **the code structure key**
instead (e.g. what each segment of `RP.RSS.0074SQ.MA.0U` means).

### 1.3 Quotations and orders, with outcomes

Source: `VBAK`/`VBAP` (quotation type), plus document flow `VBFA` to see whether a quote became an
order.

| Field | SAP | Use |
|---|---|---|
| Quotation number, item, date | `VBELN`, `POSNR`, `AUDAT` | Identity, timing |
| Quoted material + quantity | `MATNR`, `KWMENG` | What was asked for |
| Quoted price + conditions | as above | The offer we made |
| Validity | `ANGDT`, `BNDDT` | Open vs expired |
| **Reason for rejection** | `ABGRU` | **Why we lost** — price, lead time, not available, competitor |
| Follow-on order | via `VBFA` | Won or lost |
| Customer, channel, branch | `KUNNR`, `VTWEG`, `VKBUR` | Segmenting the win curve |

**This is the highest-value dataset after billing.** Invoices only show deals we won; they tell us
nothing about the price at which we lose. Without quote outcomes, every discount guardrail is an
assumption. Two practical asks:
- Make `ABGRU` **mandatory** on rejected quote items, with a short, fixed list of reasons.
- Add a free-text or characteristic field for **"what the customer asked for that we don't make"**.
  That single field turns the assortment-gap engine from inference into measurement.

### 1.4 Customer master

`KNA1` (general), `KNVV` (sales area): customer group `KDGRP`, price group `KONDA`, price list
`PLTYP`, payment terms `ZTERM`, region/district, industry, and the account-group split between
dealer, project contractor, retail, and export. Needed to segment elasticity — projects behave
nothing like showroom walk-ins.

---

## Tier 2 — high value, add as soon as practical

| Data | Source | What it unlocks |
|---|---|---|
| **Stock on hand + movements** | `MARD`, `MCHB`, `MSEG` | Was a lost quote a price problem or a stock problem? Censors demand properly. |
| **Stock-out / ATP history** | ATP logs or daily stock snapshots | The difference between "no demand" and "no supply" — critical for the gap engine |
| Deliveries | `LIKP`, `LIPS` | Lead time as a competitive factor (a real loss reason in projects) |
| Returns & credit memos | `VBRK` (`FKART` = RE/G2) | True net revenue; product quality signals |
| Purchase/import records for traded goods | `EKKO`/`EKPO`, import costs | Real landed cost for imported lines, replacing the modelled estimate |
| Production cost breakdown | `CKIS` / costing runs | Which specs are cheap to make — matters for which gaps we fill |
| Rebate agreements | `KONA` | Off-invoice discount, often the largest hidden leak |
| Sales targets / budgets | COPA, `CE1xxxx` | Performance against plan, by branch and channel |

---

## Tier 3 — useful later

Showroom footfall and appointment logs, sample issues (a strong early demand signal — samples
requested but never ordered are lost deals), marketing spend by campaign, project pipeline / CRM
opportunities, export orders, competitor quotes collected by the sales team, and the field
price-capture form this system already provides.

---

## What each model needs

| Model | Target | Key inputs | Tier |
|---|---|---|---|
| **Win probability / price elasticity** | Quote won or lost | Price index vs market, discount %, channel, customer group, order size, lead time, stock at quote time | 1.3, 1.1, 1.4 |
| **Margin-optimal discount ceiling** | Expected margin | Win curve × (net price − cost) by segment | 1.1 cost, 1.3 |
| **Discount governance** | Required discount per deal | Predicted win at each price, competitor price, customer history | 1.1, 1.3 |
| **Price recommendation** | Target list price | Hedonic attributes, competitor set, elasticity, cost floor | 1.1, 1.2 |
| **Realised-price / leakage analytics** | Pocket price | Condition-level discounts, rebates, freight | 1.1 conditions, 2 rebates |
| **Assortment gap & new-product priority** | Unmet demand (m²) | Rejections for "not available", stock-outs, competitor range, global trends | 1.3, 2 stock |
| **Substitution / cannibalisation** | Switch behaviour | Basket and sequence of purchases by customer, attribute similarity | 1.1, 1.2 |
| **Branch / rep pricing behaviour** | Discount vs peers | Line-level discount by `VKBUR`, `PERNR`, controlled for mix | 1.1 |
| **Customer value & churn risk** | Repeat purchase | Order frequency, recency, mix, discount dependence | 1.1, 1.4 |

---

## Practical extraction notes

- **Format:** CSV or Parquet, one file per table, UTF-8, pipe or comma delimited. Excel is fine for
  a first sample but breaks on volume.
- **Method:** whichever is easiest for your BASIS team — `SE16N` export, a BW/BEx extract, CDS views
  over OData, or a read-only DB user. A nightly delta (`FKDAT >= yesterday`) keeps it current.
- **History:** 24–36 months. Less than 12 months makes seasonality and price-change effects
  unreliable.
- **Units:** every quantity convertible to m². Send `MARM` rather than pre-converting.
- **Privacy:** customer names can be hashed. We need the *identifier and attributes*, not the name.
  Sales employee can be a code. Nothing in the models needs a person's name.
- **Do not pre-aggregate.** Monthly totals by material destroy exactly the variation the models
  learn from.

---

## The minimum first pull

If the full list takes weeks to arrange, this alone moves the engine from demo to real:

1. `VBRP` + `VBRK` billing lines, 24 months, with `KZWI1`, discount subtotal, `NETWR`, `FKIMG`,
   `VRKME`, `MATNR`, `VKBUR`, `VTWEG`, `KUNAG`, `FKDAT`
2. Material master with **UoM conversion to m²** and the tile attribute classification
3. Standard cost per material
4. Quotation items with `ABGRU` and won/lost status

Items 1–3 make every pricing number real. Item 4 makes the discount guardrails real.
