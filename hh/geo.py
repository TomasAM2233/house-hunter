"""Distances to Av. Maipú, Puente Saavedra, train stations, Villa Borges and plazas/parks, plus a cached Nominatim geocoder."""
import json, math, os, time
import requests
from . import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REF = json.load(open(os.path.join(ROOT, "geo", "reference.json")))
GEOCODE_CACHE = os.path.join(ROOT, "data", "geocode_cache.json")
PARKS = os.path.join(ROOT, "geo", "parks.json")  # written by osm_parks.py
_parks = None


def _xy(lat, lon, lat0=-34.52):
    # Local equirectangular projection in metres; plenty accurate at neighbourhood scale.
    return (lon * 111_320 * math.cos(math.radians(lat0)), lat * 110_540)


def dist_m(a, b):
    (x1, y1), (x2, y2) = _xy(*a), _xy(*b)
    return math.hypot(x2 - x1, y2 - y1)


def _seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = _xy(*p), _xy(*a), _xy(*b)
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def maipu_m(lat, lon):
    p = (lat, lon)
    return min(_seg_dist(p, w[i], w[i + 1]) for w in _REF["maipu"] for i in range(len(w) - 1))


def station_line(name, network):
    if name in config.TREN_DE_LA_COSTA:
        return "Tren de la Costa"
    return network or "Mitre"


def nearest_station(lat, lon):
    best = None
    for name, (slat, slon, _op, network) in _REF["stations"].items():
        line = station_line(name, network)
        d = dist_m((lat, lon), (slat, slon))
        eff = d / config.BLOCK_M + config.STATION_LINE_PENALTY_BLOCKS.get(line, 2)
        if best is None or eff < best["effective_blocks"]:
            best = {"name": name, "line": line, "blocks": round(d / config.BLOCK_M, 1), "effective_blocks": round(eff, 1)}
    return best


def parks():
    global _parks
    if _parks is None:
        _parks = [p for p in (json.load(open(PARKS)) if os.path.exists(PARKS) else [])
                  if p["m2"] >= config.PARK_MIN_M2]
    return _parks


def _inside(p, ring):
    (x, y), pts = _xy(*p), [_xy(*q) for q in ring]
    hit = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def nearest_park(lat, lon):
    """Closest plaza/park, in metres to its edge (0 if inside). None if geo/parks.json hasn't been fetched yet."""
    p, best = (lat, lon), None
    for park in parks():
        ring = park["ring"]
        d = 0 if _inside(p, ring) else min(_seg_dist(p, ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring)))
        if best is None or d < best["m"]:
            best = {"name": park["name"], "m": round(d)}
    return best


def villa_blocks(lat, lon):
    return max(0, dist_m((lat, lon), config.VILLA_BORGES) - config.VILLA_BORGES_RADIUS_M) / config.BLOCK_M


def describe(lat, lon):
    return {
        "maipu_blocks": round(maipu_m(lat, lon) / config.BLOCK_M, 1),
        "puente_blocks": round(dist_m((lat, lon), config.PUENTE_SAAVEDRA) / config.BLOCK_M, 1),
        "villa_blocks": round(villa_blocks(lat, lon), 1),
        "station": nearest_station(lat, lon),
        "park": nearest_park(lat, lon),
    }


_cache = None


AREA = (-58.53, -34.55, -58.46, -34.49)  # lon/lat box around Olivos, Florida and La Lucila, as in geocode()


def in_area(lat, lon):
    return AREA[0] <= lon <= AREA[2] and AREA[1] <= lat <= AREA[3]


def geocode(address):
    """Street address -> [lat, lon] via OpenStreetMap Nominatim, cached on disk, 1 req/s."""
    global _cache
    if _cache is None:
        _cache = json.load(open(GEOCODE_CACHE)) if os.path.exists(GEOCODE_CACHE) else {}
    if address in _cache:
        return _cache[address]
    time.sleep(1.1)
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", timeout=30,
                         params={"q": address, "format": "json", "limit": 1, "countrycodes": "ar",
                                 "viewbox": "-58.53,-34.49,-58.46,-34.55", "bounded": 1},
                         headers={"User-Agent": "house-hunter/0.1 (personal project)"})
        res = r.json()
        _cache[address] = [float(res[0]["lat"]), float(res[0]["lon"])] if res else None
    except Exception:
        return None
    os.makedirs(os.path.dirname(GEOCODE_CACHE), exist_ok=True)
    json.dump(_cache, open(GEOCODE_CACHE, "w"), ensure_ascii=False, indent=0)
    return _cache[address]


def reference():
    """Map layers for the dashboard: Av. Maipú, stations, Puente Saavedra, plus the reference lines and places
    in geo/overlays.json (Mitre and Belgrano rail, Panamericana, General Paz, Cementerio de Olivos, La Salle,
    Municipalidad), pulled once from OpenStreetMap; and the plazas/parks and the Villa Borges no-go circle."""
    ov = os.path.join(ROOT, "geo", "overlays.json")
    return {"maipu": [[[round(a, 5), round(b, 5)] for a, b in w] for w in _REF["maipu"]],
            "stations": _REF["stations"], "puente": list(config.PUENTE_SAAVEDRA),
            "parks": [{"name": p["name"], "ring": p["ring"]} for p in parks()],
            "villa": {"center": list(config.VILLA_BORGES),
                      "radius_m": config.VILLA_BORGES_RADIUS_M + config.VILLA_BORGES_MIN_BLOCKS * config.BLOCK_M},
            **(json.load(open(ov)) if os.path.exists(ov) else {})}
