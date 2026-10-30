"""Fetch Vicente López's official zoning sources into geo/zoning/ so the hunt can tell each house's zone.

The municipality publishes no zoning dataset: only the zoning plan as a PDF (Anexo 4 of the Código de Ordenamiento
Urbano, updated to May 2012) and the code's own text, which bounds each zone street by street. Their hosts don't
answer from everywhere, so .github/workflows/zoning.yml runs this on GitHub's runners.

This downloads both, plus OpenStreetMap's streets to place the plan on the map (zoning_build.py does that), and
writes a summary of what's inside the plan (fill colours, labels) to geo/zoning/probe.json.
"""
import collections, json, os
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "geo", "zoning")
SOURCES = {
    "plano.pdf": "https://observatorioamba.org/planes-y-proyectos/vicente-lopez/normas/705_leg618_legcou_aii___a4_plano_de_zonificacion_del_partido.pdf",
    "cou_5_zonificacion.pdf": "https://www.ecofield.net/Legales/Ord/Vicente_Lopez_BA/Cod_Urbano/5_ZONIFICACION.pdf",
    "cou_7_morfologia.pdf": "https://legislacion.vicentelopez.gov.ar/api/pdf/95669",
}
UA = {"User-Agent": "Mozilla/5.0 (house-hunter; zoning)"}


def download():
    got = {}
    for name, url in SOURCES.items():
        if os.path.exists(os.path.join(OUT, name)):  # the 2012 plan and the code text don't change
            got[name] = os.path.getsize(os.path.join(OUT, name))
            continue
        try:
            r = requests.get(url, headers=UA, timeout=120)
            r.raise_for_status()
            open(os.path.join(OUT, name), "wb").write(r.content)
            got[name] = len(r.content)
        except Exception as e:
            got[name] = f"error: {e}"[:200]
    return got


def probe(path):
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    pages = []
    for page in doc:
        d = page.get_drawings()
        fills = collections.Counter(tuple(round(c, 3) for c in x["fill"]) for x in d if x.get("fill"))
        strokes = collections.Counter(tuple(round(c, 3) for c in x["color"]) for x in d if x.get("color"))
        spans = []
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l["spans"]:
                    t = s["text"].strip()
                    if t:
                        spans.append({"t": t, "x": round(s["bbox"][0], 1), "y": round(s["bbox"][1], 1), "size": round(s["size"], 1)})
        pages.append({"size": [round(page.rect.width), round(page.rect.height)], "rotation": page.rotation,
                      "drawings": len(d), "images": len(page.get_images()),
                      "fills": [[list(k), v] for k, v in fills.most_common(40)],
                      "strokes": [[list(k), v] for k, v in strokes.most_common(15)],
                      "spans": spans[:4000], "n_spans": len(spans)})
    return pages


OSM_Q = """
[out:json][timeout:120];
(
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street)$"](-34.56,-58.54,-34.48,-58.45);
  relation["boundary"="administrative"]["admin_level"="5"]["name"~"Vicente L"](-34.56,-58.54,-34.48,-58.45);
);
out geom;
"""


def osm():
    """Streets and the partido boundary, to georeference the plan (its street names are drawn, not text)."""
    for url in ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"] * 2:
        try:
            r = requests.post(url, data={"data": OSM_Q}, timeout=180, headers={"User-Agent": "house-hunter/0.1 (personal project)"})
            r.raise_for_status()
            els = r.json()["elements"]
            break
        except Exception as e:
            print(f"overpass {url}: {e}")
    else:
        return 0
    ways, bound = [], []
    for e in els:
        if e["type"] == "way" and e.get("geometry"):
            ways.append({"name": e.get("tags", {}).get("name", ""), "hw": e["tags"]["highway"],
                         "g": [[round(p["lat"], 6), round(p["lon"], 6)] for p in e["geometry"]]})
        elif e["type"] == "relation":
            bound += [[[round(p["lat"], 6), round(p["lon"], 6)] for p in m["geometry"]]
                      for m in e.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
    json.dump({"ways": ways, "boundary": bound}, open(os.path.join(OUT, "osm.json"), "w"), separators=(",", ":"))
    return len(ways)


def text_of(path):
    import fitz
    return "\n".join(p.get_text() for p in fitz.open(path))


def main():
    os.makedirs(OUT, exist_ok=True)
    got = download()
    res = {"downloads": got, "osm_ways": osm()}
    if isinstance(got.get("plano.pdf"), int):
        res["plano"] = probe(os.path.join(OUT, "plano.pdf"))
    for name in ("cou_5_zonificacion.pdf", "cou_7_morfologia.pdf"):
        if isinstance(got.get(name), int):
            open(os.path.join(OUT, name.replace(".pdf", ".txt")), "w").write(text_of(os.path.join(OUT, name)))
    json.dump(res, open(os.path.join(OUT, "probe.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "plano"}, indent=1))
    for i, p in enumerate(res.get("plano", [])):
        print(f"page {i}: {p['size']} drawings={p['drawings']} images={p['images']} spans={p['n_spans']} fills={p['fills'][:12]}")


if __name__ == "__main__":
    main()
