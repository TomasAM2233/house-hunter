"""Pull plazas and parks around Olivos / Florida / La Lucila from OpenStreetMap into geo/parks.json.

Run by .github/workflows/osm.yml (and by run.py when the file is missing); Overpass doesn't answer from everywhere.
"""
import json, math, os, sys
import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "geo", "parks.json")
BBOX = "-34.56,-58.54,-34.48,-58.45"  # south,west,north,east, a bit wider than the search area
Q = f"""
[out:json][timeout:90];
(
  way["leisure"~"^(park|playground|recreation_ground)$"]({BBOX});
  relation["leisure"="park"]({BBOX});
  way["place"="square"]({BBOX});
  way["landuse"="recreation_ground"]({BBOX});
);
out geom;
"""
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def _area_m2(ring):
    lat0 = math.radians(sum(p[0] for p in ring) / len(ring))
    xy = [(lon * 111_320 * math.cos(lat0), lat * 110_540) for lat, lon in ring]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))) / 2


def fetch(log=print):
    els = None
    for url in MIRRORS:
        try:
            r = requests.post(url, data={"data": Q}, timeout=120, headers={"User-Agent": "house-hunter/0.1 (personal project)"})
            r.raise_for_status()
            els = r.json()["elements"]
            break
        except Exception as e:
            log(f"overpass {url}: {e}")
    if els is None:
        return False
    rings = []
    for e in els:
        t = e.get("tags", {})
        if t.get("access") == "private":
            continue
        if e["type"] == "way" and e.get("geometry"):
            parts = [e["geometry"]]
        elif e["type"] == "relation":
            parts = [m["geometry"] for m in e.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
        else:
            continue
        for g in parts:
            ring = [[round(p["lat"], 5), round(p["lon"], 5)] for p in g]
            if len(ring) > 3 and ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                continue
            kind = t.get("leisure") or t.get("place") or t.get("landuse")
            name = t.get("name") or {"playground": "plaza de juegos", "square": "plaza"}.get(kind, "plaza / parque")
            rings.append({"name": name, "kind": kind, "m2": round(_area_m2(ring)), "ring": ring})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rings, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    log(f"{len(rings)} plazas/parks -> {OUT}")
    return True


if __name__ == "__main__":
    sys.exit(0 if fetch() else 1)
