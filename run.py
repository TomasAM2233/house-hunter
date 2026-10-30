"""Full pipeline: scrape -> merge history -> geo -> enrich + AI for candidates -> score -> data/listings.json.

python run.py                 # scrape everything enabled and rescore
python run.py --no-scrape     # just rescore what we already have (e.g. after editing weights or AI results)
python run.py --assess-queue  # AI reads asked for from the app (data/ai_requests/), results in data/ai_results.json
"""
import argparse, bisect, json, os, re, shutil, sys, time, traceback
import requests
from hh import ai, config, geo, http, score, text
import osm_parks
from hh.sources import argenprop, zonaprop, mercadolibre, tokko

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "listings.json")
PREFS = os.path.join(ROOT, "data", "preferences.md")   # Tomás's own words; edited from the app or on GitHub
SETTINGS = os.path.join(ROOT, "data", "settings.json")  # alert thresholds, saved by the app
TAGS = os.path.join(ROOT, "data", "tags.json")         # favourite / visited / dismissed + notes, saved by the app
WEB_DATA = os.path.join(ROOT, "web", "listings.json")
REQUESTS = os.path.join(ROOT, "data", "ai_requests")    # one file per "Evaluar con IA" tap in the app
RESULTS = os.path.join(ROOT, "data", "ai_results.json") # the re-scored listings for those taps; the app polls it
PHOTOS_V = 2      # bump to fetch item pages again for listings stored with only the search card's photos
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
                for k in ("enriched", "description", "photos", "features_text", "partial_data", "photos_v"):
                    if k not in prev:
                        continue
                    longer = k == "description" and len(prev[k] or "") > len(l.get(k) or "")
                    if prev.get("enriched") or not l.get(k) or longer:
                        l[k] = prev[k]
                for k in ("total_m2", "covered_m2", "lot_m2", "bedrooms", "bathrooms", "garage", "age_years", "address_exact", "publisher", "modified"):
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


def side_percentiles(listings):
    """Percentiles that sit next to the score's (and matter less): covered m2, USD/m2 (cheaper = higher) and m2 still
    buildable, each among every listing that has the number. Recomputed on every run, unlike the score's."""
    ls = [l for l in listings if not l.get("duplicate_of")]
    get = {"m2": lambda l: l.get("covered_m2"), "ppm2": score.ppm2, "build": score.buildable_left}
    for l in ls:
        l["pcts"], l["build_m2"] = {}, score.buildable_left(l)
    for k, f in get.items():
        vals = sorted(v for v in map(f, ls) if v is not None)
        for l in ls:
            v = f(l)
            below = None if v is None else bisect.bisect_left(vals, v) if k != "ppm2" else len(vals) - bisect.bisect_right(vals, v)
            l["pcts"][k] = None if v is None else round(100 * below / max(1, len(vals)))


def big_lot(l):
    """Tomás's standing alert: 300+ m2 (lot, else total) under USD 230k, 4 to 8 cuadras from Maipú."""
    r = config.ALERT_BIG_LOT
    m2, _ = score.lot_m2(l)
    g = l.get("geo") or {}
    return bool(m2 and m2 >= r["min_m2"] and l.get("price_usd") and l["price_usd"] < r["max_price"]
                and g.get("maipu_blocks") is not None and r["maipu_blocks"][0] <= g["maipu_blocks"] <= r["maipu_blocks"][1])


def alert(new):
    """Push a phone notification (ntfy.sh, topic in NTFY_TOPIC) for each new listing that ranks near the top,
    or that is a big lot at a good price around the Maipú sweet spot."""
    topic = os.environ.get("NTFY_TOPIC")
    st = json.load(open(SETTINGS)) if os.path.exists(SETTINGS) else {}   # thresholds edited in the app
    min_pct = st.get("alert_percentile", config.ALERT_PERCENTILE)
    min_ai = st.get("alert_ai_score", config.ALERT_AI_SCORE)
    for l in sorted(new, key=lambda l: -l["score"]):
        lot = big_lot(l)
        good = l.get("pct", 0) >= min_pct or (l.get("ai_final") or {}).get("score", 0) >= min_ai
        if not (good or lot):
            continue
        g = l.get("geo") or {}
        m2, what = score.lot_m2(l)
        title = (f"{m2:.0f} m² {what} · " if lot else "") + f"P{l.get('pct')} · {l['score']:.0f}/100 · USD {l['price_usd'] or 0:,.0f} · {l.get('zone') or ''}"
        body = (brief if (brief := (l.get("ai_final") or {}).get("brief")) else
                f"{l.get('total_m2') or '?'} m² tot, {l.get('ambientes') or '?'} amb, {g.get('maipu_blocks', '?')} cdas a Maipú. {l.get('address', '')}")
        log(f"ALERT {l['id']}: {title}")
        if not topic:
            continue
        try:
            requests.post("https://ntfy.sh/", timeout=20, json={"topic": topic, "title": title, "message": body,
                                                                  "click": f"{config.SITE_URL}#casa={l['id']}", "priority": 4, "tags": ["house"],
                                                                  "actions": [{"action": "view", "label": "Ver aviso original", "url": l["url"]}]})
        except Exception as e:
            log(f"alert failed: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-scrape", action="store_true")
    ap.add_argument("--sources", default=os.environ.get("HH_SOURCES", "zonaprop,argenprop,tokko,mercadolibre"))
    ap.add_argument("--max-enrich", type=int, default=150)
    ap.add_argument("--quick", action="store_true", help="only the newest pages of the sites that support it, to catch new listings fast")
    ap.add_argument("--assess", default="", help="comma-separated ids: fresh AI read + verdict for just these, now")
    ap.add_argument("--assess-queue", action="store_true", help="--assess with the ids the app queued in data/ai_requests/")
    args = ap.parse_args()
    queued = sorted(f for f in os.listdir(REQUESTS) if f.endswith(".json")) if args.assess_queue and os.path.isdir(REQUESTS) else []
    requested = {}  # id -> when it was asked for
    for f in queued:
        try:
            requested[f[:-5]] = json.load(open(os.path.join(REQUESTS, f))).get("at")
        except Exception:
            requested[f[:-5]] = None
    requested.update({i: None for i in args.assess.split(",") if i})
    if args.assess_queue and not requested:
        log("nothing queued")
        return
    if requested:
        args.no_scrape = True

    listings = load()
    known = set(listings)
    tags = json.load(open(TAGS)) if os.path.exists(TAGS) else {}
    status = {}
    prev = json.load(open(DATA)).get("status", {}) if os.path.exists(DATA) else {}
    if not args.no_scrape:
        for name in args.sources.split(","):
            src, last = SOURCES[name], prev.get(name, {})
            age = lambda t: (time.time() - time.mktime(time.strptime(t, "%Y-%m-%d %H:%M"))) / 3600 if t else 1e9
            if args.quick:
                if not hasattr(src, "NEW_PAGES"):
                    continue
                if name == "zonaprop" and not http.ANT_KEY and age(last.get("at")) < 20:
                    continue  # ScraperAPI renders cost 10 credits: once a day is all the free plan allows
                newest = True
            else:
                # with only ScraperAPI (render = 10 credits a page) full sweeps are spaced out; ScrapingAnt has room for every run
                every = getattr(src, "FULL_EVERY_HOURS", None) if http.API_KEY and not http.ANT_KEY else None
                newest = bool(every and age(last.get("full_at")) < every)
            try:
                fresh = SOURCES[name].search(log=log, **({"newest_only": True} if newest else {}))
                seen = {l["id"] for l in fresh}
                complete = not newest and not getattr(SOURCES[name].search, "failed_pages", None)
                for l in listings.values():
                    if complete and l["source"] == name and l["id"] not in seen:
                        l["active"] = False  # kept for the percentile history; shown as "Reservada"
                        l.setdefault("gone_at", TODAY)
                listings = merge(listings, fresh)
                now = time.strftime("%Y-%m-%d %H:%M")
                status[name] = {"ok": True, "count": len(fresh) if not newest else last.get("count"), "complete": complete, "at": now,
                                "mode": "newest" if newest else "full", "full_at": now if complete else last.get("full_at")}
            except Exception as e:
                traceback.print_exc()
                status[name] = {"ok": False, "error": str(e)[:200], "at": time.strftime("%Y-%m-%d %H:%M")}

    # geography
    if not os.path.exists(geo.PARKS):
        osm_parks.fetch(log=log)  # once; refreshed by hand with the osm workflow
    for l in listings.values():
        if not l.get("price_usd") and text.usd_price(l.get("description")):
            l["price_usd"] = text.usd_price(l["description"])  # cards that only say "consultar" or show pesos
        if l.get("lat") is not None and l.get("zone") and not geo.in_area(l["lat"], l["lng"]):
            # the agent dropped the pin somewhere else (seen: a CABA street with the same name); trust the address
            l["lat"] = l["lng"] = None
            l["address_exact"] = False
            l["geocode_query"] = l.get("geocode_query") or f"{re.sub(r' al ', ' ', l.get('address') or '', flags=re.I)}, Vicente López, Buenos Aires"
        if l.get("lat") is None and l.get("geocode_query"):
            ll = geo.geocode(l["geocode_query"])
            if ll:
                l["lat"], l["lng"] = ll
        l["geo"] = geo.describe(l["lat"], l["lng"]) if l.get("lat") is not None else None

    def enrich(l):
        try:
            SOURCES[l["source"]].enrich(l)
            l["photos_v"] = PHOTOS_V
            if l.get("lat") is not None:
                l["geo"] = geo.describe(l["lat"], l["lng"])
            return True
        except Exception as e:
            log(f"enrich failed {l['id']}: {e}")

    note = lambda l: tags.get(l["id"], {}).get("note", "")
    errors = {}
    if requested:
        # asked for from the app: the full item page (every photo) and a fresh read with his note, whatever the rank
        for i in requested:
            l = listings.get(i)
            if not l:
                errors[i] = "no la encontré en los datos"
                continue
            if hasattr(SOURCES.get(l["source"]), "enrich") and (not l.get("enriched") or l.get("photos_v", 0) < PHOTOS_V):
                enrich(l)
            try:
                ai.analyse(l, note(l), force=True, log=log)
            except Exception as e:
                errors[i] = "lectura de fotos: " + ("se acabó la cuota gratis de Gemini por hoy" if ai.EXHAUSTED else str(e)[:160])
    else:
        # enrich + AI only for active listings that survive the non-AI filters, best pre-score first
        cands = [l for l in listings.values() if l.get("active") and not score.hard_filters(l)]
        cands.sort(key=lambda l: -score.score(l)["score"])
        enriched = reads = 0
        for l in cands:
            # item pages for new candidates, and once more for ones stored with only the search card's few photos
            stale = not l.get("enriched") or (l.get("photos_v", 0) < PHOTOS_V and len(l.get("photos") or []) <= 8)
            if hasattr(SOURCES.get(l["source"]), "enrich") and stale and enriched < args.max_enrich:
                enriched += bool(enrich(l))
                if score.hard_filters(l):  # full data can rule it out before spending an AI read
                    continue
            if tags.get(l["id"], {}).get("dismissed"):
                continue  # never for houses Tomás dismissed
            if ai.budget_left() - reads < 2 and not ai.cached(l, current=True, note=note(l)):
                continue  # today's automatic quota is spent, keeping one verdict call for each house read in this run
            cache = ai._load()
            if l["id"] not in cache and any(_twins(l, o) and o["id"] in cache for o in listings.values()):
                continue  # same property already read under another source; dedupe keeps that one
            reads += not ai.cached(l, current=True, note=note(l))
            ai.analyse(l, note(l), log=log)

    cache = ai._load()
    for l in listings.values():
        res = cache.get(l["id"])
        if res is None and l.get("active"):
            twin = next((o for o in listings.values() if o["id"] in cache and _twins(l, o)), None)
            res = cache[twin["id"]] if twin else None
        l["ai"] = res
        l.update(score.score(l, res))


    dedupe(listings.values())
    side_percentiles(listings.values())
    # Final AI verdict for every candidate with a photo read, best first, while today's quota lasts: reads
    # everything, including Tomás's preferences and notes, and its score overrides ours. Skips what he dismissed.
    prefs = open(PREFS).read() if os.path.exists(PREFS) else ""
    for l in sorted(listings.values(), key=lambda l: -l["score"]):
        l["score_calc"] = l["score"]
        if not l.get("ai") or l["discard"]:
            continue
        if requested and l["id"] in requested and l["id"] not in errors:
            try:
                v = ai.final(l, prefs, note(l), force=True, log=log)
            except Exception as e:
                errors[l["id"]] = "evaluación: " + ("se acabó la cuota gratis de Gemini por hoy" if ai.EXHAUSTED else str(e)[:160])
                v = None
        else:
            due = l.get("active") and not tags.get(l["id"], {}).get("dismissed") and not requested
            v = ai.final(l, prefs, note(l), compute=due and ai.budget_left() >= 1, log=log)
        if v:
            l["ai_final"] = {k: v.get(k) for k in ("score", "brief", "reasons", "investment", "questions", "general_questions", "at")}
            l["score"] = v["score"]
    # Percentile of each score among every listing ever scored (listings.json keeps inactive ones too).
    # Frozen the first time a listing gets a score; the app can recompute all of them on demand.
    # Ranked on the algorithm's score, which every listing has on the same scale (the AI verdict covers only the top).
    hist = sorted(l["score_calc"] for l in listings.values())
    for l in listings.values():
        if l.get("pct") is None or l.get("pct_score") != l["score_calc"]:
            l["pct"] = round(100 * bisect.bisect_left(hist, l["score_calc"]) / max(1, len(hist)))
            l["pct_score"], l["pct_n"] = l["score_calc"], len(hist)
    alert(l for l in listings.values() if l["id"] not in known and l.get("active") and not l["discard"] and not l.get("duplicate_of"))
    if os.path.exists(DATA):
        status = {**json.load(open(DATA)).get("status", {}), **status}
    out = sorted(listings.values(), key=lambda l: (not l.get("active"), bool(l["discard"]), -l["score"]))
    payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M"), "status": status, "weights": config.WEIGHTS,
               "search": config.SEARCH, "reference": geo.reference(), "listings": out}
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(payload, open(DATA, "w"), ensure_ascii=False, indent=1)
    shutil.copy(DATA, WEB_DATA)
    if requested:
        # what the app polls for: the re-scored listing per request (last 12 kept)
        res = json.load(open(RESULTS)) if os.path.exists(RESULTS) else {}
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for i, at in requested.items():
            res.pop(i, None)
            res[i] = {"requested_at": at, "done_at": now, "error": errors.get(i), "listing": listings.get(i)}
            log(f"assessed {i}: " + (errors[i] if i in errors else f"{listings[i]['score']:.0f}/100"))
        json.dump(dict(list(res.items())[-12:]), open(RESULTS, "w"), ensure_ascii=False, indent=1)
        for f in queued:
            os.remove(os.path.join(REQUESTS, f))
    shortlist = [l for l in out if l.get("active") and not l["discard"]]
    pending = len([l for l in shortlist if not l.get("ai")])
    log(f"{len(out)} listings, {len(shortlist)} on the shortlist, {pending} waiting for AI")


if __name__ == "__main__":
    sys.exit(main())
