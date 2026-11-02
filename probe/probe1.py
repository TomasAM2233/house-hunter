"""Temporary probe (removed before merge): slugs, volumes and filters for the CABA expansion."""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests as rq
from hh import http
from hh.sources import zonaprop

BARRIOS = ["palermo", "belgrano", "villa-crespo", "almagro", "colegiales", "chacarita", "villa-urquiza", "villa-ortuzar",
           "parque-chas", "nunez", "recoleta", "balvanera", "san-nicolas"]

def P(*a): print(*a, flush=True)

P("== scrapingant usage")
try:
    r = rq.get(f"https://api.scrapingant.com/v2/usage?x-api-key={http.ANT_KEY}", timeout=30); P(r.status_code, r.text[:300])
except Exception as e: P(e)
try:
    r = rq.get(f"https://api.scraperapi.com/account?api_key={http.API_KEY}", timeout=30); P(r.status_code, r.text[:300])
except Exception as e: P(e)

P("== overpass subte B/D")
q = """[out:json][timeout:90];
rel["route"="subway"]["ref"~"^(B|D)$"](-34.65,-58.52,-34.53,-58.36);
(._;>;);
out body;"""
for url in ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]:
    try:
        r = rq.post(url, data={"data": q}, timeout=120, headers={"User-Agent": "house-hunter/0.1 (personal project)"})
        els = r.json()["elements"]
        nodes = {e["id"]: e for e in els if e["type"] == "node"}
        st = {}
        for e in els:
            if e["type"] == "relation":
                for m in e["members"]:
                    if m["type"] == "node" and m["role"].startswith("stop") and m["ref"] in nodes:
                        n = nodes[m["ref"]]
                        st.setdefault((e["tags"].get("ref"), n["tags"].get("name")), (round(n["lat"], 5), round(n["lon"], 5)))
        # station nodes too
        q2 = """[out:json][timeout:90];node["station"="subway"](-34.65,-58.52,-34.53,-58.36);out body;"""
        r2 = rq.post(url, data={"data": q2}, timeout=120, headers={"User-Agent": "house-hunter/0.1 (personal project)"})
        P("STOPS", json.dumps({f"{k[0]}|{k[1]}": v for k, v in st.items()}, ensure_ascii=False))
        P("STATIONS", json.dumps([[n["tags"].get("name"), n["tags"].get("line") or n["tags"].get("ref") or n["tags"].get("network"), round(n["lat"], 5), round(n["lon"], 5)] for n in r2.json()["elements"]], ensure_ascii=False))
        break
    except Exception as e:
        P(url, e)

P("== zonaprop")
def zp(url):
    try:
        st = zonaprop._state(http.get(url, via_api=True).text)["listStore"]
        pg = st["paging"]
        return st, pg
    except Exception as e:
        P("  fail", url, str(e)[:150]); return None, None
caba = "-".join(BARRIOS)
B = "https://www.zonaprop.com.ar/casas-ph-venta-"
pubs = collections.Counter(); locs = collections.Counter()
for u in [f"{B}{caba}-mas-de-3-ambientes-80000-240000-dolar.html",
          f"{B}{caba}-mas-de-3-ambientes-mas-de-100-m2-80000-240000-dolar.html",
          f"{B}{caba}-mas-de-3-ambientes-desde-100-m2-totales-80000-240000-dolar.html",
          f"{B}palermo-mas-de-3-ambientes-80000-240000-dolar.html",
          f"{B}{caba}-mas-de-3-ambientes-80000-240000-dolar-orden-publicado-descendente.html"]:
    st, pg = zp(u)
    if not st: continue
    P(u.split("venta-")[1][-90:], "paging:", {k: pg.get(k) for k in ("total", "totalPages", "currentPage")})
    for p in st["listPostings"]:
        pubs[(p.get("publisher") or {}).get("name")] += 1
        loc = (p.get("postingLocation") or {}).get("location") or {}
        chain = []
        while loc:
            chain.append(loc.get("name")); loc = loc.get("parent")
        locs[" < ".join(c or "?" for c in chain)] += 1
P("ZP LOCS", locs.most_common(40))
P("ZP PUBS", pubs.most_common(60))

P("== argenprop")
from bs4 import BeautifulSoup
for u in ["https://www.argenprop.com/casas-o-ph/venta/" + "-o-".join(BARRIOS) + "/dolares-80000-240000",
          "https://www.argenprop.com/casas-o-ph/venta/" + "-o-".join(BARRIOS) + "/3-ambientes-o-mas/dolares-80000-240000",
          "https://www.argenprop.com/casas-o-ph/venta/palermo/dolares-80000-240000"]:
    try:
        html = http.get(u, via_api=True).text
        s = BeautifulSoup(html, "html.parser")
        pages = max([int(p) for p in re.findall(r"[?&]pagina-(\d+)", html)], default=1)
        title = s.title.get_text(strip=True) if s.title else ""
        tot = re.search(r"([\d.]+)\s+(?:propiedades|resultados|Casas|PH)", s.get_text(" "))
        addrs = [" ".join(a.get_text(" ", strip=True).split()) for a in s.select(".card__address")][:6]
        ag = [a.get_text(strip=True) for a in s.select(".card__agent-name")]
        P(u[-70:], "pages", pages, "|", title[:100], "|", tot.group(0) if tot else None, addrs, ag[:20])
    except Exception as e:
        P("  fail", u, str(e)[:150])

P("== mercadolibre")
from hh.sources import mercadolibre as ml
for kind in ("casas", "ph"):
    for b in BARRIOS:
        u = f"https://inmuebles.mercadolibre.com.ar/{kind}/venta/capital-federal/{b}/_PriceRange_80000USD-240000USD_NoIndex_True"
        try:
            html = ml.fetch(u).text
            n = re.search(r'"total":(\d+)', html) or re.search(r'([\d.]+)\s+resultados', html)
            cards = [c for c in ml._cards(html) if c.get("metadata", {}).get("id")] or list(ml._html_cards(html))
            locs = [((({c["type"]: c for c in cd.get("components", [])}.get("location", {}).get("location")) or {}).get("text", "")) for cd in cards[:3]]
            P(kind, b, "total", n.group(1) if n else None, "cards", len(cards), locs)
        except Exception as e:
            P(kind, b, "fail", str(e)[:120])
