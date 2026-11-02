"""Temporary probe 4: the new CABA code paths end to end on small samples (newest pages, one band, geocoding)."""
import collections, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hh import config, geo, score
from hh.sources import zonaprop, argenprop, mercadolibre, tokko


def P(*a):
    print(*a, flush=True)


def show(name, ls):
    P(name, len(ls), collections.Counter(l.get("zone") for l in ls).most_common(20))
    for l in ls[:3]:
        P("   ", l["id"], l.get("zone"), l.get("address"), l.get("lat"), l.get("geocode_query"))


zp = zonaprop.search(newest_only=True, log=P)
show("ZP newest", zp)
out, failed = [], []
caba = zonaprop.zone_groups()[2][0]
zonaprop._sweep(caba, (228_000, None), False, 9, P, out, failed)
show("ZP band 228k+", out)
ap = argenprop.search(newest_only=True, log=P)
show("AP newest", ap)
for z in ("Villa Urquiza", "Palermo"):
    ml = []
    for kind in ("ph",):
        import re
        html = mercadolibre.fetch(mercadolibre.search_url(kind, z, 0)).text
        cards = [c for c in mercadolibre._cards(html) if c.get("metadata", {}).get("id")] or list(mercadolibre._html_cards(html))
        ml += [mercadolibre._normalize(c, kind, z) for c in cards]
    show("ML " + z, ml)
for a in config.AGENCIES[-6:] + [x for x in config.AGENCIES if x["name"] == "Braulio Inmuebles"]:
    try:
        got = tokko.search_site(a, P, max_pages=3)
        show("TK " + a["name"], got)
    except Exception as e:
        P("TK", a["name"], "ERR", e)
# geocode + describe a few CABA cards
n = 0
for l in (zp + ap)[:200]:
    if config.caba(l.get("zone")) and l.get("lat") is None and l.get("geocode_query"):
        ll = geo.geocode(l["geocode_query"], l["zone"])
        g = geo.describe(*ll, l["zone"]) if ll else None
        P("GEO", l["geocode_query"], ll, g and (g["ref"], g["ref_blocks"], g["park"]))
        n += 1
        if n >= 8:
            break
for l in zp[:15]:
    if l.get("lat") is not None:
        l["geo"] = geo.describe(l["lat"], l["lng"], l["zone"])
        sc = score.score(l)
        P("SCORE", l["id"], l["zone"], l["geo"]["ref"], l["geo"]["ref_blocks"], sc["score"], sc["discard"][:2])
