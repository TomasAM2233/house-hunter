"""Official zone of a point in Vicente López, from geo/zoning.json (built by zoning_build.py from the municipality's
zoning plan), with the zone's building limits from section 7 of the Código de Ordenamiento Urbano."""
import json, os
from .geo import ROOT, _inside, _seg_dist, _xy

ZONING = os.path.join(ROOT, "geo", "zoning.json")
EDGE_M = 40  # a geocoded address within this of another zone may well be in it (zones often split along a street)

# code: (name, FOS, FOT, max height in m). FOS = share of the lot the building may cover, FOT = total m2 buildable
# as a multiple of the lot. Base values, without the code's "premios" (e.g. for a wide frontage).
PARAMS = {
    "R1": ("Residencial baja densidad", 0.5, 0.8, 10.5),
    "R2": ("Residencial media baja densidad", 0.6, 1.0, 10.5),
    "R3": ("Residencial media densidad", 0.6, 1.1, 10.5),
    "R4": ("Residencial media densidad / comercio restringido", 0.6, 1.2, 12.5),
    "C1A": ("Comercial / residencial media densidad", 0.6, 1.5, 10.5),
    "C1B": ("Comercial / residencial media densidad", 0.6, 1.5, 10.5),
    "C2": ("Comercial local / residencial media alta densidad", 0.6, 1.8, 12.5),
    "C3": ("Comercial / residencial alta densidad", 0.6, 2.65, 22.5),
    "C4": ("Comercial", 0.6, 1.2, 13.5),
    "C5": ("Comercial / residencial media alta densidad", 0.6, 2.0, None),
    "T1": ("Torres, residencial alta densidad", 0.6, 2.5, None),
    "T2": ("Torres, residencial alta densidad / comercial", 0.6, 2.65, None),
    "T3L": ("Torres, residencial alta densidad / comercial", 0.6, 2.65, None),
    "T4": ("Torres, comercial de oficinas", 0.6, 3.0, None),
    "I1": ("Industrial / residencial baja densidad", 0.6, 1.2, None),
    "E1": ("Esparcimiento", 0.2, 0.3, None),
    "UE": ("Uso específico (club, colegio, institución)", None, None, None),
}

_zones = None


def zones():
    global _zones
    if _zones is None:
        _zones = []
        for z in (json.load(open(ZONING))["zones"] if os.path.exists(ZONING) else []):
            xs, ys = zip(*(_xy(*p) for p in z["rings"][0]))
            _zones.append({**z, "bbox": (min(xs), min(ys), max(xs), max(ys))})
    return _zones


def _dist(p, z):
    """Metres from p to zone polygon z, 0 if inside."""
    rings = z["rings"]
    if _inside(p, rings[0]) and not any(_inside(p, h) for h in rings[1:]):
        return 0
    return min(_seg_dist(p, r[i], r[(i + 1) % len(r)]) for r in rings for i in range(len(r)))


def at(lat, lon):
    """{"code", "name", "fos", "fot", "height_m", "edge": other zone within EDGE_M or None}, or None outside the
    plan (or when geo/zoning.json is missing). A geocoded point usually sits on the street between two blocks, so the
    zone is the nearest one, and "edge" names a different zone that's about as close."""
    if not zones():
        return None
    p, (x, y) = (lat, lon), _xy(lat, lon)
    near = []
    for z in zones():
        x0, y0, x1, y1 = z["bbox"]
        if x0 - EDGE_M * 2 <= x <= x1 + EDGE_M * 2 and y0 - EDGE_M * 2 <= y <= y1 + EDGE_M * 2:
            near.append((_dist(p, z), z["code"]))
    near.sort()
    if not near or near[0][0] > EDGE_M:
        return None
    # Geocoded points sit on the street, and the rail strip along Maipú, clubs and schools (RES2, UE...) are as
    # close as the lots across it, so a zone where houses get built wins when it's within reach.
    lots = [n for n in near if n[0] <= EDGE_M and PARAMS.get(n[1], (0, 0, None))[2] and n[1] != "E1"]
    near = lots + [n for n in near if n not in lots]
    d0, code = near[0]
    edge = next((c for d, c in near if c != code and d <= max(EDGE_M, d0 + 15)), None)
    name, fos, fot, h = PARAMS.get(code, ("Zona especial (ver el código)", None, None, None))
    return {"code": code, "name": name, "fos": fos, "fot": fot, "height_m": h, "edge": edge}
