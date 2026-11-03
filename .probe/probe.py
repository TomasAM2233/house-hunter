"""One-off probe (deptos): which search URLs work on each portal, how many results, which filter slugs exist."""
import re, sys, json
sys.path.insert(0, ".")
from hh import http
from hh.sources import mercadolibre, zonaprop

def links(html, pat):
    return sorted(set(m for m in re.findall(r'href="([^"]+)"', html) if re.search(pat, m, re.I)))[:25]

ZP = [
    "departamentos-venta-palermo-recoleta-3-ambientes-100000-240000-dolar.html",
    "departamentos-venta-palermo-recoleta-mas-de-3-ambientes-100000-240000-dolar.html",
    "departamentos-venta-palermo-recoleta-3-ambientes-con-cochera-100000-240000-dolar.html",
    "departamentos-venta-palermo-recoleta-3-ambientes-mas-de-80-m2-cubiertos-100000-240000-dolar.html",
]
for u in ZP:
    try:
        h = http.get("https://www.zonaprop.com.ar/" + u, via_api=True).text
        t = re.search(r"<title>([^<]*)", h)
        try:
            st = zonaprop._state(h)["listStore"]
            pg = st["paging"]
            n = len(st["listPostings"])
            types = {}
            for p in st["listPostings"]:
                k = (p.get("realEstateType") or {}).get("name")
                types[k] = types.get(k, 0) + 1
            feats = st["listPostings"][0].get("mainFeatures") if st["listPostings"] else {}
        except Exception as e:
            pg, n, types, feats = str(e), 0, {}, {}
        print("ZP", u, "|", t.group(1).strip() if t else None, "|", {k: pg[k] for k in ("total", "totalPages")} if isinstance(pg, dict) else pg, n, types)
        print("   feats:", json.dumps(feats, ensure_ascii=False)[:800])
        print("   links:", links(h, r"cochera|garage|m2|metros|balc"))
    except Exception as e:
        print("ZP", u, "FAILED", e)

AP = [
    "departamentos/venta/palermo-o-recoleta/3-ambientes/dolares-100000-240000",
    "departamentos/venta/palermo-o-recoleta/3-ambientes/dolares-100000-240000?con-cochera",
]
for u in AP:
    try:
        h = http.get("https://www.argenprop.com/" + u, via_api=True).text
        t = re.search(r"<title>([^<]*)", h)
        cnt = re.search(r"([\d.]+)\s+(?:Departamentos|resultados|propiedades)", h)
        print("AP", u, "|", t.group(1).strip() if t else None, "|", cnt.group(0) if cnt else None, "| cards", h.count("listing__item"),
              "| pages", max([int(p) for p in re.findall(r"[?&]pagina-(\d+)", h)], default=1))
        print("   links:", links(h, r"cochera|garage|m2|metros|balc|ambiente"))
    except Exception as e:
        print("AP", u, "FAILED", e)

for u in ["https://inmuebles.mercadolibre.com.ar/departamentos/venta/3-ambientes/capital-federal/palermo/_PriceRange_100000USD-240000USD_NoIndex_True",
          "https://inmuebles.mercadolibre.com.ar/departamentos/venta/capital-federal/recoleta/_PriceRange_100000USD-240000USD_NoIndex_True"]:
    try:
        h = mercadolibre.fetch(u).text
        cards = [c for c in mercadolibre._cards(h) if c.get("metadata", {}).get("id")] or list(mercadolibre._html_cards(h))
        tot = re.search(r'"total":\s*(\d+)', h) or re.search(r"([\d.]+)\s+resultados", h)
        print("ML", u, "| cards", len(cards), "| total", tot.group(1) if tot else None)
        if cards:
            print("   first:", json.dumps(mercadolibre._normalize(cards[0], "departamentos", "Palermo"), ensure_ascii=False)[:600])
        print("   links:", links(h, r"cochera|ambientes|balc|m2|superficie")[:15])
    except Exception as e:
        print("ML", u, "FAILED", e)
