"""Full pipeline: scrape -> merge history -> geo -> enrich + AI for candidates -> score -> data/listings.json.

python run.py                 # scrape everything enabled and rescore
python run.py --no-scrape     # just rescore what we already have (e.g. after editing weights or AI results)
"""
import argparse, bisect, json, os, re, shutil, sys, time, traceback
from hh import ai, config, geo, http, score
from hh.sources import argenprop, zonaprop, mercadolibre, tokko

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "listings.json")
PREFS = os.path.join(ROOT, "data", "preferences.md")   # Tomás's own words; edited from the app or on GitHub
TAGS = os.path.join(ROOT, "data", "tags.json")         # favourite / visited / dismissed + notes, saved by the app
WEB_DATA = os.path.join(ROOT, "web", "listings.json")
SOURCES = {"zonaprop": zonaprop, "argenprop": argenprop, "mercadolibre": mercadolibre, "tokko": tokko}
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
            if (prev.get("enriched") and not l.get("enriched")) or l.get("card_only"):
                # keep the richer copy: an enriched one, or (for card-only scrapes) the longer description
                for k in ("enriched", "description", "photos", "features_text", "partial_data"):
                    if k not in prev:
                        continue
                    longer = k == "description" and len(prev[k] or "") > len(l.get(k) or "")
                    if prev.get("enriched") or not l.get(k) or longer:
                        l[k] = prev[k]
                for k in ("total_m2", "covered_m2", "bedrooms", "bathrooms", "garage", "age_years", "address_exact", "publisher", "modified"):
                    if l.get(k) is None and prev.get(k) is not None:
                        l[k] = prev[k]
            for k in ("pct", "pct_score", "pct_n"):
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


def _close(a, b):
    return bool(a and b) and abs(a - b) <= 0.03 * max(a, b)


def _street(l):
    """Significant words of the street part of the address, for matching the same listing across portals."""
    words = re.findall(r"[a-záéíóúñ]{4,}", (l.get("address") or "").split(",")[0].lower())
    return {w for w in words if w not in ("entre", "esquina", "general", "avenida")}


def _twins(a, b):
    return (a["id"] != b["id"] and a.get("price_usd") and a["price_usd"] == b.get("price_usd")
            and _close(a.get("total_m2"), b.get("total_m2"))
            and ((a.get("lat") is not None and b.get("lat") is not None
                  and geo.dist_m((a["lat"], a["lng"]), (b["lat"], b["lng"])) < 250)
                 or bool(_street(a) & _street(b))))


def dedupe(listings):
    """Same property posted by several agencies: same price and total m2, within ~200 m. Keep the best scored."""
    act = sorted((l for l in listings if l.get("active") and l.get("price_usd")), key=lambda l: (bool(l["discard"]), not l.get("ai"), -l["score"]))
    kept = []
    for l in act:
        twin = next((k for k in kept if _twins(k, l)), None)
        if twin:
            l["duplicate_of"] = twin["id"]
            l["discard"] = list(l["discard"]) + [f"duplicado de {twin['id']}"]
        else:
            l.pop("duplicate_of", None)
            kept.append(l)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scrape", action="store_true")
    ap.add_argument("--sources", default=os.environ.get("HH_SOURCES", "zonaprop,argenprop,tokko,mercadolibre"))
    ap.add_argument("--max-enrich", type=int, default=150)
    args = ap.parse_args()

    listings = load()
    tags = json.load(open(TAGS)) if os.path.exists(TAGS) else {}
    status = {}
    prev = json.load(open(DATA)).get("status", {}) if os.path.exists(DATA) else {}
    if not args.no_scrape:
        for name in args.sources.split(","):
            # API-backed sources: a full sweep every FULL_EVERY_HOURS, otherwise one newest-first check a day
            every, last = getattr(SOURCES[name], "FULL_EVERY_HOURS", None), prev.get(name, {})
            age = lambda t: (time.time() - time.mktime(time.strptime(t, "%Y-%m-%d %H:%M"))) / 3600 if t else 1e9
            newest = bool(every and http.API_KEY and age(last.get("full_at")) < every)
            if newest and last.get("ok") and age(last.get("at")) < 20:
                log(f"{name}: checked at {last['at']}, next check tomorrow (API quota)")
                continue
            try:
                fresh = SOURCES[name].search(log=log, **({"newest_only": True} if newest else {}))
                seen = {l["id"] for l in fresh}
                complete = not newest and not getattr(SOURCES[name].search, "failed_pages", None)
                for l in listings.values():
                    if complete and l["source"] == name and l["id"] not in seen:
                        l["active"] = False
                listings = merge(listings, fresh)
                now = time.strftime("%Y-%m-%d %H:%M")
                status[name] = {"ok": True, "count": len(fresh) if not newest else last.get("count"), "complete": complete, "at": now,
                                "mode": "newest" if newest else "full", "full_at": now if complete else last.get("full_at")}
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
    for rank, l in enumerate(cands):
        src = SOURCES.get(l["source"])
        if hasattr(src, "enrich") and not l.get("enriched") and enriched < args.max_enrich:
            try:
                src.enrich(l)
                enriched += 1
                if l.get("lat") is not None:
                    l["geo"] = geo.describe(l["lat"], l["lng"])
            except Exception as e:
                log(f"enrich failed {l['id']}: {e}")
            if score.hard_filters(l):  # full data can rule it out before spending an AI read
                continue
        if rank >= config.AI_TOP_N or tags.get(l["id"], {}).get("dismissed"):
            continue  # photo reads only for the top candidates, and never for houses Tomás dismissed
        cache = ai._load()
        if l["id"] not in cache and any(_twins(l, o) and o["id"] in cache for o in listings.values()):
            continue  # same property already read under another source; dedupe keeps that one
        ai.analyse(l, log=log)

    cache = ai._load()
    for l in listings.values():
        res = cache.get(l["id"])
        if res is None and l.get("active"):
            twin = next((o for o in listings.values() if o["id"] in cache and _twins(l, o)), None)
            res = cache[twin["id"]] if twin else None
        l["ai"] = res
        l.update(score.score(l, res))


    dedupe(listings.values())
    # Final AI verdict for the top candidates: reads everything, including Tomás's preferences and notes,
    # and its score overrides ours. Listings he dismissed in the app are skipped.
    prefs = open(PREFS).read() if os.path.exists(PREFS) else ""
    top = sorted((l for l in listings.values() if l.get("active") and l.get("ai") and not l["discard"]
                  and not tags.get(l["id"], {}).get("dismissed")), key=lambda l: -l["score"])[:config.AI_TOP_N]
    top_ids = {l["id"] for l in top}
    for l in listings.values():
        l["score_calc"] = l["score"]
        if not l.get("ai") or l["discard"]:
            continue
        v = ai.final(l, prefs, tags.get(l["id"], {}).get("note", ""), compute=l["id"] in top_ids, log=log)
        if v:
            l["ai_final"] = {k: v[k] for k in ("score", "brief", "reasons", "at")}
            l["score"] = v["score"]
    # Percentile of each score among every listing ever scored (listings.json keeps inactive ones too).
    # Frozen the first time a listing gets a score; the app can recompute all of them on demand.
    hist = sorted(l["score"] for l in listings.values())
    for l in listings.values():
        if l.get("pct") is None or l.get("pct_score") != l["score"]:
            l["pct"] = round(100 * bisect.bisect_left(hist, l["score"]) / max(1, len(hist)))
            l["pct_score"], l["pct_n"] = l["score"], len(hist)
    if os.path.exists(DATA):
        status = {**json.load(open(DATA)).get("status", {}), **status}
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
