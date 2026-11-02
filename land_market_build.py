"""Freeze the area's price of land into geo/land_market.json (see score.land_value).

Every active house (not PH) with a location, price, covered m2 and lot gives a point: the USD per m2 of lot its
asking price implies once its building is taken out at what it's worth. A listing's market price of land is the
median of the points nearest to it. The file is frozen on purpose: if it moved with every run, so would every
score and the AI verdicts cached by their input. Rebuild it every few months, or after changing the building cost
or depreciation in hh/config.py:  python land_market_build.py
The CABA side is frozen by run.py on its own the first time it has enough houses.
"""
import json, os, statistics
from hh import score

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "listings.json")
OUT = os.path.join(ROOT, "geo", "land_market.json")


MIN_POINTS = 30  # houses a side of General Paz needs before its price of land gets frozen


def side(l):
    return "caba" if (l.get("geo") or {}).get("region") == "caba" else "gba"


def build(listings, sides=("gba", "caba"), log=print):
    """Freeze the points of the given sides (Vicente López "gba", CABA "caba"), keeping the other side's as they are.
    Each point is [lat, lng, USD per m2 of lot, id, side]. Returns the sides written."""
    old = json.load(open(OUT)) if os.path.exists(OUT) else {"points": []}
    allold = [p if len(p) > 4 else p + ["gba"] for p in old["points"]]
    keep = [p for p in allold if p[4] not in sides]
    new, done = {s: [] for s in sides}, []
    for l in listings:
        if not l.get("active") or l.get("duplicate_of") or l.get("type") != "casa" or l.get("lat") is None:
            continue
        v = score.implied_land(l, l.get("ai"))
        if v is not None and side(l) in new:
            new[side(l)].append([round(l["lat"], 5), round(l["lng"], 5), round(v), l["id"], side(l)])
    for s, pts in new.items():
        if len(pts) < MIN_POINTS:
            keep += [p for p in allold if p[4] == s]  # not enough houses yet: left as it was
            continue
        keep += pts
        done.append(s)
        log(f"land market {s}: {len(pts)} houses, median USD {round(statistics.median(p[2] for p in pts))} per m2 of lot")
    meds = {s: round(statistics.median(p[2] for p in keep if p[4] == s)) for s in ("gba", "caba") if any(p[4] == s for p in keep)}
    json.dump({"built": __import__("time").strftime("%Y-%m-%d"), "median": meds.get("gba"), "medians": meds,
               "points": keep}, open(OUT, "w"))
    score._MARKET = None
    return done


def missing():
    """Sides with no frozen points yet."""
    pts = json.load(open(OUT))["points"] if os.path.exists(OUT) else []
    have = {p[4] if len(p) > 4 else "gba" for p in pts}
    return [s for s in ("gba", "caba") if s not in have]


def main():
    build(json.load(open(DATA))["listings"])


if __name__ == "__main__":
    main()
