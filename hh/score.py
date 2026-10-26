"""The house score: hard filters (discard reasons) + ten weighted components, each 0..1, with a short why."""
import re
from . import config, text

S = config.SEARCH


def clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def lerp(x, x0, y0, x1, y1):
    """Piecewise-linear helper: y0 at x0, y1 at x1, clamped outside."""
    if x <= x0:
        return y0
    if x >= x1:
        return y1
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def n(x):
    """Spanish-style whole number for the reasons shown in the app: 204500.0 -> '204.500'."""
    return "?" if x is None else f"{x:,.0f}".replace(",", ".")


PATIO_ES = {"none": "sin patio", "small": "patio chico", "medium": "patio mediano", "large": "patio grande"}


def ppm2(l):
    return round(l["price_usd"] / l["total_m2"]) if l.get("price_usd") and l.get("total_m2") else None


def lot_m2(l):
    """(m2, what it is): the lot (terreno) when the listing or its text gives it, else the total surface."""
    desc = (l.get("description") or "") + " " + (l.get("title") or "")
    if l.get("lot_m2"):
        return l["lot_m2"], "terreno"
    t = text.lot_m2(desc)
    if t:
        return t, "terreno"
    return l.get("total_m2"), "totales"


def maipu_sweet(blocks):
    """1 around the sweet spot (6 cuadras from Maipú), falling off towards the 3 and 15 cuadra limits."""
    s = config.MAIPU_SWEET_BLOCKS
    if blocks <= s - 0.5:
        return lerp(blocks, 3, 0.3, s - 0.5, 1)
    if blocks <= s + 0.5:
        return 1.0
    if blocks <= 10:
        return lerp(blocks, s + 0.5, 1, 10, 0.6)
    return lerp(blocks, 10, 0.6, 15, 0)


def park_value(m):
    """Walking distance to the edge of the nearest plaza/park: on the block 1, 3 cuadras 0.6, 8+ cuadras 0."""
    return lerp(m, 100, 1, 300, 0.6) if m <= 300 else lerp(m, 300, 0.6, 800, 0)


def hard_filters(l, ai=None):
    """Reasons to discard. Missing data never discards on its own; it's flagged instead."""
    r = []
    p = l.get("price_usd")
    if p and p > S["price_ceiling"]:  # no floor: a cheap house is a find, not a red flag
        r.append(f"precio USD {n(p)} (más de {n(S['price_ceiling'])})")
    if l.get("type") not in S["types"]:
        r.append(f"tipo '{l.get('type')}'")
    if l.get("total_m2") and l["total_m2"] < S["min_total_m2"]:
        r.append(f"{l['total_m2']:.0f} m² totales (< {S['min_total_m2']})")
    if l.get("ambientes") and l["ambientes"] < S["min_ambientes"]:
        r.append(f"{l['ambientes']:.0f} ambientes")
    v = ppm2(l)
    if v and v > S["ppm2_max"]:
        r.append(f"USD {n(v)}/m² (más de {n(S['ppm2_max'])})")
    g = l.get("geo")
    if g:
        if g["maipu_blocks"] < config.MAIPU_MIN_BLOCKS:
            r.append(f"a {g['maipu_blocks']} cuadras de Maipú (muy cerca)")
        if g["maipu_blocks"] > config.MAIPU_MAX_BLOCKS:
            r.append(f"a {g['maipu_blocks']} cuadras de Maipú (muy lejos)")
        if g["puente_blocks"] < config.PUENTE_MIN_BLOCKS:
            r.append(f"a {g['puente_blocks']} cuadras de Puente Saavedra")
        if g.get("villa_blocks") is not None and g["villa_blocks"] < config.VILLA_BORGES_MIN_BLOCKS:
            r.append(f"a {g['villa_blocks']} cuadras de la villa Borges")
    desc = (l.get("description") or "") + " " + (l.get("title") or "")
    if l.get("type") == "ph":
        stacked = ai.get("ph_stacked") if ai and ai.get("ph_stacked") is not None else text.ph_stacked(desc)
        if stacked:
            r.append("PH en altura / superpuesto")
    if ai and (ai.get("corner") or text.corner(desc)) and ai.get("patio_seen") is False:
        r.append("esquina sin patio visible en las fotos")
    if ai:
        if ai.get("patio") == "none":
            r.append("sin patio ni jardín")
        if ai.get("pasillo_ph") and l.get("type") == "ph":
            r.append("PH por pasillo / muy alargado")
        if (ai.get("reform_usd") or 0) > config.REFORM_BUDGET_USD * 1.75:
            r.append(f"reforma estimada USD {n(ai['reform_usd'])}")
    return r


def components(l, ai=None):
    desc = (l.get("description") or "") + " " + (l.get("title") or "") + " " + " ".join(l.get("features_text") or [])
    c = {}
    reform = (ai or {}).get("reform_usd")
    reform = reform if isinstance(reform, (int, float)) else None

    # price: asking + estimated reform, and $/m2 total
    p = l.get("price_usd")
    if p:
        eff = p + (reform or 0)
        s1 = lerp(eff, 140_000, 1, 250_000, 0)
        v = ppm2(l)
        s2 = lerp(v, 1_000, 1, 2_000, 0) if v else 0.5
        c["price"] = (0.6 * s1 + 0.4 * s2, f"USD {n(eff)} efectivo" + (f" (incl. reforma {n(reform)})" if reform else "") + (f", {n(v)}/m²" if v else ""))
    else:
        c["price"] = (0.3, "sin precio en USD")

    # space
    t, cov, amb = l.get("total_m2"), l.get("covered_m2"), l.get("ambientes")
    s = 0.45 * lerp(t or 100, 100, 0, 300, 1) + 0.35 * lerp(cov or 80, 70, 0, 200, 1) + 0.2 * lerp(amb or 3, 3, 0, 6, 1)
    c["space"] = (s, f"{n(t)} m² tot, {n(cov)} cub, {n(amb)} amb")

    # location: cuadras to Maipú around the sweet spot (a train station nearby can stand in, capped), plus a plaza/park
    g = l.get("geo")
    if g:
        st, pk = g["station"], g.get("park")
        mv = max(maipu_sweet(g["maipu_blocks"]), 0.7 * lerp(st["effective_blocks"], 4, 1, 10, 0))
        why = f"{n(g['maipu_blocks'])} cuadras a Maipú, {n(st['blocks'])} a est. {st['name']} ({st['line']})"
        if pk:
            pv = park_value(pk["m"])
            v = (1 - config.PARK_SHARE) * mv + config.PARK_SHARE * pv
            why += f", plaza a {n(pk['m'] / config.BLOCK_M)} cdas ({pk['name']})" if pk["m"] >= 50 else f", frente a plaza ({pk['name']})"
        else:
            v = mv  # parks not fetched yet: Maipú alone
        c["location"] = (v, why + ("" if l.get("address_exact") else " · ubicación aproximada"))
    else:
        c["location"] = (0.4, "sin ubicación")

    # condition
    if ai and ai.get("condition"):
        rs = lerp(reform or 0, 5_000, 1, 20_000, 0.45) if (reform or 0) <= 20_000 else lerp(reform, 20_000, 0.45, 35_000, 0)
        c["condition"] = (0.5 * (ai["condition"] - 1) / 4 + 0.5 * rs, f"estado {ai['condition']}/5, reforma ~USD {n(reform or 0)}")
    else:
        age = l.get("age_years")
        c["condition"] = ((0.7 if age is not None and age <= 20 else 0.5 if age is not None and age <= 50 else 0.35), f"sin IA; antigüedad {age if age is not None else '?'} años")

    # patio
    um2 = text.uncovered_m2(desc) or l.get("uncovered_m2")
    if ai and ai.get("patio"):
        m2 = ai.get("patio_m2_est") or um2
        base = {"none": 0, "small": 0.3, "medium": 0.65, "large": 1}.get(ai["patio"], 0.3)
        c["patio"] = (max(base, lerp(m2, 0, 0, 60, 1)) if m2 else base, PATIO_ES.get(ai["patio"], f"patio {ai['patio']}") + (f" ~{m2:.0f} m²" if m2 else ""))
    elif um2:
        c["patio"] = (lerp(um2, 0, 0, 60, 1), f"{um2} m² descubiertos según aviso")
    else:
        c["patio"] = (0.4 if text.has_patio_words(desc) else 0.1, "menciona patio/jardín" if text.has_patio_words(desc) else "no menciona patio")

    # vertical
    if ai and ai.get("vertical_potential") is not None:
        c["vertical"] = (clip(float(ai["vertical_potential"])), "según IA")
    else:
        v = 0.15 if l.get("type") == "ph" else 0.4 + 0.2 * text.own_lot(desc) + 0.2 * text.single_storey(desc)
        c["vertical"] = (v, "heurística: " + ("PH" if l.get("type") == "ph" else "casa" + (", lote propio" if text.own_lot(desc) else "") + (", una planta" if text.single_storey(desc) else "")))

    # credit
    ac = text.apto_credito(desc)
    if ac is None and l.get("apto_credito_field") is not None:
        ac = l["apto_credito_field"]
    if ac is None and l.get("credit_pill"):
        ac = True
    if ac is None and ai:
        ac = ai.get("apto_credito")
    c["credit"] = ({True: 1, False: 0, None: 0.4}[ac], {True: "apto crédito", False: "no apto crédito", None: "no aclara"}[ac])

    # garage
    gar = l.get("garage") or 0
    if gar >= 1:
        c["garage"] = (1, f"{gar:.0f} cochera")
    elif re.search(r"cochera|garage|garaje", text.norm(desc)):
        c["garage"] = (0.7, "menciona cochera")
    else:
        c["garage"] = (0, "sin cochera")

    # quiet
    gq = lerp(g["maipu_blocks"], 3, 0.3, 7, 1) if g else 0.5
    aq = ((ai.get("quiet") or 3) - 1) / 4 if ai else 0.5
    c["quiet"] = (0.6 * gq + 0.4 * aq, "lejos de Maipú" if gq > 0.8 else "cerca de avenida" if gq < 0.5 else "intermedio")

    # light
    if ai and ai.get("natural_light"):
        c["light"] = ((ai["natural_light"] - 1) / 4, f"luz {ai['natural_light']}/5")
    else:
        lum = any("lumin" in str(v).lower() for v in (l.get("tags") or {}).values()) or "luminos" in text.norm(desc)
        c["light"] = (0.75 if lum else 0.5, "luminoso según aviso" if lum else "sin dato")
    return c


def score(l, ai=None):
    comps = components(l, ai)
    total = sum(config.WEIGHTS[k] * v for k, (v, _) in comps.items())
    flags = []
    if not l.get("geo"):
        flags.append("sin ubicación")
    elif not l.get("address_exact"):
        flags.append("ubicación aproximada")
    if not ai:
        flags.append("sin análisis IA")
    if l.get("partial_data"):
        flags.append("datos parciales")
    if l.get("type") == "ph" and text.pasillo_words(l.get("description", "")) and not (ai and ai.get("pasillo_ph") is False):
        flags.append("posible pasillo")
        total -= 5
    p = l.get("price_usd")
    if p and p > S["price_max"]:
        # over budget but negotiable: up to 10 points off at the ceiling, on top of the price component
        flags.append(f"sobre presupuesto (USD {n(p)})")
        total -= lerp(p, S["price_max"], 0, S["price_ceiling"], 10)
    return {
        "score": round(max(0, total), 1),
        "components": {k: {"value": round(v, 2), "points": round(config.WEIGHTS[k] * v, 1), "max": config.WEIGHTS[k], "why": why} for k, (v, why) in comps.items()},
        "discard": hard_filters(l, ai),
        "flags": flags,
    }
