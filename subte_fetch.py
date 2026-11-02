"""Pull the Subte B and D stations (and their lines, for the map) from OpenStreetMap into geo/subte.json.

In the CABA barrios the location rules count cuadras from the nearest of these stations instead of Av. Maipú.
Run by .github/workflows/osm.yml; Overpass doesn't answer from everywhere, but it does from GitHub's runners.
"""
import json, os, sys
import requests
from hh import config

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "geo", "subte.json")
BBOX = "-34.65,-58.53,-34.53,-58.35"
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = {"User-Agent": "house-hunter/0.1 (personal project)"}


def q(lines):
    return f"""[out:json][timeout:120];
rel["route"="subway"]["ref"~"^({'|'.join(lines)})$"]({BBOX});
out geom;"""


def fetch(log=print):
    for url in MIRRORS:
        try:
            r = requests.post(url, data={"data": q(config.SUBTE_LINES)}, timeout=150, headers=UA)
            r.raise_for_status()
            els = r.json()["elements"]
            break
        except Exception as e:
            log(f"overpass {url}: {e}")
    else:
        return False
    stations, ways = {}, {}
    for rel in els:
        ln = rel["tags"].get("ref")
        for m in rel.get("members", []):
            if m["type"] == "node" and m.get("role", "").startswith("stop") and "lat" in m:
                stations.setdefault((ln, m["ref"]), (m["lat"], m["lon"]))
            elif m["type"] == "way" and m.get("role", "") in ("", "forward", "backward") and m.get("geometry"):
                ways.setdefault(ln, {})[m["ref"]] = [[round(p["lat"], 5), round(p["lon"], 5)] for p in m["geometry"]]
    # station names: the stop nodes often carry only "ref"; the names come from the station nodes around them
    ids = ",".join(str(i) for _, i in stations)
    r = requests.post(url, data={"data": f"[out:json][timeout:60];node(id:{ids});out tags;"
                                         f"node[\"station\"=\"subway\"]({BBOX});out;"}, timeout=90, headers=UA)
    tags = {e["id"]: e for e in r.json()["elements"]}
    named = [e for e in r.json()["elements"] if e.get("tags", {}).get("station") == "subway"]
    out = {}
    for (ln, i), (lat, lon) in stations.items():
        name = (tags.get(i, {}).get("tags") or {}).get("name")
        if not name and named:
            near = min(named, key=lambda e: (e["lat"] - lat) ** 2 + (e["lon"] - lon) ** 2)
            name = near["tags"].get("name")
        out.setdefault((ln, name), (round(lat, 5), round(lon, 5)))
    st = sorted([[n, ln, la, lo] for (ln, n), (la, lo) in out.items()], key=lambda s: (s[1], s[2]))
    if len(st) < 25:
        log(f"only {len(st)} stations from Overpass; keeping the old file")
        return False
    json.dump({"stations": st, "lines": {ln: list(w.values()) for ln, w in ways.items()}}, open(OUT, "w"),
              ensure_ascii=False, separators=(",", ":"))
    log(f"{len(st)} Subte stations -> {OUT}")
    return True


if __name__ == "__main__":
    sys.exit(0 if fetch() else 1)
