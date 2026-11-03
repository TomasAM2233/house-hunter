"""The apartment score (Tomás, 2026-11-03): 3 ambientes in Palermo or Recoleta, 80+ m², balcony, good view, garage,
modern or renovated (nothing run-down or ugly). Same shape as hh/score.py: hard filters + weighted components."""
import json, os, re, statistics
from . import config, text

D = config.DEPTO
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET = os.path.join(ROOT, "geo", "depto_market.json")
BALCONY_ES = {"none": "sin balcón", "french": "balcón francés", "small": "balcón chico", "medium": "balcón mediano",
              "large": "balcón grande / terraza"}


def is_depto(l):
    return l.get("kind") == "depto" or l.get("type") == "departamento"


def kind(l):
    return "depto" if is_depto(l) else "casa"


def _s():
    from . import score  # helpers shared with the house score
    return score


def desc(l):
    return " ".join([l.get("description") or "", l.get("title") or ""] + [str(x) for x in l.get("features_text") or [] if x])


def m2(l):
    """Surface the price is compared on: covered m2, else 90% of the total (balconies are in the total)."""
    if l.get("covered_m2"):
        return l["covered_m2"]
    return round(0.9 * l["total_m2"]) if l.get("total_m2") else None


def ppm2_cov(l):
    v = m2(l)
    return round(l["price_usd"] / v) if l.get("price_usd") and v else None


# ── area price, frozen like the houses' price of land so scores and cached AI verdicts stay put ──
_MARKET = None


def market():
    global _MARKET
    if _MARKET is None:
        _MARKET = json.load(open(MARKET)) if os.path.exists(MARKET) else {"points": [], "median": None}
    return _MARKET


def market_ppm2(l):
    """Median USD per covered m2 of the DEPTO_NEIGHBOURS nearest apartments (not this one), or the overall median."""
    m = market()
    pts = [p for p in m["points"] if p[3] != l.get("id")]
    if not pts:
        return None
    if l.get("lat") is None:
        return m.get("median")
    k = sorted(pts, key=lambda p: (p[0] - l["lat"]) ** 2 + ((p[1] - l["lng"]) * 0.823) ** 2)[:config.DEPTO_NEIGHBOURS]
    return statistics.median(p[2] for p in k)


def build_market(listings, log=print):
    """Freeze geo/depto_market.json the first time there are enough apartments with price, m2 and location.
    Delete the file (or run this again by hand) to rebuild it. Returns True when it wrote the file."""
    global _MARKET
    pts = []
    for l in listings:
        if not is_depto(l) or not l.get("active") or l.get("duplicate_of") or l.get("lat") is None:
            continue
        v = ppm2_cov(l)
        if v and 800 <= v <= 6_000:
            pts.append([round(l["lat"], 5), round(l["lng"], 5), v, l["id"]])
    if len(pts) < config.DEPTO_MARKET_MIN:
        return False
    med = round(statistics.median(p[2] for p in pts))
    json.dump({"points": pts, "median": med, "n": len(pts)}, open(MARKET, "w"), indent=0)
    _MARKET = None
    log(f"depto market: froze {len(pts)} apartments, median USD {med}/m² cubierto")
    return True


# ── signals ──
def balcony(l, ai=None):
    """(value 0..1, label, known_none)."""
    if ai and ai.get("balcony"):
        b = ai["balcony"]
        return ({"none": 0, "french": 0.2, "small": 0.5, "medium": 0.8, "large": 1}.get(b, 0.4),
                BALCONY_ES.get(b, f"balcón {b}") + (f" ~{ai['balcony_m2_est']:.0f} m²" if isinstance(ai.get("balcony_m2_est"), (int, float)) else ""),
                b == "none")
    t = desc(l)
    b = text.balcony(t)
    if b is False:
        return 0, "sin balcón según aviso", True
    if b and text.french_balcony(t):
        return 0.2, "balcón francés según aviso", False
    if b:
        return 0.6, "balcón según aviso", False
    return 0.3, "no menciona balcón", False


def garage(l, ai=None):
    """'fixed', 'optional', False or None."""
    t = text.garage(desc(l))
    if (l.get("garage") or 0) >= 1 and t != "optional":
        return "fixed"
    if t is not None:
        return t
    if ai and ai.get("garage") is not None:
        return "fixed" if ai["garage"] is True else "optional" if ai["garage"] == "optional" else False
    return None


def floor(l, ai=None):
    f = (ai or {}).get("floor_est")
    return f if isinstance(f, (int, float)) else text.floor_number(desc(l))


def hard_filters(l, ai=None):
    S = _s()
    r = []
    p = l.get("price_usd")
    if p and p > D["price_ceiling"]:
        r.append(f"precio USD {S.n(p)} (más de {S.n(D['price_ceiling'])})")
    if l.get("zone") and l["zone"] not in D["zones"]:
        r.append(f"barrio {l['zone']} (solo {' y '.join(D['zones'])})")
    tot = l.get("total_m2") or l.get("covered_m2")
    if tot and tot < D["min_total_m2"]:
        r.append(f"{tot:.0f} m² (< {D['min_total_m2']})")
    if l.get("ambientes") and l["ambientes"] < D["min_ambientes"]:
        r.append(f"{l['ambientes']:.0f} ambientes")
    if balcony(l, ai)[2]:
        r.append("sin balcón")
    g = garage(l, ai)
    if g is False or (g is None and l.get("enriched") and not l.get("card_only") and ai and ai.get("garage") is False):
        r.append("sin cochera")
    if ai:
        if (ai.get("condition") or 5) < D["min_condition"]:
            r.append(f"estado {ai['condition']}/5 (venido abajo)")
        if (ai.get("modern") or 5) < D["min_modern"]:
            r.append(f"estética {ai['modern']}/5 (viejo o feo)")
        if (ai.get("view") or 5) < D["min_view"]:
            r.append(f"vista {ai['view']}/5 (a pared o pulmón)")
    return r


def components(l, ai=None):
    S = _s()
    lerp, n = S.lerp, S.n
    c = {}
    reform = (ai or {}).get("reform_usd")
    reform = reform if isinstance(reform, (int, float)) else None
    t = desc(l)

    p = l.get("price_usd")
    v = ppm2_cov(l)
    if p:
        eff = p + (reform or 0)
        s1 = lerp(eff, 150_000, 1, 250_000, 0)
        s2 = lerp(v, 2_000, 1, 3_300, 0) if v else 0.5
        c["price"] = (0.6 * s1 + 0.4 * s2, f"USD {n(eff)} efectivo" + (f" (incl. reforma {n(reform)})" if reform else "")
                      + (f", {n(v)}/m² cub." if v else ""))
    else:
        c["price"] = (0.3, "sin precio en USD")

    # investment: price per m2 against the apartments around it, and what keeps it easy to resell
    mk = market_ppm2(l)
    why = []
    if v and mk:
        r = v / mk
        pv = lerp(r, 0.8, 1, 1.2, 0)
        why.append(f"USD {n(v)}/m² cub. contra ~{n(mk)} de la zona ({(r - 1) * 100:+.0f}%)")
    else:
        pv = 0.5
        why.append("sin referencia de precio de la zona" if v else "sin m² para comparar con la zona")
    g = garage(l, ai)
    ac = credit(l, ai)
    bv = balcony(l, ai)[0]
    fl = floor(l, ai)
    liq = 0.35 * (1 if g == "fixed" else 0.4 if g == "optional" else 0.3) + 0.25 * {True: 1, False: 0, None: 0.5}[ac] \
        + 0.2 * min(1, bv / 0.6) + 0.2 * (lerp(fl, 1, 0.2, 6, 1) if fl is not None else 0.5)
    why.append("fácil de revender" if liq >= 0.75 else "reventa normal" if liq >= 0.5 else "le faltan cosas que pide el comprador")
    c["investment"] = (0.65 * pv + 0.35 * liq, ", ".join(why))

    # modern / condition
    if ai and ai.get("condition"):
        mo = ai.get("modern") or ai["condition"]
        rs = lerp(reform or 0, 0, 1, 20_000, 0)
        c["modern"] = (0.5 * (mo - 1) / 4 + 0.3 * (ai["condition"] - 1) / 4 + 0.2 * rs,
                       f"estética {mo}/5, estado {ai['condition']}/5, reforma ~USD {n(reform or 0)}")
    else:
        age = _s().house_age(l)
        base = 0.7 if age is not None and age <= 10 else 0.5 if age is not None and age <= 35 else 0.35
        fresh = bool(re.search(r"reciclad|a estrenar|renovad|moderno|refaccionad|impecable", text.norm(t)))
        c["modern"] = (min(1, base + 0.15 * fresh), f"sin IA; antigüedad {age if age is not None else '?'} años"
                       + (", el aviso dice reciclado/moderno" if fresh else ""))

    # view
    if ai and ai.get("view"):
        c["view"] = ((ai["view"] - 1) / 4, f"vista {ai['view']}/5" + (f", piso {fl:.0f}" if fl is not None else "")
                     + (f": {ai['view_notes']}" if ai.get("view_notes") else ""))
    else:
        vw = text.view_words(t)
        base = lerp(fl, 1, 0.25, 10, 0.8) if fl is not None else 0.4
        c["view"] = (S.clip(base + 0.25 * vw), (f"piso {fl:.0f}" if fl is not None else "piso no informado")
                     + (", promete vista" if vw > 0 else ", interno/contrafrente" if vw < 0 else ""))

    tot, cov, amb = l.get("total_m2"), l.get("covered_m2"), l.get("ambientes")
    s = 0.5 * lerp(tot or 80, 80, 0, 130, 1) + 0.3 * lerp(cov or 70, 70, 0, 110, 1) + 0.2 * (1 if (amb or 3) >= 4 else 0.6)
    c["space"] = (s, f"{n(tot)} m² tot, {n(cov)} cub, {n(amb)} amb")

    geo = l.get("geo")
    if geo:
        st, pk = geo["station"], geo.get("park")
        sv = lerp(st["blocks"], 3, 1, 12, 0)
        pv2 = S.park_value(pk["m"]) if pk else 0.5
        qv = ((ai.get("quiet") or 3) - 1) / 4 if ai else 0.5
        c["location"] = (0.5 * pv2 + 0.3 * sv + 0.2 * qv,
                         (f"plaza a {n(pk['m'] / config.BLOCK_M)} cdas ({pk['name']})" if pk and pk["m"] >= 50 else
                          f"frente a plaza ({pk['name']})" if pk else "sin datos de plazas")
                         + f", subte {st['line'][-1]} a {n(st['blocks'])} cdas ({st['name']})"
                         + ("" if l.get("address_exact") else " · ubicación aproximada"))
    else:
        c["location"] = (0.4, "sin ubicación")

    bv, bwhy, _ = balcony(l, ai)
    c["balcony"] = (bv, bwhy)

    c["garage"] = ({"fixed": 1, "optional": 0.4, False: 0, None: 0.2}[g],
                   {"fixed": "con cochera", "optional": "cochera opcional (aparte)", False: "sin cochera", None: "no aclara cochera"}[g])

    if ai and ai.get("natural_light"):
        c["light"] = ((ai["natural_light"] - 1) / 4, f"luz {ai['natural_light']}/5")
    else:
        lum = "luminos" in text.norm(t)
        c["light"] = (0.75 if lum else 0.5, "luminoso según aviso" if lum else "sin dato")

    c["credit"] = ({True: 1, False: 0, None: 0.4}[ac], {True: "apto crédito", False: "no apto crédito", None: "no aclara"}[ac])
    return c


def credit(l, ai=None):
    ac = text.apto_credito(desc(l))
    if ac is None and l.get("apto_credito_field") is not None:
        ac = l["apto_credito_field"]
    if ac is None and l.get("credit_pill"):
        ac = True
    if ac is None and ai:
        ac = ai.get("apto_credito")
    return ac


def score(l, ai=None):
    S = _s()
    comps = components(l, ai)
    W = config.WEIGHTS_DEPTO
    total = sum(W[k] * v for k, (v, _) in comps.items())
    flags = []
    if not l.get("geo"):
        flags.append("sin ubicación")
    elif not l.get("address_exact"):
        flags.append("ubicación aproximada")
    if not ai:
        flags.append("sin análisis IA")
    if l.get("partial_data"):
        flags.append("datos parciales")
    g = garage(l, ai)
    if g is None:
        flags.append("cochera sin confirmar")
    elif g == "optional":
        flags.append("cochera aparte")
    bv, _, none = balcony(l, ai)
    if not none and bv <= 0.3:
        flags.append("balcón sin confirmar" if bv == 0.3 else "balcón francés")
    p = l.get("price_usd")
    if p and p > D["price_max"]:
        flags.append(f"sobre presupuesto (USD {S.n(p)})")
        total -= S.lerp(p, D["price_max"], 0, D["price_ceiling"], 10)
    return {
        "score": round(max(0, total), 1),
        "components": {k: {"value": round(v, 2), "points": round(W[k] * v, 1), "max": W[k], "why": why} for k, (v, why) in comps.items()},
        "discard": hard_filters(l, ai),
        "flags": flags,
    }
