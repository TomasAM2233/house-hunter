"""Freeze the area's price of land into geo/land_market.json (see score.land_value).

Every active house (not PH) with a location, price, covered m2 and lot gives a point: the USD per m2 of lot its
asking price implies once its building is taken out at what it's worth. A listing's market price of land is the
median of the points nearest to it. The file is frozen on purpose: if it moved with every run, so would every
score and the AI verdicts cached by their input. Rebuild it every few months, or after changing the building cost
or depreciation in hh/config.py:  python land_market_build.py
"""
import json, os, statistics
from hh import score

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "listings.json")
OUT = os.path.join(ROOT, "geo", "land_market.json")


def main():
    ls = json.load(open(DATA))["listings"]
    pts = []
    for l in ls:
        if not l.get("active") or l.get("duplicate_of") or l.get("type") != "casa" or l.get("lat") is None:
            continue
        v = score.implied_land(l, l.get("ai"))
        if v is not None:
            pts.append([round(l["lat"], 5), round(l["lng"], 5), round(v), l["id"]])
    med = round(statistics.median(p[2] for p in pts))
    json.dump({"built": __import__("time").strftime("%Y-%m-%d"), "median": med, "points": pts}, open(OUT, "w"))
    print(f"{len(pts)} houses, median USD {med} per m2 of lot")


if __name__ == "__main__":
    main()
