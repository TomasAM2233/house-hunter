"""Temporary probe 3: Tokko's CABA location ids, and which candidate agency websites (Tokko's public site template)
list houses/PH in the CABA barrios. Only the agencies' public search pages are read."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests as rq
from hh import config, http


def P(*a):
    print(*a, flush=True)


key0 = config.AGENCIES[0]["key"]
cf = None
url = f"https://www.tokkobroker.com/api/v1/state/?key={key0}&format=json&limit=100"
while url and not cf:
    d = rq.get(url, timeout=60).json()
    for s in d["objects"]:
        if any(x["name"] in ("Almagro", "Palermo") for x in s.get("divisions", [])):
            cf = s
    url = ("https://www.tokkobroker.com" + d["meta"]["next"]) if d["meta"].get("next") else None
P("STATE", cf and {k: cf[k] for k in cf if k != "divisions"})
divs = [(x["id"], x["name"]) for x in (cf or {}).get("divisions", [])]
P("DIVS", json.dumps(divs, ensure_ascii=False))
want = {i: config.barrio(n) for i, n in divs if config.barrio(n)}
P("WANT", json.dumps({i: [n for j, n in divs if j == i][0] + " -> " + z for i, z in want.items()}, ensure_ascii=False))

SITES = {"Filippo Propiedades": "https://www.filippopropiedades.com.ar", "Carlos D'Odorico": "https://www.carlosdodorico.com",
         "Idea Cinco": "https://www.ideacinco.com.ar", "Inteligencia Urbana": "https://www.inteligenciaurbana.com.ar",
         "Martina Domínguez Realty": "https://www.martinadominguezrealty.com.ar", "Crecer Inmobiliaria": "https://www.crecer.com.ar",
         "Karas Propiedades": "https://www.karaspropiedades.com.ar", "Real Props": "https://www.realprops.com.ar",
         "Braulio Inmuebles": "https://www.braulioinmuebles.com", "Kraft Propiedades": "https://www.kraft.com.ar",
         "Bolajuzon": "https://bolajuzon.com", "Geraci Propiedades": "https://www.geraci.com.ar",
         "Lexinton Propiedades": "https://www.lexinton.com.ar", "Desimone Grillo": "https://www.desimonegrillo.com.ar",
         "Oslo Propiedades": "https://www.oslopropiedades.com.ar", "MUV Propiedades": "https://www.muvpropiedades.com",
         "Yacoub": "https://yacoub.com.ar", "RG Montes": "https://www.rgmontes.com", "Belga": "https://www.belga.com.ar",
         "Golden Haus": "https://www.goldenhaus.com.ar", "Baigún RyN": "https://baigunryn.com"}
locs = ",".join(map(str, want))
s = config.SEARCH
for name, site in SITES.items():
    try:
        base = (f"{site}/Buscar?operation=1&ptypes=3,13&locations={locs}&min-price={s['price_min']}&max-price={s['price_ceiling']}&currency=USD&o=2,2")
        found = {}
        for page in (1, 2, 3):
            body = http.get(base + (f"&p={page}" if page > 1 else ""), pause=(0.5, 1), tries=2).text
            new = dict(re.findall(r'href="/p/(\d+)-([^"]+)"', body))
            if not new or (page > 1 and "--NoMoreProperties--" in body):
                break
            found.update(new)
        P("SITE", name, len(found), list(found.values())[:6])
    except Exception as e:
        P("SITE", name, "ERR", str(e)[:120])
