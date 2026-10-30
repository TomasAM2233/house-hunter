"""Turn Vicente López's official zoning plan (geo/zoning/plano.pdf) into geo/zoning.json, so each house's zone can be
looked up by its coordinates (hh/zoning.py).

The plan is a vector PDF: every block, or strip of lots along an avenue, is a filled shape whose colour is its zone
in the plan's legend. It has no coordinates, and its street names are drawn rather than written, so it's placed on
the map by matching its blocks to the blocks formed by OpenStreetMap's streets (geo/zoning/osm.json, fetched by
zoning_fetch.py): first the outline of the whole partido against its OSM boundary (scale, then the best rotation),
then an affine fit that pulls each plan block's centre onto the nearest OSM block's (a few metres off in the end).

Run once, after zoning_fetch.py: pip install pymupdf shapely numpy scipy && python zoning_build.py
"""
import collections, json, math, os
import numpy as np
import pymupdf
from scipy.spatial import cKDTree
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import polygonize, transform, unary_union
from shapely.validation import make_valid

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "geo", "zoning")
OUT = os.path.join(ROOT, "geo", "zoning.json")
LAT0 = -34.52
KX, KY = 111_320 * math.cos(math.radians(LAT0)), 110_540  # metres per degree, as in hh/geo.py

# Fill colour of each zone in the plan's legend ("REFERENCIAS"). A few special zones share a colour; the nearest
# label on the plan decides between them.
LEGEND = {
    "R1": (1.0, 1.0, 0.659), "R2": (1.0, 0.812, 0.62), "R3": (1.0, 0.678, 0.678), "R4": (1.0, 0.49, 0.322),
    "RU": (0.867, 0.757, 0.431), "C1": (1.0, 0.749, 0.0), "C2": (0.988, 0.745, 0.827), "C3": (0.745, 0.643, 0.698),
    "C4": (0.922, 0.549, 0.643), "C5": (0.718, 0.482, 0.592), "I1": (0.949, 0.8, 1.0), "T1": (0.937, 0.38, 0.38),
    "T2": (1.0, 0.482, 0.38), "T3L": (1.0, 0.624, 0.498), "T4": (0.882, 0.318, 0.318), "UE": (0.82, 0.937, 0.741),
    "U1": (0.431, 0.867, 0.867), "U5": (0.431, 0.867, 0.867), "U6": (0.431, 0.867, 0.867),
    "U9": (0.431, 0.867, 0.867), "U20": (0.431, 0.867, 0.867), "UT5": (0.431, 0.867, 0.867),
    "U2": (0.682, 0.996, 0.98), "U7": (0.745, 0.996, 0.933), "U8": (0.204, 0.616, 0.616),
    "U23": (0.498, 1.0, 0.749), "RES1": (0.498, 1.0, 0.749), "U25": (0.0, 0.62, 0.62), "U28": (0.0, 0.62, 0.62),
    "UPS": (0.0, 0.62, 0.62), "U26": (0.498, 0.624, 1.0), "U32": (0.392, 0.643, 0.808), "UC4": (0.867, 0.431, 0.541),
    "RES2": (0.647, 0.867, 0.431), "RM1": (0.867, 0.431, 0.0), "RM2": (1.0, 0.498, 0.498),
    "RM3": (0.867, 0.647, 0.431), "E1": (0.749, 1.0, 0.498), "EQ2": (0.0, 0.541, 0.722), "ES": (0.0, 0.647, 0.867),
    "IDE": (0.541, 0.867, 0.431), "FC1": (0.529, 0.702, 0.02), "FC2": (0.612, 1.0, 0.561), "FC4": (0.243, 0.612, 0.027),
}
# Parts of the sheet that aren't the map: the notes and legend column, and the small diagrams at the bottom right.
NOT_MAP = [box(0, 900, 560, 2126), box(1200, 1600, 2551, 2126)]


def _rings(items):
    """A filled path's line segments, split into closed rings wherever the pen jumps."""
    out, cur = [], []
    for it in items:
        a, b = (it[1].x, it[1].y), (it[2].x, it[2].y)
        if cur and (abs(cur[-1][0] - a[0]) > .01 or abs(cur[-1][1] - a[1]) > .01):
            out.append(cur)
            cur = []
        cur = cur or [a]
        cur.append(b)
    return [r for r in out + [cur] if len(r) >= 3]


def plan_shapes(page):
    by = collections.defaultdict(list)
    for d in page.get_drawings():
        col = tuple(round(c, 3) for c in d.get("fill") or ())
        if col not in set(LEGEND.values()):
            continue
        for r in _rings([it for it in d["items"] if it[0] == "l"]):
            p = make_valid(Polygon(r))
            if p.area > 0:
                by[col].append(p)
    shapes = []
    for col, ps in by.items():
        u = unary_union(ps)
        shapes += [(col, g) for g in getattr(u, "geoms", [u])
                   if g.geom_type == "Polygon" and not any(b.contains(g.centroid) for b in NOT_MAP)]
    return shapes


def osm_xy():
    d = json.load(open(os.path.join(SRC, "osm.json")))
    xy = lambda pts: [(lon * KX, lat * KY) for lat, lon in pts]
    boundary = max(polygonize(unary_union([LineString(xy(b)) for b in d["boundary"]])), key=lambda p: p.area)
    streets = unary_union([LineString(xy(w["g"])) for w in d["ways"] if len(w["g"]) > 1])
    blocks = [p for p in polygonize(streets) if 3_000 < p.area < 40_000 and boundary.contains(p.centroid)]
    return boundary, blocks


def fit(shapes, boundary, osm_blocks):
    """Affine (A, t) taking plan points to local metres."""
    geoms = [g for _, g in shapes]
    outline = unary_union([g.buffer(25) for g in geoms]).buffer(-25)  # closes the streets and highways
    outline = max(getattr(outline, "geoms", [outline]), key=lambda g: g.area)
    s = math.sqrt(boundary.area / outline.area)
    flipped = affinity.scale(outline, s, -s, origin=(0, 0))  # PDF y grows downwards
    best = None
    for rot in range(-45, 46):
        g = affinity.rotate(flipped, rot, origin=(0, 0))
        g = affinity.translate(g, boundary.centroid.x - g.centroid.x, boundary.centroid.y - g.centroid.y)
        iou = g.intersection(boundary).area / g.union(boundary).area
        if best is None or iou > best[0]:
            best = (iou, rot)
    th = math.radians(best[1])
    A = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]]) @ np.diag([s, -s])
    t = np.array([boundary.centroid.x, boundary.centroid.y]) - A @ np.array([outline.centroid.x, outline.centroid.y])
    # Plan blocks: the zone shapes merged across the hairlines between lots, split by the street gaps.
    u = unary_union([g.buffer(0.6) for g in geoms]).buffer(-0.6)
    P = np.array([[g.centroid.x, g.centroid.y] for g in getattr(u, "geoms", [u]) if g.area > 30])
    Q = np.array([[g.centroid.x, g.centroid.y] for g in osm_blocks])
    tree = cKDTree(Q)
    for it in range(30):
        dd, ii = tree.query(P @ A.T + t)
        m = dd < (max(25, np.percentile(dd, 60)) if it < 10 else 30)
        sol = np.linalg.lstsq(np.hstack([P[m], np.ones((m.sum(), 1))]), Q[ii[m]], rcond=None)[0]
        A, t = sol[:2].T, sol[2]
    dd, _ = tree.query(P @ A.T + t)
    print(f"outline IoU {best[0]:.3f} at {best[1]}°; blocks matched within 20 m: {(dd < 20).mean():.0%}, "
          f"median {np.median(dd):.1f} m")
    return A, t


def main():
    page = pymupdf.open(os.path.join(SRC, "plano.pdf"))[0]
    labels = [(w[4], (w[0] + w[2]) / 2, (w[1] + w[3]) / 2) for w in page.get_text("words")]
    by_colour = collections.defaultdict(list)
    for code, col in LEGEND.items():
        by_colour[col].append(code)
    shapes = plan_shapes(page)
    boundary, osm_blocks = osm_xy()
    A, t = fit(shapes, boundary, osm_blocks)
    to_m = lambda x, y: (A[0, 0] * np.asarray(x) + A[0, 1] * np.asarray(y) + t[0],
                         A[1, 0] * np.asarray(x) + A[1, 1] * np.asarray(y) + t[1])

    def nearest_label(g, codes):
        c = g.representative_point()
        near = [(math.hypot(x - c.x, y - c.y), tx) for tx, x, y in labels if tx in codes]
        return min(near)[1] if near else None

    zones = collections.defaultdict(list)
    for col, g in shapes:
        codes = by_colour[col]
        code = codes[0] if len(codes) == 1 else nearest_label(g, codes) or codes[0]
        if code == "C1":  # one colour, two zones on the plan: C1A and C1B
            code = nearest_label(g, ("C1A", "C1B")) or code
        m = transform(to_m, g).intersection(boundary)
        if m.area > 40:
            zones[code].append(m)
    feats = []
    for code, ps in sorted(zones.items()):
        u = unary_union(ps).simplify(1.0)
        for p in getattr(u, "geoms", [u]):
            if p.geom_type != "Polygon" or p.area < 40:
                continue
            ll = lambda ring: [[round(y / KY, 5), round(x / KX, 5)] for x, y in ring.coords[:-1]]
            feats.append({"code": code, "rings": [ll(p.exterior)] + [ll(h) for h in p.interiors if h.area > 40]})
    json.dump({"source": "Plano de zonificación, Código de Ordenamiento Urbano de Vicente López (Anexo 4, "
                         "actualizado a mayo de 2012), ubicado sobre las calles de OpenStreetMap",
               "zones": feats}, open(OUT, "w"), separators=(",", ":"))
    print(f"{len(feats)} polygons in {len(zones)} zones -> {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
