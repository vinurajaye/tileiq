"""Price audit: prove every price, or refuse to use it.

Tile sites publish a number and rarely say *per what*. Guessing the unit is the
single biggest way a comparison engine can lie. So nothing here guesses
silently:

1. **Stated unit wins.** If the page says "per sqm" / "per box" / "each", use it.
2. **Otherwise infer it from the source's own data** by regressing log(price) on
   log(tile area). A slope near 1 means the price follows the tile, so it is
   per piece; a slope near 0 means it is already per sqm. The slope, R² and
   sample size are stored as the evidence.
3. **If neither resolves it**, the price is marked unresolved and is excluded
   from every comparison. It is shown in the UI as "unit unverified", never
   converted.

On top of that, `run_checks()` looks for prices that are impossible, stale,
duplicated or inconsistent, and `spot_check()` re-fetches live pages to confirm
what we stored is still what the site shows.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

# Plausible Sri Lanka retail range, LKR per sqm. The floor is deliberately well
# below the cheapest real tile (~LKR 2,000/sqm, about Rs 185/sqft) so it only
# rejects readings that cannot be a tile price at all; the ceiling clears the
# most expensive imported slabs. Anything outside is flagged, never silently used.
LKR_SQM_MIN, LKR_SQM_MAX = 1_500.0, 80_000.0
STALE_DAYS = 45

STATED_UNIT = [
    ("per_sqm", r"per\s*(?:sq\.?\s*m|m2|m²|sqm|square\s*met(?:er|re))|/\s*(?:sqm|m2|m²)"),
    ("per_sqft", r"per\s*(?:sq\.?\s*ft|sqft|square\s*f(?:oot|eet))|/\s*sq\.?\s*ft"),
    ("per_box", r"per\s*(?:box|carton|ctn)|/\s*box|price\s*per\s*box"),
    ("per_piece", r"per\s*(?:piece|pc|pcs|tile|nos?\b)|each\b|/\s*(?:pc|piece)"),
]


def stated_unit(*texts: str) -> str | None:
    blob = " ".join(str(t) for t in texts if t)
    for unit, pattern in STATED_UNIT:
        if re.search(pattern, blob, re.I):
            return unit
    return None


# ---------------------------------------------------------------- unit inference
def infer_source_unit(df: pd.DataFrame) -> dict:
    """Infer a source's pricing unit from how price scales with tile area."""
    d = df.dropna(subset=["list_price", "size_short", "size_long"]).copy()
    d = d[(d["list_price"] > 0)]
    if len(d) < 8:
        return {"unit": None, "method": "insufficient data", "n": len(d), "slope": None, "r2": None}

    area = (d["size_short"] * d["size_long"]) / 1e6
    if area.nunique() < 3:
        # Only one or two formats: decide by which reading lands in a sane range.
        med_area = float(area.median())
        as_sqm = float(d["list_price"].median())
        as_piece = as_sqm / med_area if med_area else np.nan
        sqm_ok = LKR_SQM_MIN <= as_sqm <= LKR_SQM_MAX
        piece_ok = LKR_SQM_MIN <= as_piece <= LKR_SQM_MAX
        if piece_ok and not sqm_ok:
            unit, why = "per_piece", f"as-sqm would be LKR {as_sqm:,.0f}/sqm (outside plausible range)"
        elif sqm_ok and not piece_ok:
            unit, why = "per_sqm", f"as-piece would be LKR {as_piece:,.0f}/sqm (outside plausible range)"
        else:
            unit, why = None, "both readings plausible; too few formats to separate them"
        return {"unit": unit, "method": f"range test ({why})", "n": len(d), "slope": None, "r2": None,
                "formats": int(area.nunique())}

    x, y = np.log(area.values), np.log(d["list_price"].values)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0

    # The slope is only evidence when the fit is decent. A weak or negative slope
    # is noise, not proof of per-sqm pricing.
    if r2 >= 0.5 and slope >= 0.7:
        unit, method = "per_piece", "log-log slope of price vs tile area"
    elif r2 >= 0.5 and 0 <= slope <= 0.35:
        unit, method = "per_sqm", "log-log slope of price vs tile area"
    else:
        unit, method = None, f"slope {slope:.2f} with R²={r2:.2f} is not conclusive"

    # Whichever way the slope pointed, the resulting per-sqm price has to be
    # plausible. If it isn't, fall back to the reading that is.
    med_area, med_price = float(area.median()), float(d["list_price"].median())
    implied = {"per_sqm": med_price, "per_piece": med_price / med_area if med_area else np.nan}
    if unit and not (LKR_SQM_MIN <= implied[unit] <= LKR_SQM_MAX):
        other = "per_piece" if unit == "per_sqm" else "per_sqm"
        if LKR_SQM_MIN <= implied[other] <= LKR_SQM_MAX:
            unit, method = other, (f"{method}, overridden: as-{'sqm' if other == 'per_piece' else 'piece'} "
                                   f"implies LKR {implied['per_sqm' if other == 'per_piece' else 'per_piece']:,.0f}"
                                   f"/sqm, outside the plausible range")
        else:
            unit, method = None, "neither reading lands in a plausible per-sqm range"
    elif unit is None:
        sqm_ok = LKR_SQM_MIN <= implied["per_sqm"] <= LKR_SQM_MAX
        piece_ok = LKR_SQM_MIN <= implied["per_piece"] <= LKR_SQM_MAX
        if piece_ok and not sqm_ok:
            unit, method = "per_piece", f"{method}; range test: as-sqm would be LKR {implied['per_sqm']:,.0f}/sqm"
        elif sqm_ok and not piece_ok:
            unit, method = "per_sqm", f"{method}; range test: as-piece would be LKR {implied['per_piece']:,.0f}/sqm"

    return {"unit": unit, "method": method, "n": len(d),
            "slope": round(float(slope), 2), "r2": round(float(r2), 2), "formats": int(area.nunique())}


def resolve_prices(cat: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach price_per_sqm + the evidence behind the unit, per source.

    Returns (catalogue with resolved prices, one evidence row per source).
    """
    cat = cat.copy()
    for col in ("price_per_sqm", "list_per_sqm", "price_unit", "unit_basis", "unit_evidence",
                "price_confidence"):
        cat[col] = None

    evidence = []
    for source, block in cat.groupby("source"):
        if block["list_price"].notna().sum() == 0:
            continue
        # 1. a unit stated on the page itself. Only text that came from the page
        #    counts - never our own scraper notes, or the check is circular.
        stated = block.apply(lambda r: stated_unit(r.get("price_raw_text"), r.get("raw_text")), axis=1)
        inferred = infer_source_unit(block)
        evidence.append({"source": source, "priced_products": int(block["list_price"].notna().sum()),
                         "stated_on_page": int(stated.notna().sum()), **inferred})

        for idx, row in block.iterrows():
            # pandas turns "no match" into NaN, which is truthy - check it properly.
            said = stated.loc[idx]
            said = said if isinstance(said, str) else None
            unit = said or inferred["unit"]
            basis = "stated on page" if said else (
                f"inferred: {inferred['method']}" if inferred["unit"] else "unresolved")
            price = row["sell_price"] if pd.notna(row.get("sell_price")) else row.get("list_price")
            if pd.isna(price) or unit is None:
                cat.at[idx, "unit_basis"] = basis
                cat.at[idx, "price_confidence"] = "unverified"
                continue
            area = (row["size_short"] * row["size_long"] / 1e6) if pd.notna(row.get("size_short")) else np.nan

            def to_sqm(value):
                if pd.isna(value):
                    return np.nan
                return {
                    "per_sqm": value,
                    "per_sqft": value * 10.7639,
                    "per_piece": value / area if area and not np.isnan(area) else np.nan,
                    "per_box": np.nan,  # needs box coverage; captured per source where published
                }.get(unit, np.nan)

            # List and selling price must be converted the same way, or a discount
            # computed from them compares two different units.
            per_sqm = to_sqm(price)
            list_sqm = to_sqm(row.get("list_price"))
            cat.at[idx, "price_per_sqm"] = round(per_sqm, 0) if pd.notna(per_sqm) else None
            cat.at[idx, "list_per_sqm"] = round(list_sqm, 0) if pd.notna(list_sqm) else None
            cat.at[idx, "price_unit"] = unit
            cat.at[idx, "unit_basis"] = basis
            cat.at[idx, "unit_evidence"] = (
                f"slope {inferred['slope']} (R²={inferred['r2']}, n={inferred['n']})"
                if inferred.get("slope") is not None else inferred.get("method"))
            # Confidence is about the number we ended up with, so an unconvertible
            # price is never "high" just because the page named a unit.
            cat.at[idx, "price_confidence"] = ("unverified" if pd.isna(per_sqm) else
                                               "high" if said else "medium")
    cat["price_per_sqm"] = pd.to_numeric(cat["price_per_sqm"], errors="coerce")
    # Out-of-range prices are never used, whatever the unit logic concluded.
    bad = cat["price_per_sqm"].notna() & (~cat["price_per_sqm"].between(LKR_SQM_MIN, LKR_SQM_MAX))
    cat.loc[bad, "price_confidence"] = "out of range"
    return cat, pd.DataFrame(evidence)


# ---------------------------------------------------------------- checks
def run_checks(cat: pd.DataFrame) -> pd.DataFrame:
    """Every automated data-quality check, as one findings table."""
    out = []

    def add(severity, check, detail, n, sample=""):
        out.append({"severity": severity, "check": check, "detail": detail, "products": int(n),
                    "example": sample})

    priced = cat[cat["list_price"].notna()]
    unresolved = priced[priced["price_per_sqm"].isna()]
    if len(unresolved):
        add("warning", "Price unit unresolved",
            "Published price could not be converted to a per-sqm basis, so it is excluded from comparisons.",
            len(unresolved), unresolved.iloc[0]["url"])

    oor = cat[cat["price_confidence"] == "out of range"]
    if len(oor):
        add("error", "Price outside plausible range",
            f"Converted price falls outside LKR {LKR_SQM_MIN:,.0f}–{LKR_SQM_MAX:,.0f}/sqm. Excluded.",
            len(oor), oor.iloc[0]["url"])

    nosize = cat[cat["size_mm"] == "Unknown"]
    if len(nosize):
        add("warning", "Size not parsed", "No tile dimensions found, so the product cannot be compared.",
            len(nosize), nosize.iloc[0]["url"])

    noimg = cat[cat["image"].fillna("") == ""]
    if len(noimg):
        add("info", "No image", "Product has no picture from the source site.", len(noimg),
            noimg.iloc[0]["url"])

    if "observed_on" in cat:
        obs = pd.to_datetime(cat["observed_on"], errors="coerce")
        stale = cat[obs < (pd.Timestamp.today() - pd.Timedelta(days=STALE_DAYS))]
        if len(stale):
            add("warning", "Stale price", f"Not re-checked in over {STALE_DAYS} days.", len(stale),
                stale.iloc[0]["url"])

    dupes = cat[cat.duplicated("product_id", keep=False)]
    if len(dupes):
        add("error", "Duplicate product id", "The same id appears more than once.", len(dupes),
            dupes.iloc[0]["url"])

    # Prices that disagree wildly with their own peer group (same brand, size, body).
    p = cat[cat["price_per_sqm"].notna()].copy()
    if len(p) > 20:
        grp = p.groupby(["brand", "size_mm", "body"])["price_per_sqm"]
        med = grp.transform("median")
        mad = grp.transform(lambda s: (s - s.median()).abs().median())
        z = (p["price_per_sqm"] - med).abs() / mad.replace(0, np.nan)
        odd = p[z > 6]
        if len(odd):
            add("warning", "Price far from its peer group",
                "More than 6 robust deviations from other tiles of the same brand, size and body.",
                len(odd), odd.iloc[0]["url"])

    missing_src = cat[cat["url"].fillna("") == ""]
    if len(missing_src):
        add("error", "No source URL", "Row cannot be traced back to a public page.", len(missing_src), "")

    return pd.DataFrame(out) if out else pd.DataFrame(
        columns=["severity", "check", "detail", "products", "example"])


# ---------------------------------------------------------------- live spot check
def spot_check(cat: pd.DataFrame, n: int = 12, seed: int = 0) -> pd.DataFrame:
    """Re-fetch a random sample of source pages and confirm the stored price.

    This is the part that catches a site changing its layout: if the parser
    silently starts reading the wrong number, the stored price and the live page
    stop agreeing.
    """
    from .scrapers import buyrocell, mascons, rocell, tileshop  # noqa: F401  (parsers by source)
    from .scrapers.base import fetch

    # The parser is chosen by the page the PRICE came from, which is not always the
    # page the product is catalogued on (Rocell products carry BuyRocell prices).
    parsers = {
        "buyrocell.com": ("buyrocell", lambda u, p: buyrocell._parse_product(u, p)),
        "mascons.com": ("mascons", lambda u, p: mascons._record(u, p)),
        "tileshop.com": ("tileshop", lambda u, p: tileshop._record(u, p)),
    }

    def price_page(row):
        return row["price_url"] if isinstance(row.get("price_url"), str) and row["price_url"].startswith("http") \
            else row.get("url")

    pool = cat[cat["list_price"].notna()].copy()
    pool["check_url"] = pool.apply(price_page, axis=1)
    pool = pool[pool["check_url"].fillna("").str.startswith("http")]
    pool = pool[pool["check_url"].apply(lambda u: any(host in u for host in parsers))]
    if pool.empty:
        return pd.DataFrame()
    sample = pool.sample(min(n, len(pool)), random_state=seed)

    rows = []
    for _, r in sample.iterrows():
        url = r["check_url"]
        host = next(h for h in parsers if h in url)
        source, parse = parsers[host]
        resp = fetch(url, source, refresh=True)
        live_price, status = None, "unreachable"
        if resp is not None and resp.ok:
            try:
                rec = parse(url, resp.text)
                live_price = (rec or {}).get("list_price")
                status = "parsed" if rec else "no product found on page"
            except Exception as exc:
                status = f"parser error: {type(exc).__name__}"
        stored = r["list_price"]
        match = (live_price is not None and stored is not None
                 and abs(float(live_price) - float(stored)) <= max(1.0, 0.01 * float(stored)))
        rows.append({"checked_at": datetime.now().isoformat(timespec="seconds"), "brand": r["brand"],
                     "name": r["name"], "source": source, "url": url, "stored_price": stored,
                     "live_price": live_price, "status": status,
                     "result": "match" if match else ("price changed" if live_price is not None else "failed")})
    return pd.DataFrame(rows)
