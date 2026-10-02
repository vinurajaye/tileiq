"""Standard tile record: maps any brand's product text into one vocabulary.

Every product, ours or a competitor's, is reduced to the attributes that drive
tile price: size, body, finish, look and application. The rules here are
deliberately plain keyword rules so a product manager can read and extend them.
An LLM extractor can later replace `normalise()` for messy sources (PDF price
lists, flyers); the output shape stays the same.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- size
# Matches "600x600", "600 x 600 mm", "150mm x900mm", "12 x 24 in.", "60X120cm".
# The unit may sit after either dimension.
SIZE_RE = re.compile(
    r"(\d{1,4}(?:\.\d+)?)\s*(mm|cm|in\.?|inch(?:es)?|\")?\s*[x×X\*]\s*"
    r"(\d{1,4}(?:\.\d+)?)\s*(mm|cm|in\.?|inch(?:es)?|\")?", re.I)

# Nominal sizes the market actually trades in (mm, short side first).
STANDARD_SIZES = [
    (75, 150), (100, 300), (100, 400), (100, 600), (150, 600), (150, 900), (200, 200),
    (200, 600), (200, 800), (200, 1200), (250, 400), (250, 750), (300, 300), (300, 450),
    (300, 600), (300, 900), (300, 1200), (400, 400), (400, 600), (400, 800), (450, 450),
    (450, 900), (500, 500), (600, 600), (600, 900), (600, 1200), (750, 750), (800, 800),
    (800, 1200), (800, 1600), (900, 900), (1000, 1000), (1200, 1200), (1200, 1800),
    (1200, 2400), (1600, 3200),
]


def parse_size(*texts: str) -> tuple[int, int] | None:
    """Return (short, long) side in mm, snapped to the nearest standard size."""
    for text in texts:
        if not text:
            continue
        for a, unit_a, b, unit_b in SIZE_RE.findall(str(text)):
            a, b = float(a), float(b)
            unit = (unit_b or unit_a or "").lower().rstrip(".")
            if unit.startswith("in") or unit == '"':
                a, b = a * 25.4, b * 25.4          # US listings quote inches
            # Unmarked numbers: tiles are quoted in cm up to ~200 (60x120, 100x100)
            # and in mm above that (300x600, 600x1200).
            elif unit == "cm" or (not unit and max(a, b) <= 200):
                a, b = a * 10, b * 10
            if not (50 <= min(a, b) and max(a, b) <= 3300):
                continue
            short, long_ = sorted((a, b))
            best = min(STANDARD_SIZES, key=lambda s: abs(s[0] - short) + abs(s[1] - long_))
            if abs(best[0] - short) + abs(best[1] - long_) <= 40:
                return best
            return int(round(short)), int(round(long_))
    return None


def size_label(size: tuple[int, int] | None) -> str:
    return f"{size[0]}x{size[1]}" if size else "Unknown"


def size_class(size: tuple[int, int] | None) -> str:
    if not size:
        return "Unknown"
    area = size[0] * size[1] / 1e6
    if size[1] >= 1600 or area >= 1.4:
        return "Slab / XL"
    if area >= 0.64 or size[1] >= 1200:
        return "Large format"
    if area >= 0.25:
        return "Standard floor"
    return "Small / wall"


# ---------------------------------------------------------------- vocabularies
BODY_RULES = [
    ("Mosaic", r"mosaic"),
    ("Slab", r"\bslab"),
    ("Full body", r"full[\s-]?body|homogeneous|through[\s-]?body"),
    ("Double charge", r"double[\s-]?charge|\bdc\b"),
    ("Soluble salt", r"soluble[\s-]?salt|\bnpsp\b"),
    ("Porcelain polished (PGVT)", r"pgvt|polished glazed vitrified|nano"),
    ("Porcelain (GVT)", r"gvt|glazed vitrified|porcelain|vitrified"),
    ("Ceramic", r"ceramic|wall tile|red body|white body"),
]

FINISH_RULES = [
    ("Structured / anti-slip", r"anti[\s-]?slip|structured|rustic|r1[0-3]\b|grip|outdoor"),
    ("Carving", r"carving|carved|3d"),
    ("Sugar", r"sugar"),
    ("Lappato / semi-polished", r"lappato|semi[\s-]?polish|satin[\s-]?polish|honed"),
    ("Satin", r"satin|silk|velvet|soft"),
    ("Matte", r"\bmatt?e?\b|natural finish|nature matt"),
    ("Gloss / polished", r"gloss|polish|shine|high[\s-]?gloss|mirror"),
]

LOOK_RULES = [
    ("Marble", r"marble|statuario|calacatta|carrara|onyx|travertin|emperador|botticino|"
               r"crema|marfil|armani|bianco|arabescato|satuario|portoro|nero|pietra|picasso"),
    ("Wood", r"wood|oak|teak|walnut|maple|timber|parquet|plank|cedar|ash\b|pine"),
    ("Cement / concrete", r"cement|concrete|beton|urban|industrial|resin|loft"),
    ("Stone", r"stone|slate|granite|rock|quartz|sandstone|limestone|basalt|lava|dolmen|"
              r"pebble|cotto|terracotta|earth"),
    ("Terrazzo", r"terrazzo|terazzo|venetian"),
    ("Decor / pattern", r"deco|pattern|geometric|moroccan|encaustic|hexagon|abstract|motif|"
                        r"highlighter|border|listello|flower|floral"),
    ("Plain colour", r"plain|mono|solid|pure|\bwhite\b|super white|ivory|single colou?r"),
]

APPLICATION_RULES = [
    ("Outdoor", r"outdoor|exterior|garden|parking|pool|driveway|cool roof"),
    ("Floor", r"floor"),
    ("Wall", r"wall|kitchen back|bathroom wall"),
]


def _thickness(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*mm", str(text), re.I)
    return float(m.group(1)) if m else None


def _first(rules, text, default="Unknown"):
    for label, pattern in rules:
        if re.search(pattern, text, re.I):
            return label
    return default


def _all(rules, text):
    return [label for label, pattern in rules if re.search(pattern, text, re.I)]


def normalise(row: dict) -> dict:
    """Map a scraped product row to the standard tile record."""
    a = {k.lower(): str(v) for k, v in (row.get("attributes") or {}).items()}
    name = row.get("name", "")
    everything = " | ".join([name, row.get("categories", ""), row.get("description", "")] +
                            [f"{k}: {v}" for k, v in a.items()])

    size = parse_size(a.get("size", ""), a.get("dimension", ""), row.get("categories", ""),
                      name, row.get("description", ""))

    # Body: explicit type attribute beats keywords elsewhere.
    body_text = " ".join([a.get("type", ""), a.get("surface", ""), row.get("categories", ""), name,
                          row.get("description", "")])
    body = _first(BODY_RULES, body_text)
    # Explicit finish/surface attributes win; fall back to the name, then free text.
    finish = _first(FINISH_RULES, " ".join([a.get("finish", ""), a.get("surface", "")]))
    if finish == "Unknown":
        finish = _first(FINISH_RULES, name)
    if finish == "Unknown":
        finish = _first(FINISH_RULES, row.get("description", ""))

    # Macktiles puts "Polished" in Surface and a design family in Finish; treat
    # polished porcelain as PGVT, the way the market labels it.
    if row.get("source") == "macktiles":
        code = name.upper().replace(" ", "")
        if body == "Unknown" or body == "Porcelain (GVT)":
            body = "Soluble salt" if code.startswith("NPSP") or code.startswith("SS") else (
                "Porcelain polished (PGVT)" if finish == "Gloss / polished" else "Porcelain (GVT)")
    if body == "Unknown" and size and size[0] >= 600:
        body = "Porcelain (GVT)"  # 600mm+ formats in this market are vitrified
    if body == "Unknown" and size and size[1] <= 450:
        body = "Ceramic"
    if size and size[1] >= 1600 and body not in ("Mosaic",):
        body = "Slab"

    look = _first(LOOK_RULES, " ".join([a.get("collection", ""), name]))
    if look == "Unknown":
        look = _first(LOOK_RULES, " ".join([a.get("finish", ""), row.get("description", "")]))
    if look == "Unknown" and a.get("finish", "").lower() == "nature":
        look = "Stone"  # Macktiles "Nature" range: stone/marble inspired, refined by matching later

    apps = _all(APPLICATION_RULES, everything)
    application = "Outdoor" if "Outdoor" in apps else ("Floor & wall" if {"Floor", "Wall"} <= set(apps) else
                                                         (apps[0] if apps else (
                                                             "Wall" if body == "Ceramic" else "Floor & wall")))

    return {
        **{k: row.get(k) for k in ("source", "brand", "group", "product_id", "name", "url", "image",
                                    "observed_on")},
        # Prices are carried through exactly as published; unit resolution and any
        # conversion happen in tileiq/audit.py, with the evidence recorded.
        "list_price": row.get("list_price"), "sell_price": row.get("sell_price"),
        "price_basis": row.get("price_basis"), "price_raw_text": row.get("price_raw_text"),
        "size_mm": size_label(size),
        "size_short": size[0] if size else None,
        "size_long": size[1] if size else None,
        "size_class": size_class(size),
        "body": body,
        "finish": finish,
        "look": look,
        "application": application,
        "colour": a.get("colors", "").split(",")[0].split(" ")[0] if a.get("colors") else "",
        "launched": a.get("launched") or None,
        "thickness_mm": _thickness(a.get("thickness", "")),
        "rectified": bool(a.get("rectified")),
        "shade_variation": a.get("shade_variation", ""),
        "origin": a.get("origin", ""),
        # Global-source extras: US retail price and the retailer's own demand flags.
        **{k: row.get(k) for k in ("usd_per_sqm", "is_bestseller", "is_new_arrival", "is_clearance")},
        "raw_text": everything[:800],
    }


def is_tile(rec: dict) -> bool:
    """Drop bathware, trims and accessories that slip into catalogue feeds."""
    txt = rec["raw_text"].lower()
    if re.search(r"bath ?ware|accessor|basin|closet|faucet|trim and field|skirting|grout|adhesive", txt) \
            and not re.search(r"floor tiles|wall tiles|60x60|60x120", txt):
        return False
    return rec["size_mm"] != "Unknown"
