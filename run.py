"""Full pipeline: scrape -> merge history -> geo -> enrich + AI for candidates -> score -> data/listings.json.

python run.py                 # scrape everything enabled and rescore
python run.py --no-scrape     # just rescore what we already have (e.g. after editing weights or AI results)
"""
import argparse, json, os, shutil, sys, time, traceback
from hh import ai, config, geo, score
from hh.sources import zonaprop, mercadolibre

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "listings.json")
WEB_DATA = os.path.join(ROOT, "web", "listings.json")
SOURCES = {"zonaprop": zonaprop, "mercadolibre": mercadolibre}
TODAY = time.strftime("%Y-%m-%d")


def log(*a):
    print(*a, flush=True)


def load():
    if os.path.exists(DATA):
        return {l["id"]: l for l in json.load(open(DATA))["listings"]}
    return {}


def merge(old, fresh):
    for l in fresh:
        prev = old.get(l["id"])
        if prev:
            l["first_seen"] = prev.get("first_seen", TODAY)
            hist = prev.get("price_history", [])
            if l.get("price_usd") and (not hist or hist[-1][1] != l["price_usd"]):
                hist.append([TODAY, l["price_usd"]])
            l["price_history"] = hist
            if prev.get("enriched") and not l.get("enriched"):
                for k in ("enriched", "description", "photos", "features_text"):
                    if k in prev:
                        l[k] = prev[k]
            if l.get("lat") is None and prev.get("lat") is not None:
                l["lat"], l["lng"] = prev["lat"], prev["lng"]
        else:
            l["first_seen"] = TODAY
            l["price_history"] = [[TODAY, l["price_usd"]]] if l.get("price_usd") else []
        l["last_seen"] = TODAY
        l["active"] = True
        old[l["id"]] = l
    return old


def dedupe(listings):
    """Same property posted by several agencies: same price and total m2, within ~200 m. Keep the best scored."""
    act = sorted((l for l in listings if l.get("active") and l.get("price_usd")), key=lambda l: (bool(l["discard"]), not l.get("ai"), -l["score"]))
    kept = []
    for l in act:
        twin = next((k for k in kept if k["price_usd"] == l["price_usd"] and k.get("total_m2") == l.get("total_m2")
                     and l.get("lat") is not None and k.get("lat") is not None
                     and geo.dist_m((l["lat"], l["lng"]), (k["lat"], k["lng"])) < 200), None)
        if twin:
            l["duplicate_of"] = twin["id"]
            l["discard"] = list(l["discard"]) + [f"duplicado de {twin['id']}"]
        else:
            l.pop("duplicate_of", None)
            kept.append(l)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scrape", action="store_true")
    ap.add_argument("--sources", default=os.environ.get("HH_SOURCES", "zonaprop"))
    ap.add_argument("--max-enrich", type=int, default=80)
    args = ap.parse_args()

    listings = load()
    status = {}
    if not args.no_scrape:
        for name in args.sources.split(","):
            try:
                fresh = SOURCES[name].search(log=log)
                seen = {l["id"] for l in fresh}
                complete = not getattr(SOURCES[name].search, "failed_pages", None)
                for l in listings.values():
                    if complete and l["source"] == name and l["id"] not in seen:
                        l["active"] = False
                listings = merge(listings, fresh)
                status[name] = {"ok": True, "count": len(fresh), "complete": complete, "at": time.strftime("%Y-%m-%d %H:%M")}
            except Exception as e:
                traceback.print_exc()
                status[name] = {"ok": False, "error": str(e)[:200], "at": time.strftime("%Y-%m-%d %H:%M")}

    # geography
    for l in listings.values():
        if l.get("lat") is None and l.get("geocode_query"):
            ll = geo.geocode(l["geocode_query"])
            if ll:
                l["lat"], l["lng"] = ll
        l["geo"] = geo.describe(l["lat"], l["lng"]) if l.get("lat") is not None else None

    # enrich + AI only for active listings that survive the non-AI filters, best pre-score first
    cands = [l for l in listings.values() if l.get("active") and not score.hard_filters(l)]
    cands.sort(key=lambda l: -score.score(l)["score"])
    enriched = 0
    for l in cands:
        if l["source"] == "zonaprop" and not l.get("enriched") and enriched < args.max_enrich:
            try:
                zonaprop.enrich(l)
                enriched += 1
            except Exception as e:
                log(f"enrich failed {l['id']}: {e}")
        ai.analyse(l, log=log)

    cache = ai._load()
    for l in listings.values():
        res = cache.get(l["id"])
        l["ai"] = res
        l.update(score.score(l, res))

    dedupe(listings.values())
    if not status and os.path.exists(DATA):
        status = json.load(open(DATA)).get("status", {})
    out = sorted(listings.values(), key=lambda l: (not l.get("active"), bool(l["discard"]), -l["score"]))
    payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "status": status, "weights": config.WEIGHTS,
               "search": config.SEARCH, "reference": geo.reference(), "listings": out}
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(payload, open(DATA, "w"), ensure_ascii=False, indent=1)
    shutil.copy(DATA, WEB_DATA)
    shortlist = [l for l in out if l.get("active") and not l["discard"]]
    pending = len([l for l in shortlist if not l.get("ai")])
    log(f"{len(out)} listings, {len(shortlist)} on the shortlist, {pending} waiting for AI")


if __name__ == "__main__":
    sys.exit(main())
