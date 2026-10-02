"""The sales agent: plain-English questions in, grounded answers out.

Two modes, same tools:
  * free (default)  - a rule-based parser routes the question to the tools and
                      writes the answer from their outputs. No API key, no cost.
  * claude          - Claude calls the same tools and writes the answer. Turned
                      on when the `anthropic` package is installed and
                      TILEIQ_LLM=claude is set (credentials via ANTHROPIC_API_KEY
                      or `ant auth login`).

Every number in an answer comes from a tool; the agent never invents one.
"""
from __future__ import annotations

import json
import os
import pickle
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import engine, taxonomy

OUT = Path(__file__).resolve().parents[1] / "data" / "processed"


# ---------------------------------------------------------------- data access
@lru_cache(maxsize=1)
def data() -> dict:
    # Only the catalogue and audit outputs always exist; SAP-derived tables appear
    # once real SAP data is supplied.
    d = {}
    for name in ("catalog", "price_position", "recommendations", "gaps", "billing_scored", "quotes",
                 "discount_intel", "audit_findings", "unit_evidence", "spot_check"):
        f = OUT / f"{name}.parquet"
        d[name] = pd.read_parquet(f) if f.exists() else pd.DataFrame()
    d["meta"] = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))
    model_file = OUT / "models.pkl"
    d["fair"] = pickle.load(open(model_file, "rb"))["fair"] if model_file.exists() else None
    d["comps"] = engine.Comparables(d["catalog"], d["fair"])
    return d


def _lkr(x) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"LKR {x:,.0f}"


# ---------------------------------------------------------------- query parsing
def parse(text: str) -> dict:
    t = text.lower()
    spec: dict = {}
    size = taxonomy.parse_size(text)
    if size:
        spec["size_mm"] = taxonomy.size_label(size)
        spec["size_short"], spec["size_long"] = size
        spec["size_class"] = taxonomy.size_class(size)
    for key, rules in (("body", taxonomy.BODY_RULES), ("finish", taxonomy.FINISH_RULES),
                       ("look", taxonomy.LOOK_RULES)):
        v = taxonomy._first(rules, t)
        if v != "Unknown":
            spec[key] = v
    if "polished" in t and "body" not in spec:
        spec["body"] = "Porcelain polished (PGVT)"
    budget = re.search(r"(?:under|below|less than|max|budget|<)\s*(?:lkr|rs\.?)?\s*([\d,]{3,})", t)
    if budget:
        spec["budget"] = float(budget.group(1).replace(",", ""))
    channel = ("Project / contractor" if re.search(r"project|contractor|tender|developer", t) else
               "Dealer" if "dealer" in t else "Retail showroom" if re.search(r"retail|walk.?in|showroom", t) else None)
    brand = next((b for b in ("Rocell", "Lanka Tiles", "Macktiles", "Naveen") if b.lower() in t), None)
    intent = ("trends" if re.search(r"trend|global|world|overseas|abroad|best ?sell|popular|in demand|"
                                    r"what.s hot|new arrival", t) else
              "gaps" if re.search(r"gap|lack|missing|don.t have|not in range|whitespace|should we make|launch", t) else
              "excess_discount" if re.search(r"(discount|discounting).*(more|too much|unnecessar|unrequired|need)|"
                                             r"(over|unnecessar|unrequired).*(discount)|giving away|leak", t) else
              "discount" if re.search(r"discount|how low|give away|margin|approval", t) else
              "landed" if re.search(r"\bland(ed|s)?\b|import(ed)? (cost|price)|duty|cess|fob", t) else
              "reprice" if re.search(r"reprice|recommend|underpriced|overpriced|raise|increase price", t) else
              "compare")
    return {"spec": spec, "channel": channel, "brand": brand, "intent": intent}


# ---------------------------------------------------------------- tools
def tool_our_products(spec: dict, limit: int = 5) -> pd.DataFrame:
    """V One products matching a spec, best first."""
    d = data()
    target = {"name": "", "size_mm": spec.get("size_mm", "Unknown"), "size_class": spec.get("size_class", "Unknown"),
              "body": spec.get("body", "Unknown"), "finish": spec.get("finish", "Unknown"),
              "look": spec.get("look", "Unknown")}
    ours = d["catalog"][d["catalog"]["brand"].isin(engine.OURS)]
    if spec.get("size_mm"):
        ours = ours[ours["size_mm"] == spec["size_mm"]]
    if ours.empty:
        return ours
    s = d["comps"].score(pd.Series(target), ours)
    out = ours.assign(match=s).sort_values(["match", "price_ref"], ascending=[False, True])
    if spec.get("budget"):
        within = out[out["price_ref"].fillna(0) <= spec["budget"]]
        out = within if len(within) else out
    return out.head(limit)


def tool_comparables(spec_or_row: dict, k: int = 6) -> pd.DataFrame:
    d = data()
    row = {"name": "", "size_mm": "Unknown", "size_class": "Unknown", "body": "Unknown", "finish": "Unknown",
           "look": "Unknown", "colour": ""}
    row.update({k_: v for k_, v in spec_or_row.items() if v is not None})
    return d["comps"].find(pd.Series(row), k=k, priced_only=True)


def tool_discount_guardrail(channel: str | None) -> dict:
    ceilings = data()["meta"]["ceilings"]
    return {ch: v for ch, v in ceilings.items() if channel is None or ch == channel}


def tool_gaps(limit: int = 8) -> pd.DataFrame:
    g = data()["gaps"]
    return g[g["status"] != "Covered"].head(limit)


def tool_landed(size_mm: str | None) -> list[dict]:
    fobs = engine.SETTINGS["landed_cost"]["fob_usd_per_sqm"]
    out = []
    for importer, sizes in fobs.items():
        for size, fob in sizes.items():
            if size_mm and size != size_mm:
                continue
            out.append({"importer": importer, "size_mm": size, **engine.landed_cost(fob)})
    return out


def tool_recommendations(brand: str | None = None, limit: int = 8) -> pd.DataFrame:
    r = data()["recommendations"]
    if brand:
        r = r[r["brand"].str.contains(brand, case=False)]
    return r.reindex(r["change_pct"].abs().sort_values(ascending=False).index).head(limit)


# ---------------------------------------------------------------- free-mode answers
def _describe(spec: dict) -> str:
    parts = [spec.get("size_mm"), spec.get("body"), spec.get("finish"), spec.get("look")]
    return " · ".join(p for p in parts if p) or "any spec"


def answer_free(question: str) -> str:
    q = parse(question)
    spec, ch, intent = q["spec"], q["channel"], q["intent"]
    lines: list[str] = []

    if intent == "trends":
        from . import market
        cat = data()["catalog"]
        dim = ("size_mm" if re.search(r"size|format|large", question, re.I) else
               "finish" if re.search(r"finish|matt|gloss|polish", question, re.I) else "look")
        tr = market.global_trends(cat, by=dim)
        if tr.empty:
            return "No global benchmark data loaded yet. Run `python -m tileiq.pipeline --refresh`."
        lines.append(f"**Global demand vs our range, by {dim.replace('_mm', '')}** "
                     "(demand index = share of global best sellers; launch index = share of new arrivals; "
                     "coverage = our share of range ÷ the world's):\n")
        lines.append(f"| {dim.replace('_mm', '').title()} | Demand | New launches | Our coverage | Read |")
        lines.append("|---|---|---|---|---|")
        for _, r in tr.head(8).iterrows():
            lines.append(f"| {r[dim]} | {r['demand_index']:.2f}× | {r['launch_index']:.2f}× | "
                         f"{r['coverage_ratio']:.2f}× | {r['verdict']} |")
        best = tr.iloc[0]
        lines.append(f"\n**Priority: {best[dim]}.** It is {best['demand_index']:.1f}× over-represented among global "
                     f"best sellers and {best['launch_index']:.1f}× among new launches, while it is "
                     f"{best['our_share'] * 100:.0f}% of our range against {best['global_share'] * 100:.0f}% "
                     "globally. See the Global benchmark page for the actual designs.")
        lines.append("\n_Demand flags come from The Tile Shop (US), which marks its own best sellers and new "
                     "arrivals. US retail prices are not a Sri Lanka price guide._")
        return "\n".join(lines)

    if intent == "excess_discount":
        di = pd.read_parquet(OUT / "discount_intel.parquet") if (OUT / "discount_intel.parquet").exists() \
            else pd.DataFrame()
        if di.empty:
            return "No published discount data available yet."
        over = di[di["excess_pct"] > 3]
        lines.append(f"**{len(over)} products are discounted deeper than the market requires.** "
                     f"Average excess: {over['excess_pct'].mean():.0f} points, "
                     f"{_lkr(over['excess_lkr_sqm'].mean())}/sqm on list.\n")
        lines.append("| Product | Spec | List | Selling | Market benchmark | We give | Market needs | Excess |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for _, r in over.head(10).iterrows():
            lines.append(f"| {r['brand']} {r['name'][:26]} | {r['size_mm']} {r['finish']} | {_lkr(r['our_list'])} | "
                         f"{_lkr(r['our_sell'])} | {_lkr(r['benchmark'])} | {r['discount_pct']:.0f}% | "
                         f"{r['needed_pct']:.0f}% | **{r['excess_pct']:.0f} pts** ({_lkr(r['excess_lkr_sqm'])}/sqm) |")
        lines.append("\nEvery figure here comes from a published price; each row links back to its source page.")
        return "\n".join(lines)

    if intent == "gaps":
        g = tool_gaps()
        lines.append("**Biggest assortment gaps** (competitor presence + lost-quote demand, discounted where we "
                     "have a near substitute):\n")
        lines.append("| Spec | Status | Competitors | Lost quotes | Lost sqm | Median comp. price |")
        lines.append("|---|---|---|---|---|---|")
        for _, r in g.iterrows():
            lines.append(f"| {r['size_mm']} {r['body']} {r['finish']} {r['look']} | {r['status']} | "
                         f"{r['competitors']} | {r['lost_quotes']} | {r['lost_sqm']:,.0f} | {_lkr(r['median_price'])} |")
        lines.append("\nTreat these as candidates for a sourcing or production decision. Lost-quote volumes show "
                     "demand that walked away, not a forecast.")

    elif intent == "landed":
        rows = tool_landed(spec.get("size_mm"))
        lines.append(f"**Landed cost of imported equivalents** ({spec.get('size_mm', 'all sizes')}, per sqm):\n")
        lines.append("| Importer | Size | FOB USD | Landed (duty paid) | Likely shelf incl. VAT |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            lines.append(f"| {r['importer']} | {r['size_mm']} | {r['fob_usd']:.2f} | {_lkr(r['landed_lkr'])} | "
                         f"{_lkr(r['shelf_lkr'])} |")
        lines.append("\nRates come from `config/settings.yaml`, and each one marked VERIFY needs confirming against "
                     "the current Customs tariff.")

    elif intent == "reprice":
        r = tool_recommendations(q["brand"])
        lines.append("**SKUs with the largest recommended list-price moves:**\n")
        lines.append("| SKU | Spec | Our list | Our typical sell | Benchmark | Index | Move | Action |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for _, x in r.iterrows():
            lines.append(f"| {x['brand']} {x['name'][:28]} | {x['size_mm']} {x['finish']} | {_lkr(x['our_list'])} | "
                         f"{_lkr(x['our_sell'])} | {_lkr(x['benchmark'])} | {x['index_sell']:.2f} | "
                         f"{x['change_pct']:+.1f}% | {x['action']} |")

    else:  # compare / discount: product-led answer
        ours = tool_our_products(spec)
        lines.append(f"**Request:** {_describe(spec)}" + (f", budget {_lkr(spec['budget'])}/sqm" if spec.get("budget") else "")
                     + (f", channel: {ch}" if ch else ""))
        if ours.empty:
            lines.append(f"\nWe have **no V One product in {spec.get('size_mm', 'this spec')}**. "
                         "This counts as an assortment gap, so it's worth logging as a lost-demand signal.")
            comps = tool_comparables(spec)
        else:
            lines.append("\n**Our closest products**\n")
            lines.append("| Product | Spec | List/sqm | Typical sell/sqm | Price source |")
            lines.append("|---|---|---|---|---|")
            for _, r in ours.iterrows():
                lines.append(f"| {r['brand']} {r['name'][:30]} | {r['size_mm']} {r['body']} {r['finish']} {r['look']} | "
                             f"{_lkr(r['list_price'])} | {_lkr(r['price_ref'])} | "
                             f"{r['price_source'] if pd.notna(r['price_source']) else 'not published (needs SAP price list)'} |")
            comps = tool_comparables(ours.iloc[0].to_dict(), k=30)
        if len(comps):
            # Keep both sides visible: imports would otherwise crowd out local brands,
            # because their modelled prices cover every spec while field captures don't.
            is_imp = comps["brand"].str.startswith("Importer")
            comps = pd.concat([comps[~is_imp].head(4), comps[is_imp].head(3)])
            lines.append("\n**Competitor comparables** (price adjusted to the same spec)\n")
            lines.append("| Competitor | Product | Spec | Shelf price | Adjusted | Match |")
            lines.append("|---|---|---|---|---|---|")
            for _, c in comps.iterrows():
                lines.append(f"| {c['brand']} | {c['name'][:28]} | {c['size_mm']} {c['finish']} {c['look']} | "
                             f"{_lkr(c['price_ref'])} | {_lkr(c.get('adj_price'))} | {c['match_score']:.0f} |")
            # Local brands set the benchmark; imports are a separate floor.
            local = comps[~comps["brand"].str.startswith("Importer")] if "adj_price" in comps else comps
            imports = comps[comps["brand"].str.startswith("Importer")] if "adj_price" in comps else comps.iloc[:0]
            bench = np.nan
            if "adj_price" in comps:
                bench = (float(np.nanmedian(local["adj_price"])) if local["adj_price"].notna().sum() >= 2
                         else float(np.nanmedian(comps["adj_price"])))
            if not ours.empty and not np.isnan(bench):
                mine = ours.iloc[0]
                basis = "local brands" if local["adj_price"].notna().sum() >= 2 else "all comparables"
                lines.append(f"\nOur best match sells at **{mine['price_ref'] / bench:.2f}×** the {basis} median "
                             f"({_lkr(bench)}).")
                if len(imports) and imports["adj_price"].notna().any():
                    lines.append(f"Imported equivalents land around {_lkr(np.nanmin(imports['adj_price']))}/sqm, so "
                                 "the gap to them has to be carried by the brand and the service story, not by discount.")
        g = tool_discount_guardrail(ch)
        if g:
            lines.append("\n**Discount guardrail** (maximises expected margin, from quote history)")
            for chn, v in g.items():
                lines.append(f"- {chn}: up to **{v['ceiling']:.0f}%** (win ≈ {v['win_at_ceiling']:.0%}). "
                             f"Today's average is {v['avg_discount']:.0f}%. Anything above "
                             f"{v['ceiling'] + engine.SETTINGS['discount']['approval_buffer_pts']:.0f}% should need "
                             "manager approval.")
        if not ours.empty and len(comps) and not np.isnan(bench) and pd.notna(ours.iloc[0]["list_price"]):
            mine = ours.iloc[0]
            walk = max(bench * 0.97, mine["list_price"] * engine.SETTINGS["discount"]["cost_ratio_of_list"] * 1.25)
            target = max(bench * engine.SETTINGS["target_index"].get(mine["brand"], 1.0), walk)
            lines.append(f"\n**Pricing call for {mine['name']}**")
            if target > bench * engine.SETTINGS["target_index"].get(mine["brand"], 1.0) * 1.001:
                lines.append(f"- Quote at **{_lkr(target)}/sqm** ({1 - target / mine['list_price']:.0%} off list). "
                             "That is the cost-based floor, which sits above our target market position here: the "
                             "comparable set is cheap, so hold price on the value story rather than chase it down.")
            else:
                lines.append(f"- Quote at **{_lkr(target)}/sqm**, which is {1 - target / mine['list_price']:.0%} off list "
                             f"and holds {mine['brand']}'s target position of {target / bench:.2f}× the market.")
            lines.append(f"- Walk-away floor: **{_lkr(walk)}/sqm** ({1 - walk / mine['list_price']:.0%} off list). "
                         "Below this, a comparable competitor tile is cheaper anyway, so extra discount rarely wins.")
            if mine["price_ref"] < walk:
                lines.append(f"- ⚠️ Our current typical price ({_lkr(mine['price_ref'])}) is **"
                             f"{1 - mine['price_ref'] / bench:.0%} below the market median**. That's discount we "
                             "don't need to give.")

    return "\n".join(lines)


# ---------------------------------------------------------------- Claude mode
SYSTEM = """You are TileIQ, a pricing and assortment analyst for the V One tile group in Sri Lanka
(Rocell and Lanka Tiles). Competitors include Macktiles, Naveen Ceramic and importers from
India, China and Spain/Italy. Answer sales and pricing questions using only numbers returned by
the tools; if a tool has no data, say so. Prices are LKR per sqm. Lead with the recommendation,
then the evidence, in a compact table where useful. Flag clearly when data is marked DEMO."""


def answer_claude(question: str, history: list[dict] | None = None) -> str:
    import anthropic
    from anthropic import beta_tool

    @beta_tool
    def find_our_products(query: str) -> str:
        """Find V One (Rocell / Lanka Tiles) products matching a tile spec described in plain words.

        Args:
            query: Spec in words, e.g. "600x1200 matte marble porcelain under 6500".
        """
        return tool_our_products(parse(query)["spec"])[
            ["brand", "name", "size_mm", "body", "finish", "look", "list_price", "price_ref", "price_source"]
        ].to_json(orient="records")

    @beta_tool
    def find_competitor_comparables(query: str) -> str:
        """Competitor products comparable to a spec, with prices adjusted to that spec.

        Args:
            query: Spec in words, e.g. "600x600 polished marble".
        """
        c = tool_comparables(parse(query)["spec"])
        return c[[x for x in ["brand", "name", "size_mm", "finish", "look", "price_ref", "adj_price", "match_score",
                              "price_source", "data_quality"] if x in c]].to_json(orient="records")

    @beta_tool
    def discount_guardrails(channel: str = "") -> str:
        """Margin-maximising discount ceiling per channel from quote history.

        Args:
            channel: "Retail showroom", "Dealer", "Project / contractor", or empty for all.
        """
        return json.dumps(tool_discount_guardrail(channel or None))

    @beta_tool
    def assortment_gaps(limit: int = 8) -> str:
        """Top specs that competitors sell or customers request that V One does not cover.

        Args:
            limit: Number of gaps to return.
        """
        return tool_gaps(limit).to_json(orient="records")

    @beta_tool
    def repricing_recommendations(brand: str = "") -> str:
        """SKUs with the largest recommended list-price changes versus the competitive benchmark.

        Args:
            brand: "Rocell", "Lanka Tiles" or empty for both.
        """
        return tool_recommendations(brand or None).drop(columns=["comps"], errors="ignore").to_json(orient="records")

    @beta_tool
    def import_landed_cost(size_mm: str = "") -> str:
        """Landed cost and likely shelf price of imported tiles in Sri Lanka, per sqm.

        Args:
            size_mm: e.g. "600x1200", or empty for all sizes.
        """
        return json.dumps(tool_landed(size_mm or None), default=float)

    client = anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model="claude-opus-5",
        max_tokens=16000,
        system=SYSTEM,
        tools=[find_our_products, find_competitor_comparables, discount_guardrails, assortment_gaps,
               repricing_recommendations, import_landed_cost],
        messages=(history or []) + [{"role": "user", "content": question}],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    final = None
    for message in runner:
        final = message
    if final is None:
        return "No response."
    if final.stop_reason == "refusal":
        return "The model declined this request."
    return "".join(b.text for b in final.content if b.type == "text")


def answer(question: str, history: list[dict] | None = None) -> str:
    if os.environ.get("TILEIQ_LLM") == "claude":
        try:
            return answer_claude(question, history)
        except Exception as exc:  # fall back to free mode rather than failing the user
            return answer_free(question) + f"\n\n_(Claude mode unavailable: {exc.__class__.__name__}; free mode used.)_"
    return answer_free(question)
