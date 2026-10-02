/* TileIQ front end. No framework, no build step: load JSON once, render views. */
(() => {
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const view = $("#view");
const DATA = {};
const OURS = ["Rocell", "Lanka Tiles"];
const PALETTE = ["#38bdf8", "#fb923c", "#34d399", "#a78bfa", "#f472b6", "#facc15", "#60a5fa", "#f87171"];

/* ---------------------------------------------------------------- helpers */
const lkr = v => v == null ? "—" : "LKR " + Math.round(v).toLocaleString();
const usd = v => v == null ? "—" : "$" + Math.round(v).toLocaleString();
const pct = (v, d = 0) => v == null ? "—" : v.toFixed(d) + "%";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const img = p => p.img ? `img/${p.img}` : null;
const spec = p => [p.sz, p.f, p.lk].filter(Boolean).join(" · ");
const isOurs = p => OURS.includes(p.b);
const byId = id => DATA.catalog.find(p => p.id === id);

function confBadge(p) {
  if (p.p == null) return `<span class="badge">no public price</span>`;
  if (p.pc === "high") return `<span class="badge good">unit stated by source</span>`;
  if (p.pc === "medium") return `<span class="badge warn">unit inferred · audited</span>`;
  return `<span class="badge bad">unit unverified</span>`;
}

function tile(p, opts = {}) {
  const src = img(p);
  const flags = [];
  if (p.bs) flags.push(`<span class="badge good">best seller</span>`);
  if (p.new) flags.push(`<span class="badge accent">new</span>`);
  if (opts.flag) flags.push(`<span class="badge warn">${esc(opts.flag)}</span>`);
  const price = p.p != null ? `<div class="pr">${lkr(p.p)}<span class="muted small">/sqm</span></div>`
    : p.usd != null ? `<div class="pr">${usd(p.usd)}<span class="muted small">/sqm US</span></div>`
    : `<div class="pr muted small">price not published</div>`;
  return `<div class="tile">
    <div class="ph">${src ? `<img loading="lazy" decoding="async" src="${src}" alt="${esc(p.n)}">` : ""}
      ${flags.length ? `<div class="flags">${flags.join("")}</div>` : ""}</div>
    <div class="body">
      <div class="nm">${esc(p.n || "—")}</div>
      <div class="sp">${esc(p.b)} · ${esc(spec(p))}</div>
      ${price}
      ${opts.note ? `<div class="sp">${esc(opts.note)}</div>` : ""}
      ${p.u ? `<a class="sp" href="${esc(p.u)}" target="_blank" rel="noopener">source ↗</a>` : ""}
    </div></div>`;
}

/* Incremental grid: render a page of tiles, add more as the user scrolls. */
function tileGrid(el, rows, opts = {}) {
  const step = opts.step || 48;
  let shown = 0;
  el.innerHTML = `<div class="tiles"></div><div class="sentinel"></div>`;
  const grid = $(".tiles", el);
  if (!rows.length) { el.innerHTML = `<div class="empty">No products match these filters.</div>`; return; }
  const more = () => {
    const next = rows.slice(shown, shown + step);
    grid.insertAdjacentHTML("beforeend", next.map(p => tile(p, opts)).join(""));
    shown += next.length;
    if (shown >= rows.length) io.disconnect();
  };
  const io = new IntersectionObserver(e => { if (e[0].isIntersecting) more(); }, { rootMargin: "600px" });
  more();
  io.observe($(".sentinel", el));
}

function table(cols, rows, opts = {}) {
  const preview = opts.preview ?? 8;                 // show a readable handful first
  const head = cols.map(c => `<th class="${c.n ? "n" : ""}">${esc(c.label)}</th>`).join("");
  const tr = r => `<tr>${cols.map(c => {
    const v = c.get(r);
    return `<td class="${c.n ? "n" : ""}">${c.raw ? v : esc(v ?? "—")}</td>`;
  }).join("")}</tr>`;
  const first = rows.slice(0, preview).map(tr).join("");
  const rest = rows.slice(preview).map(tr).join("");
  const id = "t" + Math.random().toString(36).slice(2, 8);
  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead>
      <tbody id="${id}">${first}</tbody>
      ${rest ? `<tbody id="${id}-rest" hidden>${rest}</tbody>` : ""}</table></div>
    ${rest ? `<button class="more-btn" data-more="${id}">Show all ${rows.length.toLocaleString()} rows</button>` : ""}`;
}

/* Wire up every "show all rows" button on the current view. */
function bindMore() {
  $$("[data-more]").forEach(b => b.onclick = () => {
    const rest = document.getElementById(b.dataset.more + "-rest");
    if (!rest) return;
    rest.hidden = !rest.hidden;
    b.textContent = rest.hidden ? b.textContent.replace("Show fewer", "Show all") : "Show fewer";
    if (!rest.hidden) b.textContent = "Show fewer";
  });
}

/* Jargon gets a dotted underline and a plain-English explanation on hover. */
const GLOSSARY = {
  "per sqm": "Per square metre. Tile prices are published per tile or per box, so everything is converted to one unit before comparing.",
  "price index": "Our price divided by a comparable competitor's price. 1.00 means the same price; 1.20 means we are 20% dearer.",
  "specification value": "What a tile of this size, body and finish typically sells for across our own range. It shows whether a price fits the rest of the range.",
  "demand index": "How over- or under-represented a design is among the global retailer's own best sellers. 1.00 is average; 2.00 is twice its share.",
  "launch index": "The same measure for brand-new products: where the market is heading.",
  "coverage": "Our share of the range in a segment divided by the world's share. Below 1.00 means we carry less than the market does.",
  "hedonic model": "A model that prices the parts of a tile — its size, body, finish and look — so two different tiles can be compared fairly.",
  "unit inferred": "The website did not say whether a price was per tile or per square metre, so it was worked out from the source's own data and checked.",
  "reach": "How many people follow the brand on channels that publish their numbers openly.",
};
function term(word, text) {
  const tipText = text || GLOSSARY[String(word).toLowerCase()] || "";
  return tipText ? `<span class="term" data-tip="${esc(tipText)}">${esc(word)}</span>` : esc(word);
}

function kpi(label, value, sub) {
  // label may contain a term() tooltip, so it is trusted markup we build ourselves.
  return `<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div>
    ${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
}

/* ---------------------------------------------------------------- charts (inline SVG) */
const tip = document.createElement("div");
tip.className = "tip"; tip.style.display = "none"; document.body.appendChild(tip);
function hover(el) {
  el.addEventListener("mousemove", e => {
    const t = e.target.closest("[data-tip]");
    if (!t) { tip.style.display = "none"; return; }
    tip.innerHTML = t.dataset.tip;
    tip.style.display = "block";
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 280) + "px";
    tip.style.top = (e.clientY + 16) + "px";
  });
  el.addEventListener("mouseleave", () => { tip.style.display = "none"; });
}

function scatter(rows, { x, y, label, color, xLabel, yLabel, diagonal = false, logScale = false }) {
  const W = 760, H = 420, m = { l: 62, r: 16, t: 14, b: 46 };
  const xs = rows.map(x), ys = rows.map(y);
  const xMax = Math.max(...xs) * 1.05, yMax = Math.max(...ys) * 1.05;
  const px = v => m.l + (v / xMax) * (W - m.l - m.r);
  const py = v => H - m.b - (v / yMax) * (H - m.t - m.b);
  const ticks = n => Array.from({ length: n + 1 }, (_, i) => i / n);
  const gx = ticks(5).map(t => `<line class="grid-line" x1="${px(t * xMax)}" y1="${m.t}" x2="${px(t * xMax)}" y2="${H - m.b}"/>
      <text x="${px(t * xMax)}" y="${H - m.b + 16}" text-anchor="middle">${Math.round(t * xMax).toLocaleString()}</text>`).join("");
  const gy = ticks(5).map(t => `<line class="grid-line" x1="${m.l}" y1="${py(t * yMax)}" x2="${W - m.r}" y2="${py(t * yMax)}"/>
      <text x="${m.l - 8}" y="${py(t * yMax) + 4}" text-anchor="end">${Math.round(t * yMax).toLocaleString()}</text>`).join("");
  const diag = diagonal ? `<line x1="${px(0)}" y1="${py(0)}" x2="${px(Math.min(xMax, yMax))}" y2="${py(Math.min(xMax, yMax))}"
       stroke="var(--ink-3)" stroke-dasharray="5 5" stroke-width="1.2"/>` : "";
  const dots = rows.map(r => `<circle class="dot" cx="${px(x(r))}" cy="${py(y(r))}" r="5.5" fill="${color(r)}"
       data-tip="${esc(label(r))}"/>`).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    ${gx}${gy}${diag}${dots}
    <text x="${(W + m.l) / 2}" y="${H - 8}" text-anchor="middle">${esc(xLabel)}</text>
    <text transform="rotate(-90 14 ${H / 2})" x="14" y="${H / 2}" text-anchor="middle">${esc(yLabel)}</text>
  </svg>`;
}

function barRows(items, { label, value, format = v => v.toFixed(0) }) {
  const max = Math.max(...items.map(value), 1);
  return items.map(it => `<div class="bar-row"><div>${esc(label(it))}</div>
    <div class="track"><div class="fill" style="width:${(value(it) / max * 100).toFixed(1)}%"></div></div>
    <div class="num small" style="text-align:right">${format(value(it))}</div></div>`).join("");
}


/* One plain sentence per page, so nobody has to decode the charts to know why
   they are looking at it. */
const PLAIN = {
  overview: "Start here. The five numbers below summarise the market; anything worth acting on is called out under “What this says”.",
  catalogue: "Every tile we can see published, from us and from competitors. Use the filters or just type in the search box.",
  compare: "Pick a size and see what each brand sells in it, side by side, with their published prices.",
  pricing: "Where our published prices sit against competitors and against what each tile’s specification is worth. The table is sorted by how much money is on the table.",
  marketing: "How visible each brand is in public — audience, content and website features — and where global leaders are ahead of us.",
  global: "What the world is buying and launching, taken from a global retailer that publishes its own best sellers.",
  gaps: "Specifications competitors sell that we do not. Darker cells mean we hold more of that part of the market.",
  audit: "Proof that every price shown is real: where it came from, how its unit was worked out, and a live re-check against the source.",
  sources: "Every website behind the numbers, what each one gives us, and what we deliberately left out.",
};
function plain(key) {
  const text = PLAIN[key];
  return text ? `<div class="plain"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <circle cx="12" cy="12" r="9"/><path d="M12 16v-5M12 8h.01"/></svg><div>${text}</div></div>` : "";
}

/* Shown once, until dismissed. localStorage can throw in private windows. */
function guideCard() {
  let seen = false;
  try { seen = localStorage.getItem("tileiq-guide") === "done"; } catch (e) { seen = false; }
  if (seen) return "";
  return `<div class="card guide" id="guide">
    <button class="dismiss" id="guide-x">Hide</button>
    <h2>New here? Three places to start</h2>
    <div class="steps">
      <div class="step" data-go="pricing"><b>1 · Are we priced right?</b>
        <span>Published prices against competitors, and the discounts that give away the most.</span></div>
      <div class="step" data-go="gaps"><b>2 · What are we missing?</b>
        <span>Sizes and designs competitors sell that we do not.</span></div>
      <div class="step" data-go="marketing"><b>3 · How visible are we?</b>
        <span>Our audience and website against the global leaders.</span></div>
    </div>
  </div>`;
}


/* Price ladder: the market's price per size, from audited prices only. */
function priceLadder() {
  const priced = DATA.catalog.filter(p => p.p != null && p.g !== "Global" && p.sz);
  const bySize = {};
  priced.forEach(p => { (bySize[p.sz] = bySize[p.sz] || []).push(p); });
  const rows = Object.entries(bySize)
    .map(([sz, list]) => ({
      sz,
      n: list.length,
      ours: median(list.filter(isOurs).map(p => p.p)),
      others: median(list.filter(p => !isOurs(p)).map(p => p.p)),
      lo: Math.min(...list.map(p => p.p)),
      hi: Math.max(...list.map(p => p.p)),
    }))
    .filter(r => r.n >= 2)
    .sort((a, b) => (b.ours || b.others || 0) - (a.ours || a.others || 0));
  if (!rows.length) return "";
  const max = Math.max(...rows.map(r => r.hi));
  return `<div class="card">
    ${rows.map(r => `<div class="ladder-row">
      <div class="lab">${esc(r.sz)}<span class="muted small"> · ${r.n}</span></div>
      <div class="track">
        <div class="span" style="left:${(r.lo / max * 100).toFixed(1)}%;width:${((r.hi - r.lo) / max * 100).toFixed(1)}%"></div>
        ${r.others ? `<i class="pin others" style="left:${(r.others / max * 100).toFixed(1)}%"
            data-tip="Competitors' median ${lkr(r.others)}/sqm"></i>` : ""}
        ${r.ours ? `<i class="pin ours" style="left:${(r.ours / max * 100).toFixed(1)}%"
            data-tip="Our median ${lkr(r.ours)}/sqm"></i>` : ""}
      </div>
      <div class="num small">${lkr(r.ours || r.others)}</div>
    </div>`).join("")}
    <div class="legend"><span><i style="background:var(--accent)"></i>our median</span>
      <span><i style="background:var(--s2)"></i>competitor median</span>
      <span><i style="background:rgba(255,255,255,.14)"></i>full published range</span></div>
  </div>`;
}

/* Which colours and design families the market publishes most. */
function designMix() {
  const local = localRows().filter(p => p.lk);
  const glob = DATA.catalog.filter(p => p.g === "Global" && p.lk);
  const keys = [...new Set([...local, ...glob].map(p => p.lk))];
  const rows = keys.map(k => ({
    look: k,
    ours: local.filter(p => isOurs(p) && p.lk === k).length,
    comp: local.filter(p => !isOurs(p) && p.lk === k).length,
    glob: glob.filter(p => p.lk === k).length,
  })).sort((a, b) => (b.ours + b.comp + b.glob) - (a.ours + a.comp + a.glob));
  const share = (v, list) => list ? (v / list * 100) : 0;
  const tO = rows.reduce((s, r) => s + r.ours, 0), tC = rows.reduce((s, r) => s + r.comp, 0),
        tG = rows.reduce((s, r) => s + r.glob, 0);
  return `<div class="card">${table([
    { label: "Design family", get: r => r.look },
    { label: "Our range", n: 1, get: r => `${r.ours} · ${share(r.ours, tO).toFixed(0)}%` },
    { label: "Sri Lankan competitors", n: 1, get: r => `${r.comp} · ${share(r.comp, tC).toFixed(0)}%` },
    { label: "Global range", n: 1, get: r => `${r.glob} · ${share(r.glob, tG).toFixed(0)}%` },
    { label: "Read", get: r => {
        const o = share(r.ours, tO), g = share(r.glob, tG);
        if (!r.ours && g > 4) return "We do not offer this at all";
        if (o < g * 0.6) return "Thinner than the world";
        if (o > g * 1.6) return "Heavier than the world";
        return "In line";
      } },
  ], rows, { preview: rows.length })}</div>`;
}

/* ---------------------------------------------------------------- state */
let q = "";
const state = { brands: new Set(), sizes: new Set(), finishes: new Set(), looks: new Set(), priced: false, global: false };

function searchMatch(p) {
  if (!q) return true;
  const hay = `${p.n} ${p.b} ${p.sz} ${p.f} ${p.lk} ${p.bd} ${p.cl || ""}`.toLowerCase();
  return q.split(/\s+/).every(t => hay.includes(t));
}
function localRows() { return DATA.catalog.filter(p => p.g !== "Global"); }

/* ---------------------------------------------------------------- views */
const views = {};

views.overview = () => {
  const m = DATA.meta, cat = DATA.catalog, disc = DATA.discount, trends = DATA.trends.look || [];
  const local = localRows();
  const priced = cat.filter(p => p.p != null);
  const topTrend = trends[0];
  const audit = DATA.audit || [];
  const errors = audit.filter(a => a.severity === "error").reduce((s, a) => s + a.products, 0);

  const brandCounts = {};
  local.forEach(p => { brandCounts[p.b] = (brandCounts[p.b] || 0) + 1; });
  const brandList = Object.entries(brandCounts).sort((a, b) => b[1] - a[1]);

  const ourPriced = priced.filter(isOurs);
  const medOurs = median(ourPriced.map(p => p.p));
  const idx = median(DATA.position.map(r => r.index_sell));
  const deep = DATA.discount.filter(d => d.verdict && d.verdict !== "In line");

  return `
  <h1>Market overview</h1>
  ${plain("overview")}
  ${guideCard()}
  <p class="muted small" style="margin:6px 0 18px">Rocell and Lanka Tiles against the Sri Lankan market and a global
    design benchmark. Built entirely from public web pages — every figure traces to a source link.</p>

  <div class="grid cols-5">
    ${kpi("Products tracked", cat.length.toLocaleString(), `${local.length.toLocaleString()} Sri Lanka · ${(cat.length - local.length).toLocaleString()} global`)}
    ${kpi("Audited prices", priced.length.toLocaleString(), `${DATA.units.length} sources, unit verified`)}
    ${kpi("Our median price", lkr(medOurs), "per sqm, published Rocell prices")}
    ${kpi("Vs published competitors", idx ? idx.toFixed(2) + "×" : "—",
      idx ? `on ${DATA.position.length} SKUs with a comparable published price` : "no comparable prices published")}
    ${kpi("Prices worth a look", deep.length, "deep discounts or below spec value")}
  </div>

  <div class="section-title"><h2>Range by brand</h2><span class="muted small">Sri Lankan market</span></div>
  <div class="card">${barRows(brandList, { label: b => b[0], value: b => b[1], format: v => v.toLocaleString() })}</div>

  <div class="grid cols-2" style="margin-top:14px">
    <div class="card">
      <h2>Where price is leaking</h2>
      <h3>Published offer price vs the tile's own specification value</h3>
      ${deep.length ? `<div style="margin-top:12px">${barRows(deep.slice(0, 6), {
        label: d => `${d.name}`.slice(0, 26), value: d => d.give_away_lkr_sqm || 0, format: v => lkr(v)
      })}</div><p class="small muted">${deep.length} products are discounted deeply or sell below what their
        size, body and finish command across our own range.</p>`
      : `<p class="muted small" style="margin-top:10px">Nothing is out of line.</p>`}
    </div>
    <div class="card">
      <h2>Global design demand</h2>
      <h3>What sells and launches worldwide vs our range</h3>
      ${topTrend ? `<div style="margin-top:12px">${barRows(trends.slice(0, 6), {
        label: t => t.look, value: t => t.demand_index || 0, format: v => v.toFixed(2) + "×"
      })}</div><p class="small muted">Demand index — share of global best sellers, 1.00 = average.
        <b>${topTrend.look}</b> is ${(topTrend.demand_index || 0).toFixed(1)}× while we hold
        ${((topTrend.our_share || 0) * 100).toFixed(0)}% of our range there.</p>` : ""}
    </div>
  </div>

  <div class="section-title"><h2>Newest in the market</h2><span class="muted small">latest Rocell listings and global new arrivals</span></div>
  <div id="ov-new"></div>`;
};

views.overviewAfter = () => {
  const newOnes = [...DATA.catalog.filter(p => p.dt).sort((a, b) => (b.dt || "").localeCompare(a.dt || "")).slice(0, 6),
                   ...DATA.catalog.filter(p => p.new).slice(0, 6)];
  tileGrid($("#ov-new"), newOnes, { step: 12 });
};

views.catalogue = () => {
  const rows = filtered();
  return `
  <h1>Catalogue</h1>
  ${plain("catalogue")}
  <p class="muted small" style="margin:6px 0 16px">Every tile we can see published, mapped to one set of attributes.</p>
  ${filterBar()}
  <div id="cat-grid"></div>`;
};
views.catalogueAfter = () => { tileGrid($("#cat-grid"), filtered()); bindFilters(); };

function filterBar() {
  const cat = state.global ? DATA.catalog : localRows();
  const opts = (key, set) => [...new Set(cat.map(p => p[key]).filter(Boolean))].sort()
    .map(v => `<option ${set.has(v) ? "selected" : ""}>${esc(v)}</option>`).join("");
  return `<div class="controls">
    <select id="f-brand" multiple size="1" data-key="brands" style="min-width:150px">${opts("b", state.brands)}</select>
    <select id="f-size" multiple size="1" data-key="sizes" style="min-width:120px">${opts("sz", state.sizes)}</select>
    <select id="f-finish" multiple size="1" data-key="finishes" style="min-width:130px">${opts("f", state.finishes)}</select>
    <select id="f-look" multiple size="1" data-key="looks" style="min-width:130px">${opts("lk", state.looks)}</select>
    <span class="chip ${state.priced ? "on" : ""}" id="t-priced">Priced only</span>
    <span class="chip ${state.global ? "on" : ""}" id="t-global">Include global</span>
    <button id="f-clear">Clear</button>
  </div>`;
}
function bindFilters() {
  $$("select[data-key]").forEach(sel => sel.addEventListener("change", () => {
    state[sel.dataset.key] = new Set([...sel.selectedOptions].map(o => o.value));
    render();
  }));
  const t1 = $("#t-priced"), t2 = $("#t-global"), c = $("#f-clear");
  if (t1) t1.onclick = () => { state.priced = !state.priced; render(); };
  if (t2) t2.onclick = () => { state.global = !state.global; render(); };
  if (c) c.onclick = () => {
    ["brands", "sizes", "finishes", "looks"].forEach(k => state[k] = new Set());
    state.priced = state.global = false; render();
  };
}
function filtered() {
  let rows = state.global ? DATA.catalog : localRows();
  rows = rows.filter(searchMatch);
  if (state.brands.size) rows = rows.filter(p => state.brands.has(p.b));
  if (state.sizes.size) rows = rows.filter(p => state.sizes.has(p.sz));
  if (state.finishes.size) rows = rows.filter(p => state.finishes.has(p.f));
  if (state.looks.size) rows = rows.filter(p => state.looks.has(p.lk));
  if (state.priced) rows = rows.filter(p => p.p != null);
  return rows;
}

views.compare = () => {
  const local = localRows();
  const sizes = [...new Set(local.map(p => p.sz))].filter(Boolean).sort();
  const finishes = ["Any", ...new Set(local.map(p => p.f).filter(Boolean))];
  const looks = ["Any", ...new Set(local.map(p => p.lk).filter(Boolean))];
  const sz = state.cmpSize || (sizes.includes("600x1200") ? "600x1200" : sizes[0]);
  return `
  <h1>Head to head</h1>
  ${plain("compare")}
  <p class="muted small" style="margin:6px 0 16px">The same specification across every brand that publishes it.</p>
  <div class="controls">
    <select id="c-size">${sizes.map(s => `<option ${s === sz ? "selected" : ""}>${s}</option>`).join("")}</select>
    <select id="c-finish">${finishes.map(f => `<option ${f === state.cmpFinish ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>
    <select id="c-look">${looks.map(l => `<option ${l === state.cmpLook ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
  </div>
  <div id="cmp"></div>`;
};
views.compareAfter = () => {
  const bind = (id, key) => { const el = $(id); if (el) el.onchange = () => { state[key] = el.value; render(); }; };
  bind("#c-size", "cmpSize"); bind("#c-finish", "cmpFinish"); bind("#c-look", "cmpLook");
  const sz = state.cmpSize || "600x1200";
  let rows = localRows().filter(p => p.sz === sz);
  if (state.cmpFinish && state.cmpFinish !== "Any") rows = rows.filter(p => p.f === state.cmpFinish);
  if (state.cmpLook && state.cmpLook !== "Any") rows = rows.filter(p => p.lk === state.cmpLook);
  const brands = [...new Set(rows.map(p => p.b))].sort((a, b) => (OURS.includes(b) ? 1 : 0) - (OURS.includes(a) ? 1 : 0));
  $("#cmp").innerHTML = `<div class="grid" style="grid-template-columns:repeat(${Math.min(brands.length || 1, 4)},minmax(0,1fr))">
    ${brands.map(b => {
      const list = rows.filter(p => p.b === b).sort((x, y) => (x.p ?? 1e9) - (y.p ?? 1e9)).slice(0, 4);
      const priced = list.filter(p => p.p != null).map(p => p.p);
      return `<div><div class="section-title" style="margin:0 0 10px"><h2>${esc(b)}</h2></div>
        <div class="muted small" style="margin-bottom:10px">${rows.filter(p => p.b === b).length} products${priced.length ? ` · median ${lkr(median(priced))}/sqm` : " · no public price"}</div>
        <div class="tiles" style="grid-template-columns:1fr">${list.map(p => tile(p)).join("") || `<div class="empty small">Nothing in this spec.</div>`}</div></div>`;
    }).join("") || `<div class="empty">No products in this specification.</div>`}</div>`;
};

views.pricing = () => {
  const pos = DATA.position, disc = DATA.discount;
  const flagged = disc.filter(d => d.verdict && d.verdict !== "In line")
                      .sort((a, b) => (b.give_away_lkr_sqm || 0) - (a.give_away_lkr_sqm || 0));
  const deep = disc.filter(d => d.discount_pct >= 20);
  const idx = median(pos.map(p => p.index_sell));
  return `
  <h1>Pricing intelligence</h1>
  ${plain("pricing")}
  <p class="muted small" style="margin:6px 0 16px">Built from published prices only. Two reference points:
    a competitor's published price for a comparable tile where one exists, and what a specification is worth
    across our own range (hedonic model, R² ${(DATA.meta.fair_r2 || 0).toFixed(2)} on ${DATA.meta.fair_n} audited prices).</p>

  <div class="grid cols-4">
    ${kpi("Audited own prices", disc.length, "Rocell, published list and offer")}
    ${kpi("On deep discount", deep.length, "20% or more off list, published")}
    ${kpi("Vs published competitors", idx ? idx.toFixed(2) + "×" : "—",
      `${pos.length} SKUs have a comparable published competitor price`)}
    ${kpi("Flagged for review", flagged.length, "deep discount or below spec value")}
  </div>

  <div class="section-title"><h2>Published discount, and what it leaves on the table</h2>
    <span class="muted small">sorted by value given away per sqm</span></div>
  ${flagged.length ? table([
    { label: "Product", get: r => r.name },
    { label: "Spec", get: r => `${r.size_mm} ${r.finish || ""} ${r.look || ""}`.trim() },
    { label: "List", n: 1, get: r => lkr(r.our_list) },
    { label: "Selling", n: 1, get: r => lkr(r.our_sell) },
    { label: "Discount", n: 1, get: r => pct(r.discount_pct, 0) },
    { label: "Spec value", n: 1, get: r => lkr(r.fair_value) },
    { label: "Vs spec value", n: 1, get: r => r.vs_fair_pct == null ? "—" : pct(r.vs_fair_pct, 0) },
    { label: "Competitor", n: 1, get: r => lkr(r.benchmark) },
    { label: "Give-away/sqm", n: 1, get: r => lkr(r.give_away_lkr_sqm) },
    { label: "Read", get: r => r.verdict },
    { label: "Source", raw: 1, get: r => r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">open ↗</a>` : "—" },
  ], flagged.slice(0, 60)) : `<div class="empty">Nothing out of line.</div>`}

  ${pos.length ? `<div class="section-title"><h2>Our price vs comparable published competitor prices</h2>
    <span class="muted small">${pos.length} SKUs · above the line = we are priced higher</span></div>
  <div class="card" id="pos-chart"></div>
  <p class="small muted" style="margin-top:8px">Coverage is limited by what competitors publish: among Sri Lankan
    tile sellers only Rocell and Mascons put prices online, so this compares premium Rocell tiles with a budget
    importer. Treat the ratio as a floor-to-ceiling spread, not a like-for-like premium.</p>` : ""}

  <div class="section-title"><h2>Price ladder by size</h2>
    <span class="muted small">published prices only, per sqm</span></div>
  ${priceLadder()}

  <div class="section-title"><h2>What the market pays for each attribute</h2>
    <span class="muted small">hedonic model on audited prices</span></div>
  <div class="card">${barRows((DATA.premiums || []).slice().sort((a, b) => b.premium_pct - a.premium_pct).slice(0, 12),
    { label: p => `${p.value}`, value: p => p.premium_pct, format: v => (v > 0 ? "+" : "") + v.toFixed(0) + "%" })}</div>`;
};

views.pricingAfter = () => {
  const el = $("#pos-chart");
  if (!el) return;
  const pos = DATA.position;
  el.innerHTML = scatter(pos, {
    x: r => r.benchmark, y: r => r.our_sell, diagonal: true,
    color: r => r.brand === "Rocell" ? PALETTE[0] : PALETTE[1],
    xLabel: "Comparable competitor price, LKR/sqm", yLabel: "Our selling price, LKR/sqm",
    label: r => `<b>${esc(r.name)}</b><br>${esc(r.brand)} · ${esc(r.size_mm)} ${esc(r.finish || "")}<br>
      ours ${lkr(r.our_sell)} vs market ${lkr(r.benchmark)}<br>index ${r.index_sell.toFixed(2)}×`,
  }) + `<div class="legend"><span><i style="background:${PALETTE[0]}"></i>Rocell</span>
        <span><i style="background:${PALETTE[1]}"></i>Lanka Tiles</span>
        <span><i style="background:var(--ink-3)"></i>dashed = level with market</span></div>`;
  hover(el);
};

views.global = () => {
  const dim = state.trendDim || "look";
  const trends = DATA.trends[dim] || [];
  const g = DATA.catalog.filter(p => p.g === "Global");
  const bs = g.filter(p => p.bs).length, nw = g.filter(p => p.new).length;
  return `
  <h1>Global design demand</h1>
  ${plain("global")}
  <p class="muted small" style="margin:6px 0 16px">Benchmarked against The Tile Shop (US), which publishes its own
    best-seller and new-arrival flags. Those flags are real demand evidence; US prices are shown for relative
    comparison only, never as a Sri Lankan price target.</p>
  <div class="grid cols-4">
    ${kpi("Designs tracked", g.length.toLocaleString(), "global benchmark set")}
    ${kpi("Marked best sellers", bs, "retailer's own flag")}
    ${kpi("Marked new arrivals", nw, "where the market is heading")}
    ${kpi("Median US price", usd(median(g.map(p => p.usd).filter(Boolean))), "per sqm, US retail")}
  </div>
  <div class="controls" style="margin-top:16px">
    ${["look", "size_mm", "finish", "body"].map(d => `<span class="chip ${d === dim ? "on" : ""}" data-dim="${d}">
      ${({ look: "Design family", size_mm: "Size", finish: "Finish", body: "Body" })[d]}</span>`).join("")}
  </div>
  ${trends.length ? table([
    { label: ({ look: "Design", size_mm: "Size", finish: "Finish", body: "Body" })[dim], get: r => r[dim] },
    { label: "Global SKUs", n: 1, get: r => r.global_skus },
    { label: "Best-seller share", n: 1, get: r => pct((r.bestseller_share || 0) * 100, 1) },
    { label: "Demand index", n: 1, get: r => (r.demand_index || 0).toFixed(2) + "×" },
    { label: "Launch index", n: 1, get: r => (r.launch_index || 0).toFixed(2) + "×" },
    { label: "Our SKUs", n: 1, get: r => r.our_skus || 0 },
    { label: "Our coverage", n: 1, get: r => (r.coverage_ratio || 0).toFixed(2) + "×" },
    { label: "Read", get: r => r.verdict },
  ], trends) : `<div class="empty">Not enough global data in this breakdown.</div>`}

  <div class="section-title"><h2>Design mix: our range against the world</h2>
    <span class="muted small">share of each catalogue by design family</span></div>
  ${designMix()}

  <div class="section-title"><h2>What is selling globally</h2>
    <span class="muted small">best sellers and new arrivals in ${esc(trends[0]?.[dim] || "")}</span></div>
  <div id="g-examples"></div>`;
};
views.globalAfter = () => {
  $$("[data-dim]").forEach(c => c.onclick = () => { state.trendDim = c.dataset.dim; render(); });
  const dim = state.trendDim || "look";
  const top = (DATA.trends[dim] || [])[0];
  if (!top) return;
  const key = { look: "lk", size_mm: "sz", finish: "f", body: "bd" }[dim];
  const rows = DATA.catalog.filter(p => p.g === "Global" && p[key] === top[dim])
    .sort((a, b) => (b.bs ? 2 : 0) + (b.new ? 1 : 0) - ((a.bs ? 2 : 0) + (a.new ? 1 : 0)));
  tileGrid($("#g-examples"), rows.slice(0, 12), { step: 12 });
};

views.marketing = () => {
  const rows = DATA.marketing || [], feats = DATA.marketing_features || [], heads = DATA.marketing_headlines || [];
  if (!rows.length) return `<h1>Marketing</h1><div class="empty">No marketing data in this build.</div>`;
  const ours = rows.filter(r => r.is_ours);
  const leaders = rows.filter(r => r.group === "Global");
  const fmt = v => v == null ? "—" : Number(v).toLocaleString();
  const bestOurs = ours.slice().sort((a, b) => (b.audience || 0) - (a.audience || 0))[0] || {};
  const topLeader = leaders.slice().sort((a, b) => (b.audience || 0) - (a.audience || 0))[0] || {};

  return `
  <h1>Marketing</h1>
  ${plain("marketing")}
  <p class="muted small" style="margin:6px 0 16px">What each brand publishes in the open: audience on channels that
    report their own numbers, how much editorial they publish, which digital features their sites offer, and how
    heavily they discount in public.</p>

  <div class="grid cols-4">
    ${kpi("Our best " + term("reach"), fmt(bestOurs.audience), `${esc(bestOurs.brand || "")} · LinkedIn + YouTube followers`)}
    ${kpi("Global leader reach", fmt(topLeader.audience), `${esc(topLeader.brand || "")} · the bar to aim at`)}
    ${kpi("Gap to leader", bestOurs.audience && topLeader.audience ? (topLeader.audience / bestOurs.audience).toFixed(0) + "×" : "—", "how many times larger their audience is")}
    ${kpi("Site features we offer", `${ours.reduce((m, r) => Math.max(m, r.feature_count || 0), 0)} of ${feats.length}`, "vs global leaders below")}
  </div>

  ${heads.length ? `<div class="section-title"><h2>What this says</h2></div>
    <div class="card">${heads.map(h => `<div class="lead-row"><b>${esc(h.point)}</b>
      <span>${esc(h.text)}</span></div>`).join("")}</div>` : ""}

  <div class="section-title"><h2>Audience and publishing, brand by brand</h2>
    <span class="muted small">LinkedIn and YouTube only — they publish their numbers openly</span></div>
  ${table([
    { label: "Brand", get: r => r.brand },
    { label: "Who", get: r => r.group },
    { label: "LinkedIn followers", n: 1, get: r => fmt(r.linkedin_followers) },
    { label: "YouTube subscribers", n: 1, get: r => fmt(r.youtube_subscribers) },
    { label: "Lifetime video views", n: 1, get: r => fmt(r.youtube_views) },
    { label: "Editorial pages", n: 1, get: r => fmt(r.content_pages) },
    { label: "Site features", n: 1, get: r => r.feature_count ? r.feature_count : "not readable" },
    { label: "Vs leaders", n: 1, get: r => r.audience_vs_leaders == null ? "—" : r.audience_vs_leaders + "×" },
  ], rows, { preview: rows.length })}

  <div class="grid cols-2" style="margin-top:18px">
    <div class="card"><h2>Audience</h2><h3>LinkedIn + YouTube followers</h3>
      <div style="margin-top:12px">${barRows(rows.filter(r => r.audience).sort((a, b) => b.audience - a.audience),
        { label: r => r.brand, value: r => r.audience, format: v => fmt(v) })}</div></div>
    <div class="card"><h2>Editorial output</h2><h3>blog, inspiration and project pages published</h3>
      <div style="margin-top:12px">${barRows(rows.filter(r => r.content_pages).sort((a, b) => b.content_pages - a.content_pages),
        { label: r => r.brand, value: r => r.content_pages, format: v => fmt(v) })}</div></div>
  </div>

  <div class="section-title"><h2>Website features: us versus the global leaders</h2></div>
  ${table([
    { label: "Feature", get: r => r.feature },
    { label: "We offer it", raw: 1, get: r => r.we_have ? `<span class="badge good">yes</span>` : `<span class="badge bad">no</span>` },
    { label: "Global leaders with it", n: 1, get: r => `${r.leaders_with} of ${leaders.length}` },
    { label: "Read", get: r => r.verdict },
  ], feats, { preview: feats.length })}

  <div class="section-title"><h2>Public discounting</h2>
    <span class="muted small">measured from the published prices in this build</span></div>
  ${table([
    { label: "Brand", get: r => r.brand },
    { label: "Priced products seen", n: 1, get: r => fmt(r.priced_skus) },
    { label: "Share on offer", n: 1, get: r => r.on_offer_pct == null ? "—" : r.on_offer_pct.toFixed(0) + "%" },
    { label: "Average discount", n: 1, get: r => r.avg_discount_pct == null ? "—" : r.avg_discount_pct.toFixed(0) + "%" },
    { label: "Deepest discount", n: 1, get: r => r.deepest_discount_pct == null ? "—" : r.deepest_discount_pct.toFixed(0) + "%" },
  ], rows.filter(r => r.priced_skus), { preview: 10 })}

  <div class="card" style="margin-top:18px">
    <h2>What we cannot see, and why</h2>
    <p class="small muted" style="margin-top:8px">Facebook, Instagram and TikTok require a login before they show
      follower counts, so no number for them appears here rather than a guess. Ad spend, reach and engagement are
      private everywhere. Everything above comes from pages anyone can open, and each brand row links to its sources.</p>
  </div>`;
};

views.gaps = () => {
  const gaps = DATA.gaps.filter(g => g.status !== "Covered");
  const local = localRows();
  const looks = [...new Set(local.map(p => p.lk).filter(Boolean))];
  const sizes = [...new Set(local.map(p => p.sz).filter(Boolean))]
    .map(s => [s, local.filter(p => p.sz === s).length]).sort((a, b) => b[1] - a[1]).slice(0, 10).map(s => s[0]);
  const cell = (lk, sz) => {
    const all = local.filter(p => p.lk === lk && p.sz === sz);
    const mine = all.filter(isOurs);
    const share = all.length ? mine.length / all.length : null;
    const bg = share == null ? "rgba(255,255,255,.03)"
      : `color-mix(in oklab, #38bdf8 ${Math.round(share * 85 + 8)}%, #0b1118)`;
    return `<div class="cell" style="background:${bg}" data-tip="<b>${esc(lk)} · ${esc(sz)}</b><br>
      V One ${mine.length} of ${all.length} products in the market">${all.length ? `${mine.length}/${all.length}` : "—"}</div>`;
  };
  return `
  <h1>Assortment gaps</h1>
  ${plain("gaps")}
  <p class="muted small" style="margin:6px 0 16px">Specifications competitors publish that Rocell and Lanka Tiles do not cover.</p>
  <div class="card" id="heat-card">
    <h2>Our share of the market's range</h2>
    <h3>V One products ÷ all published products, by design family and size</h3>
    <div class="heat" style="grid-template-columns:130px repeat(${sizes.length}, 1fr); margin-top:14px">
      <div class="hd"></div>${sizes.map(s => `<div class="hd">${s}</div>`).join("")}
      ${looks.map(lk => `<div class="hd" style="justify-content:start">${esc(lk)}</div>
        ${sizes.map(sz => cell(lk, sz)).join("")}`).join("")}
    </div>
  </div>
  <div class="section-title"><h2>Ranked gaps</h2><span class="muted small">${gaps.length} specifications</span></div>
  ${table([
    { label: "Size", get: r => r.size_mm },
    { label: "Body", get: r => r.body },
    { label: "Finish", get: r => r.finish },
    { label: "Look", get: r => r.look },
    { label: "Status", get: r => r.status },
    { label: "Who sells it", get: r => r.competitors },
    { label: "Their SKUs", n: 1, get: r => r.competitor_skus },
    { label: "Score", n: 1, get: r => (r.gap_score || 0).toFixed(1) },
  ], gaps.slice(0, 60))}`;
};
views.gapsAfter = () => { const c = $("#heat-card"); if (c) hover(c); };

views.audit = () => {
  const findings = DATA.audit || [], units = DATA.units || [], spot = DATA.spot || [];
  const cat = DATA.catalog;
  const priced = cat.filter(p => p.p != null);
  const high = priced.filter(p => p.pc === "high").length;
  const med = priced.filter(p => p.pc === "medium").length;
  const unres = cat.filter(p => p.lp != null && p.p == null).length;
  const matched = spot.filter(s => s.result === "match").length;
  return `
  <h1>Price audit</h1>
  ${plain("audit")}
  <p class="muted small" style="margin:6px 0 16px">Tile sites publish a number and rarely say <i>per what</i>.
    Nothing here is guessed: a unit is either stated by the source or inferred from that source's own data, with the
    evidence recorded. Anything unresolved is excluded from every comparison.</p>

  <div class="grid cols-4">
    ${kpi("Prices in use", priced.length, "converted to LKR per sqm")}
    ${kpi("Unit stated by source", high, "highest confidence")}
    ${kpi("Unit inferred + audited", med, "with evidence, below")}
    ${kpi("Excluded as unverified", unres, "never shown as a comparison")}
  </div>

  <div class="section-title"><h2>How each source's unit was established</h2></div>
  ${table([
    { label: "Source", get: r => r.source },
    { label: "Priced products", n: 1, get: r => r.priced_products },
    { label: "Unit used", get: r => (r.unit || "unresolved").replace("per_", "per ") },
    { label: "Formats seen", n: 1, get: r => r.formats ?? "—" },
    { label: "Slope", n: 1, get: r => r.slope ?? "—" },
    { label: "R²", n: 1, get: r => r.r2 ?? "—" },
    { label: "Method / evidence", get: r => r.method },
  ], units)}
  <p class="small muted" style="margin-top:8px">A slope near 1 means price tracks tile area, so the number is per tile;
    near 0 means it is already per square metre. Where the fit is inconclusive, the reading is only accepted if the
    alternative would imply an impossible price per sqm.</p>

  <div class="section-title"><h2>Automated checks</h2></div>
  ${findings.length ? table([
    { label: "Severity", raw: 1, get: r => `<span class="badge ${r.severity === "error" ? "bad" : r.severity === "warning" ? "warn" : ""}">${r.severity}</span>` },
    { label: "Check", get: r => r.check },
    { label: "Products", n: 1, get: r => r.products },
    { label: "What it means", get: r => r.detail },
    { label: "Example", raw: 1, get: r => r.example ? `<a href="${esc(r.example)}" target="_blank" rel="noopener">open ↗</a>` : "—" },
  ], findings) : `<div class="card">No issues found.</div>`}

  <div class="section-title"><h2>Live spot check</h2>
    <span class="muted small">${spot.length ? `${matched}/${spot.length} matched on last run` : "run the pipeline to perform one"}</span></div>
  <p class="small muted">Random source pages are re-fetched and re-parsed, then compared with what we stored. This is
    what catches a site changing its layout, or a price moving since the last crawl.</p>
  ${spot.length ? table([
    { label: "Product", get: r => r.name },
    { label: "Source", get: r => r.source },
    { label: "Stored", n: 1, get: r => lkr(r.stored_price) },
    { label: "Live now", n: 1, get: r => lkr(r.live_price) },
    { label: "Result", raw: 1, get: r => `<span class="badge ${r.result === "match" ? "good" : "warn"}">${r.result}</span>` },
    { label: "Page", raw: 1, get: r => `<a href="${esc(r.url)}" target="_blank" rel="noopener">open ↗</a>` },
  ], spot) : ""}

  <div class="section-title"><h2>Every price, with its evidence</h2></div>
  ${table([
    { label: "Product", get: r => r.n },
    { label: "Brand", get: r => r.b },
    { label: "Spec", get: r => spec(r) },
    { label: "As published", n: 1, get: r => r.praw || (r.lp != null ? lkr(r.lp) : "—") },
    { label: "Unit", get: r => (r.pu || "unresolved").replace("per_", "per ") },
    { label: "Per sqm", n: 1, get: r => lkr(r.p) },
    { label: "Confidence", raw: 1, get: r => confBadge(r) },
    { label: "How we know", get: r => r.ub },
    { label: "Source", raw: 1, get: r => r.u ? `<a href="${esc(r.u)}" target="_blank" rel="noopener">open ↗</a>` : "—" },
  ], DATA.catalog.filter(p => p.lp != null).slice(0, 300))}`;
};

views.sources = () => {
  const m = DATA.meta;
  const rows = m.sources || [];
  return `
  <h1>Sources</h1>
  ${plain("sources")}
  <p class="muted small" style="margin:6px 0 16px">Public pages only. robots.txt respected, one request per second,
    every response cached, every price stored with its URL and observation date.</p>
  ${table([
    { label: "Source", get: r => r.source },
    { label: "Products", n: 1, get: r => r.products },
    { label: "With audited price", n: 1, get: r => r.priced },
  ], rows)}
  <div class="section-title"><h2>What each source gives us</h2></div>
  <div class="grid cols-2">
    <div class="card"><h2>Sri Lanka</h2><ul class="small muted" style="line-height:1.9;padding-left:18px">
      <li><b>rocell.com</b> — full Rocell catalogue: type, finish, size, design family, colour, launch date, images</li>
      <li><b>buyrocell.com</b> — live Rocell list and offer prices</li>
      <li><b>lankatiles.com</b> — Lanka Tiles catalogue and images (no public prices)</li>
      <li><b>macktiles.com</b> — Macktiles catalogue and images (no public prices)</li>
      <li><b>mascons.com</b> — importer/retailer with published prices</li>
    </ul></div>
    <div class="card"><h2>Global</h2><ul class="small muted" style="line-height:1.9;padding-left:18px">
      <li><b>tileshop.com</b> — global design range with the retailer's own best-seller, new-arrival and clearance flags,
        full spec sheets and images</li>
    </ul>
    <h2 style="margin-top:14px">Checked and excluded</h2><ul class="small muted" style="line-height:1.9;padding-left:18px">
      <li><b>ikman.lk / Daraz</b> — classifieds: prices exist but the unit is ambiguous per listing</li>
      <li><b>davinciceramics.com</b> — importer, but publishes neither prices nor tile sizes</li>
      <li><b>naveen.lk</b> — site is a placeholder page</li>
      <li><b>stockpile.lk</b> — Magento storefront, no usable product feed</li>
    </ul></div>
  </div>`;
};

/* ---------------------------------------------------------------- utils */
function median(a) { const v = a.filter(x => x != null).sort((x, y) => x - y); return v.length ? v[Math.floor(v.length / 2)] : null; }
function mean(a) { const v = a.filter(x => x != null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; }

/* ---------------------------------------------------------------- router */
let current = "overview";
function render() {
  view.innerHTML = views[current]();
  const after = views[current + "After"];
  if (after) after();
  bindMore();
  hover(view);
  const gx = $("#guide-x");
  if (gx) gx.onclick = () => {
    try { localStorage.setItem("tileiq-guide", "done"); } catch (e) { /* private window */ }
    const g = $("#guide"); if (g) g.remove();
  };
  $$("[data-go]").forEach(el => el.onclick = () => go(el.dataset.go));
  $$(".navlink").forEach(a => a.classList.toggle("on", a.dataset.view === current));
  const n = current === "catalogue" ? filtered().length : DATA.catalog.length;
  $("#count-badge").textContent = `${n.toLocaleString()} products`;
}
function go(v) { current = v; location.hash = "#/" + v; window.scrollTo(0, 0); render(); }

async function boot() {
  const names = ["meta", "catalog", "position", "discount", "gaps", "audit", "units", "spot", "trends", "premiums",
    "recommendations", "marketing", "marketing_features", "marketing_headlines"];
  // no-cache: always revalidate, so a rebuilt dataset is never served stale.
  const loaded = await Promise.all(names.map(n =>
    fetch(`data/${n}.json`, { cache: "no-cache" }).then(r => r.ok ? r.json() : null).catch(() => null)));
  names.forEach((n, i) => DATA[n] = loaded[i] ?? (n === "meta" || n === "trends" ? {} : []));
  $("#build-stamp").textContent = "Built " + (DATA.meta.built_at || "").replace("T", " ");
  $$(".navlink").forEach(a => a.onclick = () => go(a.dataset.view));
  addEventListener("hashchange", () => {
    const v = location.hash.replace("#/", "") || "overview";
    if (views[v] && v !== current) { current = v; render(); }
  });
  const qEl = $("#q");
  let t;
  qEl.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      q = qEl.value.trim().toLowerCase();
      if (q && current !== "catalogue") go("catalogue"); else render();
    }, 140);
  });
  addEventListener("keydown", e => {
    if (e.key === "/" && document.activeElement !== qEl) { e.preventDefault(); qEl.focus(); }
    if (e.key === "Escape") { qEl.value = ""; q = ""; render(); }
  });
  current = location.hash.replace("#/", "") || "overview";
  if (!views[current]) current = "overview";
  render();
}
boot();
})();
