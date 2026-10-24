"""One-off: reference geometry for the map from OpenStreetMap (Overpass), saved to probe/overlays.json."""
import json, requests
BBOX = "-34.56,-58.54,-34.48,-58.45"
Q = f"""
[out:json][timeout:120];
(
  way["railway"="rail"]({BBOX});
  way["highway"~"motorway|trunk"]["name"~"Panamericana|General Paz|Acceso Norte",i]({BBOX});
  way["landuse"="cemetery"]["name"~"Olivos",i]({BBOX});
  nwr["amenity"="school"]["name"~"La Salle",i]({BBOX});
  nwr["amenity"="townhall"]({BBOX});
  nwr["name"~"Municipalidad de Vicente L",i]({BBOX});
);
out tags geom;
"""
r = requests.post("https://overpass-api.de/api/interpreter", data={"data": Q}, timeout=180, headers={"User-Agent": "house-hunter/0.1"})
print(r.status_code, len(r.text))
els = r.json()["elements"]
out = []
for e in els:
    t = e.get("tags", {})
    g = e.get("geometry")
    c = [e["lat"], e["lon"]] if e["type"] == "node" else e.get("center") or (g and [sum(p["lat"] for p in g) / len(g), sum(p["lon"] for p in g) / len(g)])
    out.append({"type": e["type"], "id": e["id"], "tags": {k: t[k] for k in t if k in ("name", "railway", "highway", "landuse", "amenity", "operator", "usage", "service", "ref")},
                "geom": [[round(p["lat"], 6), round(p["lon"], 6)] for p in g] if g else None, "center": c})
json.dump(out, open("probe/overlays.json", "w"), ensure_ascii=False)
from collections import Counter
print(Counter((o["tags"].get("railway") or o["tags"].get("highway") or o["tags"].get("landuse") or o["tags"].get("amenity"), o["tags"].get("name")) for o in out).most_common(40))
