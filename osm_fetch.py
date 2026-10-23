"""One-off: pull Av. Maipú geometry and nearby train stations from OpenStreetMap into geo/reference.json."""
import json, os, requests

BBOX = "-34.545,-58.52,-34.49,-58.47"  # south,west,north,east around Vicente López / Olivos / La Lucila
Q = f"""
[out:json][timeout:60];
(
  way["highway"]["name"~"^(Avenida |Av\\. )?Maip[uú]$",i]({BBOX});
  node["railway"~"station|halt"]({BBOX});
  node["public_transport"="station"]["train"="yes"]({BBOX});
);
out geom;
"""
r = requests.post("https://overpass-api.de/api/interpreter", data={"data": Q}, timeout=90,
                  headers={"User-Agent": "house-hunter/0.1"})
r.raise_for_status()
els = r.json()["elements"]
maipu = [[[p["lat"], p["lon"]] for p in e["geometry"]] for e in els if e["type"] == "way"]
stations = {}
for e in els:
    if e["type"] == "node" and e.get("tags", {}).get("name"):
        stations[e["tags"]["name"]] = [e["lat"], e["lon"], e["tags"].get("operator", ""), e["tags"].get("network", "")]
os.makedirs("geo", exist_ok=True)
json.dump({"maipu": maipu, "stations": stations}, open("geo/reference.json", "w"), ensure_ascii=False, indent=1)
print(len(maipu), "maipu ways")
for k, v in sorted(stations.items()):
    print(k, v)
