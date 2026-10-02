"""Core analytics: comparables, fair price, price position, discounts, gaps.

Kept free of UI code so the dashboard, the agent and batch reports all call the
same functions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
SETTINGS = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
OURS = set(SETTINGS["portfolio"]["ours"])

BODY_FAMILY = {  # bodies that are credible substitutes for each other
    "Porcelain (GVT)": "vitrified", "Porcelain polished (PGVT)": "vitrified", "Double charge": "vitrified",
    "Full body": "vitrified", "Soluble salt": "vitrified", "Slab": "slab", "Ceramic": "ceramic",
    "Mosaic": "mosaic", "Unknown": "unknown",
}
FINISH_FAMILY = {
    "Gloss / polished": "shiny", "Lappato / semi-polished": "shiny", "Matte": "matte", "Satin": "matte",
    "Structured / anti-slip": "textured", "Carving": "textured", "Sugar": "textured", "Unknown": "unknown",
}
LOOK_FAMILY = {"Marble": "natural", "Stone": "natural", "Terrazzo": "natural", "Cement / concrete": "urban",
               "Plain colour": "urban", "Wood": "wood", "Decor / pattern": "decor"}


# ---------------------------------------------------------------- landed cost
def landed_cost(fob_usd: float, cfg: dict | None = None) -> dict:
    """Shelf price an importer could charge in Sri Lanka, per sqm.

    This is a CALCULATOR, not observed data. It is never mixed into the
    catalogue or any benchmark - it exists so a user can test what an import at
    a given FOB would have to sell for. Every rate comes from config/settings.yaml.
    """
    c = cfg or SETTINGS["landed_cost"]
    cif_usd = (fob_usd + c["freight_usd_per_sqm"]) * (1 + c["insurance_pct"] / 100)
    cif = cif_usd * c["usd_lkr"]
    duties = cif * (c["customs_duty_pct"] + c["cess_pct"] + c["pal_pct"]) / 100
    sscl = (cif + duties) * c["sscl_pct"] / 100
    landed = cif + duties + sscl
    shelf_ex_vat = landed * (1 + c["importer_margin_pct"] / 100)
    shelf = shelf_ex_vat * (1 + c["vat_pct"] / 100)
    return {"fob_usd": fob_usd, "cif_lkr": cif, "duties_lkr": duties, "sscl_lkr": sscl, "landed_lkr": landed,
            "shelf_ex_vat_lkr": shelf_ex_vat, "shelf_lkr": shelf}


# ---------------------------------------------------------------- fair price
@dataclass
class FairPriceModel:
    model: Ridge
    columns: list[str]
    premiums: pd.DataFrame
    r2: float
    n: int

    def features(self, df: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(index=df.index)
        area = (df["size_short"].fillna(600) * df["size_long"].fillna(600)) / 1e6
        X["log_area"] = np.log(area)
        X["log_long_side"] = np.log(df["size_long"].fillna(600) / 600)
        for col in ("body", "finish", "look", "brand"):
            dummies = pd.get_dummies(df[col].fillna("Unknown"), prefix=col, dtype=float)
            X = X.join(dummies)
        return X.reindex(columns=self.columns, fill_value=0.0)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.exp(self.model.predict(self.features(df)))


def train_fair_price(priced: pd.DataFrame) -> FairPriceModel:
    """Hedonic regression: log(list price/sqm) on tile attributes + brand.
    Each coefficient reads as a % premium, which is what a pricing manager wants."""
    df = priced.dropna(subset=["list_price"]).copy()
    X = pd.DataFrame(index=df.index)
    area = (df["size_short"].fillna(600) * df["size_long"].fillna(600)) / 1e6
    X["log_area"] = np.log(area)
    X["log_long_side"] = np.log(df["size_long"].fillna(600) / 600)
    for col in ("body", "finish", "look", "brand"):
        X = X.join(pd.get_dummies(df[col].fillna("Unknown"), prefix=col, dtype=float))
    y = np.log(df["list_price"].astype(float))
    model = Ridge(alpha=1.0).fit(X, y)
    r2 = model.score(X, y)
    prem = pd.DataFrame({"feature": X.columns, "coef": model.coef_})
    prem["premium_pct"] = (np.exp(prem["coef"]) - 1) * 100
    prem[["attribute", "value"]] = prem["feature"].str.split("_", n=1, expand=True)
    return FairPriceModel(model, list(X.columns), prem, r2, len(df))


# ---------------------------------------------------------------- comparables
class Comparables:
    """Finds like-for-like products and adjusts their prices to the target spec."""

    def __init__(self, catalog: pd.DataFrame, fair: FairPriceModel | None = None):
        self.cat = catalog.reset_index(drop=True)
        self.fair = fair
        text = (self.cat["name"].fillna("") + " " + self.cat["look"] + " " + self.cat["finish"] + " " +
                self.cat["colour"].fillna("")).str.lower()
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), min_df=1)
        self.tfidf = self.vec.fit_transform(text)

    def score(self, target: pd.Series, cand: pd.DataFrame) -> pd.Series:
        s = pd.Series(0.0, index=cand.index)
        s += np.where(cand["size_mm"] == target["size_mm"], 40,
                      np.where(cand["size_class"] == target["size_class"], 15, 0))
        s += np.where(cand["body"] == target["body"], 20,
                      np.where(cand["body"].map(BODY_FAMILY) == BODY_FAMILY.get(target["body"]), 12, 0))
        s += np.where(cand["finish"] == target["finish"], 15,
                      np.where(cand["finish"].map(FINISH_FAMILY) == FINISH_FAMILY.get(target["finish"]), 8, 0))
        s += np.where(cand["look"] == target["look"], 15,
                      np.where(cand["look"].map(LOOK_FAMILY) == LOOK_FAMILY.get(target["look"], "-"), 7, 0))
        return s

    def find(self, target: pd.Series | dict, k: int = 8, competitors_only: bool = True,
             require_same_size: bool = True, priced_only: bool = False) -> pd.DataFrame:
        target = pd.Series(target)
        # Global rows are a design benchmark, not a Sri Lanka price comparison.
        cand = self.cat[self.cat["group"] != "Global"]
        if competitors_only:
            cand = cand[~cand["brand"].isin(OURS)]
        if "product_id" in target and pd.notna(target.get("product_id")):
            cand = cand[cand["product_id"] != target["product_id"]]
        if require_same_size and target.get("size_mm") not in (None, "Unknown"):
            same = cand[cand["size_mm"] == target["size_mm"]]
            cand = same if len(same) else cand
        # Hard constraint: body family must be a credible substitute.
        fam = BODY_FAMILY.get(target.get("body"), "unknown")
        if fam != "unknown":
            cand = cand[cand["body"].map(BODY_FAMILY).isin([fam, "unknown"])]
        if priced_only:
            cand = cand[cand["price_ref"].notna()]
        if cand.empty:
            return cand.assign(match_score=[])
        score = self.score(target, cand)
        name = f"{target.get('name', '')} {target.get('look', '')} {target.get('finish', '')}".lower()
        sim = cosine_similarity(self.vec.transform([name]), self.tfidf[cand.index]).ravel()
        out = cand.assign(match_score=(score + 5 * sim).round(1)).sort_values("match_score", ascending=False)
        out = out.head(k).copy()
        if self.fair is not None and "price_ref" in out and out["price_ref"].notna().any():
            # Adjust each comparable's price for spec differences via the hedonic model,
            # holding brand fixed so the brand gap stays visible.
            t = pd.DataFrame([target])
            for c in ("size_short", "size_long"):
                t[c] = pd.to_numeric(t.get(c), errors="coerce")
            adj = []
            for _, r in out.iterrows():
                if pd.isna(r["price_ref"]):
                    adj.append(np.nan)
                    continue
                t_as = t.assign(brand=r["brand"])
                ratio = self.fair.predict(t_as)[0] / self.fair.predict(pd.DataFrame([r]))[0]
                adj.append(r["price_ref"] * float(np.clip(ratio, 0.7, 1.4)))
            out["adj_price"] = np.round(adj, -1)
        return out


# ---------------------------------------------------------------- price position
def price_position(catalog: pd.DataFrame, comps: Comparables) -> pd.DataFrame:
    """For every V One SKU with a price: where it sits vs its comparable set."""
    ours = catalog[catalog["brand"].isin(OURS) & catalog["price_ref"].notna() &
                   (catalog["group"] != "Global")]
    rows = []
    for _, r in ours.iterrows():
        c = comps.find(r, k=6, priced_only=True)
        c = c[c["match_score"] >= 55] if len(c) else c
        if c.empty or "adj_price" not in c:
            continue
        local = c[~c["brand"].str.startswith("Importer")]
        imp = c[c["brand"].str.startswith("Importer")]
        # Local brands anchor the benchmark: they are who we actually lose deals to on
        # the showroom floor. Imports are reported separately as a price floor, so a
        # cheap Indian GVT can't drag our target price down on its own.
        local_med = float(np.nanmedian(local["adj_price"])) if local["adj_price"].notna().sum() >= 2 else np.nan
        bench = local_med if not np.isnan(local_med) else float(np.nanmedian(c["adj_price"]))
        rows.append({
            "product_id": r["product_id"], "brand": r["brand"], "name": r["name"], "size_mm": r["size_mm"],
            "body": r["body"], "finish": r["finish"], "look": r["look"],
            "our_list": r.get("list_per_sqm") if pd.notna(r.get("list_per_sqm")) else r["price_ref"],
            "our_sell": r["price_ref"],
            "benchmark": bench, "n_comps": len(c), "benchmark_basis": "local brands" if not np.isnan(local_med)
            else "all comparables (few local prices)",
            "local_bench": local_med,
            "import_floor": float(np.nanmin(imp["adj_price"])) if len(imp) else np.nan,
            # How many comparables carry a price whose unit we could verify.
            "verified_comps": int(c["price_confidence"].isin(["high", "medium"]).sum())
            if "price_confidence" in c else 0,
            "index_list": (r.get("list_per_sqm") or r["price_ref"]) / bench,
            "index_sell": r["price_ref"] / bench,
            "comps": ", ".join(f"{b} {n[:22]}" for b, n in zip(c["brand"], c["name"])),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- discounts
def load_billing(path: Path) -> pd.DataFrame:
    b = pd.read_csv(path, dtype={"VTWEG": str, "VKORG": str})
    b["FKDAT"] = pd.to_datetime(b["FKDAT"])
    b["disc_pct"] = 100 * b["KZWI3"] / b["KZWI1"]
    b["net_per_sqm"] = b["NETWR"] / b["FKIMG"]
    b["channel"] = b["VTWEG"].map({"10": "Retail showroom", "20": "Dealer", "30": "Project / contractor"})
    return b


def win_curves(quotes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Win probability vs discount, per channel, from quote history.

    A logistic model with a saturating discount term lets the curve flatten.
    The ceiling is the discount that maximises expected margin per quote,
    P(win | d) x ((1 - d) - cost ratio): past it, each extra point of discount
    gives away more margin than the extra wins bring back."""
    q = quotes[quotes["DISC_PCT"].notna()].copy()
    q["won"] = (q["STATUS"] == "Won").astype(int)
    q["channel"] = q["VTWEG"].astype(str).map({"10": "Retail showroom", "20": "Dealer", "30": "Project / contractor"})
    cost = SETTINGS["discount"]["cost_ratio_of_list"]
    curves, ceilings = [], {}
    grid = np.arange(0, 40.5, 0.5)
    for ch, g in q.groupby("channel"):
        X = np.column_stack([1 - np.exp(-g["DISC_PCT"] / 5), g["DISC_PCT"] / 100])
        m = LogisticRegression(C=10).fit(X, g["won"])
        p = m.predict_proba(np.column_stack([1 - np.exp(-grid / 5), grid / 100]))[:, 1]
        exp_margin = p * ((1 - grid / 100) - cost)
        ceiling = float(grid[int(np.argmax(exp_margin))])
        observed = g.assign(band=(g["DISC_PCT"] // 2.5) * 2.5).groupby("band")["won"].agg(["mean", "count"])
        ceilings[ch] = {"ceiling": ceiling, "win_at_ceiling": float(np.interp(ceiling, grid, p)),
                        "win_at_zero": float(p[0]), "n_quotes": len(g),
                        "actual_win_rate": float(g["won"].mean()),
                        "avg_discount": float(g["DISC_PCT"].mean()),
                        "margin_at_ceiling": float(exp_margin.max()),
                        "margin_at_avg": float(np.interp(g["DISC_PCT"].mean(), grid, exp_margin))}
        curves.append(pd.DataFrame({"channel": ch, "discount": grid, "win_prob": p, "exp_margin": exp_margin}))
        curves.append(pd.DataFrame({"channel": ch, "discount": observed.index + 1.25,
                                    "observed_win": observed["mean"], "observed_n": observed["count"]}))
    return pd.concat(curves, ignore_index=True), ceilings


def discount_leakage(billing: pd.DataFrame, ceilings: dict) -> pd.DataFrame:
    """Value given away above the point where discount stops winning deals."""
    b = billing.copy()
    b["ceiling"] = b["channel"].map({k: v["ceiling"] for k, v in ceilings.items()})
    b["excess_pts"] = (b["disc_pct"] - b["ceiling"]).clip(lower=0)
    b["leakage_lkr"] = b["KZWI1"] * b["excess_pts"] / 100
    return b


# ---------------------------------------------------------------- recommendations
def recommend(position: pd.DataFrame, ceilings: dict) -> pd.DataFrame:
    """List price moves toward the brand's target index, capped per cycle."""
    if position.empty:
        return position
    cap = SETTINGS["max_list_change_pct"] / 100
    r = position.copy()
    r["target_index"] = r["brand"].map(SETTINGS["target_index"]).fillna(1.0)
    # The benchmark is a net shelf price; we steer our typical *sell* price to target
    # and scale the list price by the same ratio.
    r["target_sell"] = r["benchmark"] * r["target_index"]
    move = (r["target_sell"] / r["our_sell"] - 1).clip(-cap, cap)
    r["rec_list"] = (r["our_list"] * (1 + move)).round(-1)
    r["change_pct"] = (move * 100).round(1)
    # Never recommend a list price below what imports can land at (protects margin logic).
    r["action"] = np.select(
        [r["change_pct"] >= 2, r["change_pct"] <= -2],
        ["Raise list / cut discount", "Reprice down or hold with value story"], "Hold")
    r["disc_ceiling_retail"] = ceilings.get("Retail showroom", {}).get("ceiling")
    r["disc_ceiling_dealer"] = ceilings.get("Dealer", {}).get("ceiling")
    r["disc_ceiling_project"] = ceilings.get("Project / contractor", {}).get("ceiling")
    return r


# ---------------------------------------------------------------- gaps
def assortment_gaps(catalog: pd.DataFrame, quotes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Specs competitors sell (or customers request) that V One doesn't cover."""
    keys = ["size_mm", "body", "finish", "look"]
    # Cells with an unknown finish or look are extraction gaps, not assortment gaps.
    cat = catalog[(catalog["size_mm"] != "Unknown") & (catalog["finish"] != "Unknown") &
                  (catalog["look"] != "Unknown")].copy()
    cat["body_fam"] = cat["body"].map(BODY_FAMILY)
    cat["finish_fam"] = cat["finish"].map(FINISH_FAMILY)
    ours = cat[cat["brand"].isin(OURS)]
    comp = cat[~cat["brand"].isin(OURS) & (cat["group"] != "Global")]
    g = comp.groupby(keys).agg(competitor_skus=("product_id", "count"),
                               competitors=("brand", lambda s: ", ".join(sorted(set(s)))),
                               median_price=("price_ref", "median")).reset_index()
    own_exact = ours.groupby(keys).size().rename("our_skus_exact")
    own_near = ours.groupby(["size_mm", "body_fam", "finish_fam", "look"]).size().rename("our_skus_near")
    g = g.join(own_exact, on=keys)
    g["body_fam"] = g["body"].map(BODY_FAMILY)
    g["finish_fam"] = g["finish"].map(FINISH_FAMILY)
    g = g.join(own_near, on=["size_mm", "body_fam", "finish_fam", "look"])
    g[["our_skus_exact", "our_skus_near"]] = g[["our_skus_exact", "our_skus_near"]].fillna(0).astype(int)

    if quotes is not None and len(quotes):
        lost = quotes[quotes["ABGRU"] == "Product not available"]
        dem = lost.groupby(["REQ_SIZE", "REQ_BODY", "REQ_FINISH", "REQ_LOOK"]).agg(
            lost_quotes=("VBELN", "count"), lost_sqm=("KWMENG", "sum")).reset_index()
        dem.columns = keys + ["lost_quotes", "lost_sqm"]
        g = g.merge(dem, on=keys, how="outer")
    else:
        g["lost_quotes"], g["lost_sqm"] = 0, 0.0
    g[["competitor_skus", "our_skus_exact", "our_skus_near", "lost_quotes"]] = \
        g[["competitor_skus", "our_skus_exact", "our_skus_near", "lost_quotes"]].fillna(0).astype(int)
    g["lost_sqm"] = g["lost_sqm"].fillna(0)
    g["competitors"] = g["competitors"].fillna("(customer requests only)")
    # Gap score: competitor presence + demand evidence, discounted if we have near substitutes.
    g["gap_score"] = ((np.log1p(g["competitor_skus"]) * 10 + np.log1p(g["lost_sqm"]) * 6) /
                      (1 + 2 * g["our_skus_exact"] + 0.7 * g["our_skus_near"])).round(1)
    g["status"] = np.select([g["our_skus_exact"] > 0, g["our_skus_near"] > 0],
                            ["Covered", "Near substitute only"], "Not in range")
    return g.sort_values("gap_score", ascending=False)
