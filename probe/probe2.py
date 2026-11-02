"""Temporary probe 2: agency sites (Tokko?), Tokko CABA location ids, Argenprop paging/ambientes, subte stations."""
import json, os, re, sys, collections, unicodedata
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests as rq
from hh import http, config
from hh.sources import zonaprop
from concurrent.futures import ThreadPoolExecutor

def P(*a): print(*a, flush=True)
BARRIOS = ["palermo", "belgrano", "villa-crespo", "almagro", "colegiales", "chacarita", "villa-urquiza", "villa-ortuzar",
           "parque-chas", "nunez", "recoleta", "balvanera", "san-nicolas"]

P("== overpass subte")
for url in ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]:
    try:
        q = '[out:json][timeout:60];node["railway"="station"]["station"="subway"](-34.65,-58.53,-34.53,-58.35);out;'
        r = rq.post(url, data={"data": q}, timeout=90, headers={"User-Agent": "house-hunter/0.1 (personal project)"})
        P(url, r.status_code, r.text[:200] if r.status_code != 200 else "")
        els = r.json()["elements"]
        P("SUBTE", json.dumps([[e["tags"].get("name"), e["tags"].get("line") or e["tags"].get("ref") or e["tags"].get("network"), e["tags"].get("operator"), round(e["lat"], 5), round(e["lon"], 5)] for e in els], ensure_ascii=False))
        break
    except Exception as e:
        P(url, "ERR", e)

P("== zonaprop publishers (CABA, 4 pages)")
pubs = collections.Counter(); pinfo = {}
caba = "-".join(BARRIOS)
for page in (1, 2, 3, 4):
    url = zonaprop.BASE + f"/casas-ph-venta-{caba}-mas-de-3-ambientes-80000-240000-dolar" + ("" if page == 1 else f"-pagina-{page}") + ".html"
    try:
        st = zonaprop._state(http.get(url, via_api=True).text)["listStore"]
    except Exception as e:
        P("fail", e); continue
    for p in st["listPostings"]:
        pb = p.get("publisher") or {}
        pubs[pb.get("name")] += 1
        pinfo[pb.get("name")] = {k: v for k, v in pb.items() if k not in ("name",) and isinstance(v, (str, int))}
P("ZP PUB KEYS", list(pinfo.values())[:3])
top = [n for n, c in pubs.most_common(80) if n and not re.search(r"remax|re/max|century|keller", n, re.I)]
P("TOP", top)

P("== argenprop paging / ambientes")
from bs4 import BeautifulSoup
base = "https://www.argenprop.com/casas-o-ph/venta/" + "-o-".join(BARRIOS)
for u in [base + "/3-ambientes-o-mas/dolares-80000-240000?pagina-24", base + "/dolares-80000-240000?pagina-63"]:
    try:
        html = http.get(u, via_api=True).text
        s = BeautifulSoup(html, "html.parser")
        feats = [" ".join(li.get_text(" ", strip=True).split()) for li in s.select(".card__main-features li")]
        amb = collections.Counter(f for f in feats if "amb" in f.lower())
        P(u[-60:], "cards", len(s.select("div.listing__item")), amb.most_common(6))
    except Exception as e:
        P(u, "fail", str(e)[:150])

P("== argenprop agent pages")
ag = collections.Counter()
for page in (1, 2, 3):
    try:
        html = http.get(base + "/dolares-80000-240000" + (f"?pagina-{page}" if page > 1 else ""), via_api=True).text
        for m in re.finditer(r'card__agent-name[^>]*>\s*([^<]+)<', html):
            ag[m.group(1).strip()] += 1
    except Exception as e:
        P("fail", e)
P("AP AGENTS", ag.most_common(60))


def slug(n):
    n = unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(s\.?a\.?s?|srl|s\.r\.l\.|inmobiliaria|negocios inmobiliarios|bienes raices|propiedades|real estate|brokers?|servicios inmobiliarios)\b", " ", n)
    return re.sub(r"[^a-z0-9]+", "", n)


names = list(dict.fromkeys(top + [n for n, _ in ag.most_common(60)]))
cands = []
for n in names:
    s = slug(n)
    if len(s) < 3:
        continue
    for d in [f"https://www.{s}.com.ar", f"https://www.{s}propiedades.com.ar", f"https://www.{s}propiedades.com", f"https://www.{s}.com", f"https://{s}.com.ar"]:
        cands.append((n, d))


def check(nd):
    n, d = nd
    try:
        r = rq.get(d, timeout=12, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        t = r.text
        if r.status_code != 200 or len(t) < 2000:
            return None
        tok = "tokko" in t.lower()
        key = re.findall(r"\b[0-9a-f]{40}\b", t)
        tfw = "/Buscar" in t or "tfw" in t.lower()
        title = re.search(r"<title>([^<]{0,80})", t)
        return (n, r.url, tok, tfw, key[:2], title.group(1).strip() if title else "")
    except Exception:
        return None


with ThreadPoolExecutor(16) as ex:
    for res in ex.map(check, cands):
        if res:
            P("SITE", res)

P("== tokko locations")
key = config.AGENCIES[0]["key"]
for u in [f"https://www.tokkobroker.com/api/v1/location/quick_search/?key={key}&format=json&q=Palermo",
          f"https://www.tokkobroker.com/api/v1/location/?key={key}&format=json&name=Palermo",
          f"https://www.tokkobroker.com/api/v1/state/?key={key}&format=json&limit=40",
          f"https://www.tokkobroker.com/api/v1/location/25818/?key={key}&format=json"]:
    try:
        r = rq.get(u, timeout=30)
        P(u.split("?")[0], r.status_code, r.text[:600])
    except Exception as e:
        P(u.split("?")[0], e)
