"""Distances to Av. Maipú (or the nearest Subte B/D station in CABA), Puente Saavedra, train stations, Villa Borges and
plazas/parks, plus a cached Nominatim geocoder."""
import json, math, os, time
import requests
from . import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REF = json.load(open(os.path.join(ROOT, "geo", "reference.json")))
GEOCODE_CACHE = os.path.join(ROOT, "data", "geocode_cache.json")
PARKS = os.path.join(ROOT, "geo", "parks.json")  # written by osm_parks.py
_SUBTE = json.load(open(os.path.join(ROOT, "geo", "subte.json")))  # Subte B and D stations (OpenStreetMap), in line order
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


def nearest_subte(lat, lon):
    """Closest Subte B/D station: {name, line, blocks}."""
    best = None
    for name, line, slat, slon in _SUBTE["stations"]:
        if line not in config.SUBTE_LINES:
            continue
        d = dist_m((lat, lon), (slat, slon))
        if best is None or d < best[0]:
            best = (d, name, line)
    return {"name": best[1], "line": f"Subte {best[2]}", "blocks": round(best[0] / config.BLOCK_M, 1),
            "effective_blocks": round(best[0] / config.BLOCK_M, 1)}


def is_caba(lat, lon, zone=None):
    """CABA or Vicente López: by the listing's zone when it has one, else by the side of General Paz (taken as the
    point being closer to a Subte B/D station than to Av. Maipú, which holds well away from the border)."""
    if zone in config.SEARCH["zones_caba"]:
        return True
    if zone in config.SEARCH["zones_gba"]:
        return False
    return nearest_subte(lat, lon)["blocks"] * config.BLOCK_M < maipu_m(lat, lon)


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


def describe(lat, lon, zone=None):
    """Everything the score needs about a point. "ref_blocks" is what the location rules measure: cuadras to Av. Maipú
    in Vicente López, to the nearest Subte B/D station in CABA ("ref" says which, for the app and the AI)."""
    from . import zoning  # it builds on the helpers above
    puente = round(dist_m((lat, lon), config.PUENTE_SAAVEDRA) / config.BLOCK_M, 1)
    if is_caba(lat, lon, zone):
        sub = nearest_subte(lat, lon)
        return {
            "region": "caba", "ref": f"subte {sub['name']} ({sub['line'][-1]})", "ref_blocks": sub["blocks"],
            "maipu_blocks": None, "puente_blocks": puente, "villa_blocks": None,
            "station": sub, "park": nearest_park(lat, lon), "zoning": None,
        }
    maipu = round(maipu_m(lat, lon) / config.BLOCK_M, 1)
    return {
        "region": "gba", "ref": "Maipú", "ref_blocks": maipu,
        "maipu_blocks": maipu,
        "puente_blocks": puente,
        "villa_blocks": round(villa_blocks(lat, lon), 1),
        "station": nearest_station(lat, lon),
        "park": nearest_park(lat, lon),
        "zoning": zoning.at(lat, lon),
    }


_cache = None


AREA = (-58.53, -34.55, -58.46, -34.49)       # lon/lat box around Olivos, Florida, La Lucila and Vicente López
AREA_CABA = (-58.52, -34.63, -58.36, -34.53)  # the CABA barrios along Subte B and D


def _box(zone):
    if zone in config.SEARCH["zones_gba"]:
        return AREA
    return AREA_CABA if config.caba(zone) else (AREA[0], AREA_CABA[1], AREA_CABA[2], AREA[3])  # unknown: both


def in_area(lat, lon, zone=None):
    a = _box(zone)
    return a[0] <= lon <= a[2] and a[1] <= lat <= a[3]


def geocode(address, zone=None):
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
                                 "viewbox": "{},{},{},{}".format(*(lambda a: (a[0], a[3], a[2], a[1]))(_box(zone))), "bounded": 1},
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
            "subte": [s for s in _SUBTE["stations"] if s[1] in config.SUBTE_LINES],
            "parks": [{"name": p["name"], "ring": p["ring"]} for p in parks()],
            "villa": {"center": list(config.VILLA_BORGES),
                      "radius_m": config.VILLA_BORGES_RADIUS_M + config.VILLA_BORGES_MIN_BLOCKS * config.BLOCK_M},
            **(json.load(open(ov)) if os.path.exists(ov) else {})}
