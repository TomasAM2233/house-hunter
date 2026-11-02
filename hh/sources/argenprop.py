"""Argenprop: server-rendered cards (div.listing__item). Its WAF blocks cloud IPs, so requests go through ScraperAPI."""
import re
from bs4 import BeautifulSoup
from .. import http, config, sweeps

BASE = "https://www.argenprop.com"
FULL_EVERY_HOURS = 24 * 7  # with only ScraperAPI: newest pages daily, full sweep weekly; see zonaprop.py for the free API quota
NEW_PAGES = 2
EVERY_HOURS = 24  # with ScrapingAnt: each group swept in full once a day, its newest pages on every other run (hh/sweeps.py)


SLUGS = {"Vicente López": "vicente-lopez-vicente-lopez",  # the barrio; plain "vicente-lopez" is the partido
         "Núñez": "nunez", "Villa Ortúzar": "villa-ortuzar", "San Nicolás": "san-nicolas"}


def groups():
    """[(name, zones)]: Vicente López's barrios in one search, the CABA barrios along Subte B/D in another."""
    s = config.SEARCH
    return [(n, zs) for n, zs in (("gba", s["zones_gba"]), ("caba", s["zones_caba"])) if zs]


# The CABA search has ~1.300 listings (64 pages) and Argenprop's deep pages come back empty, so its full sweep goes
# by price bands, each split again when it still has more than MAX_PAGES pages.
BANDS_CABA = [(None, 140_000), (140_000, 160_000), (160_000, 175_000), (175_000, 190_000), (190_000, 205_000),
              (205_000, 215_000), (215_000, 228_000), (228_000, None)]
MAX_PAGES = 25


def search_url(page, newest=False, zones=None, band=(None, None)):
    s = config.SEARCH
    zones = "-o-".join(SLUGS.get(z) or z.lower().replace(" ", "-") for z in (zones or s["zones_gba"]))
    lo, hi = band[0] or s["price_min"], band[1] or s["price_ceiling"]
    q = (["orden-masnuevos"] if newest else []) + ([f"pagina-{page}"] if page > 1 else [])
    return f"{BASE}/casas-o-ph/venta/{zones}/dolares-{lo}-{hi}" + ("?" + "&".join(q) if q else "")


def _n(text):
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group(0).replace(".", "").replace(",", ".")) if m else None


def _feat(feats, pattern):
    for f in feats:
        if re.search(pattern, f, re.I):
            return _n(f)
    return None


def _photo(src):
    """Card and gallery images are *_u_small / *_u_medium; the bare uuid is the full-size file."""
    return re.sub(r"_u_[a-z]+\.jpg", ".jpg", src)


def _card(it, in_caba=False):
    a = it.select_one("a.card")
    if not a or a.get("idmoneda") != "2":  # 2 = USD
        return None
    feats = [" ".join(li.get_text(" ", strip=True).split()) for li in it.select(".card__main-features li")]
    address = " ".join(it.select_one(".card__address").get_text(" ", strip=True).split()) if it.select_one(".card__address") else ""
    street, _, zone = address.rpartition(",")
    title = it.select_one(".card__title")
    desc = it.select_one(".card__title-description")
    pics = [_photo(img.get("src") or img.get("data-src") or "") for img in it.select(".card__photos img")]
    agent = it.select_one(".card__agent-name")
    href = a["href"]
    return {
        "id": f"ap-{a['idaviso']}",
        "source": "argenprop",
        "url": BASE + href,
        "title": title.get_text(" ", strip=True) if title else "",
        "type": "ph" if href.startswith("/ph-") else "casa" if href.startswith("/casa-") else href.split("-")[0].strip("/"),
        "price_usd": float(a.get("montooperacion") or 0) or None,
        "total_m2": _feat(feats, r"m² tot"),
        "covered_m2": _feat(feats, r"m² cub"),
        "ambientes": _feat(feats, r"ambiente"),
        "bedrooms": _feat(feats, r"dorm"),
        "bathrooms": _feat(feats, r"baño"),
        "garage": None,
        "age_years": _feat(feats, r"año"),
        "address": address,
        "geocode_query": f"{re.sub(r' al ', ' ', street.strip(), flags=re.I)}, {config.geocode_suffix(config.barrio(zone.strip()) or zone.strip(), in_caba)}",
        "zone": config.barrio(zone.strip()) or zone.strip(),
        "address_exact": bool(re.search(r"\d", street) and " al " not in street),
        "lat": None,
        "lng": None,
        "description": desc.get_text("\n", strip=True) if desc else "",
        "photos": [p for p in pics if "static-content" in p],
        "tags": {},
        "credit_pill": bool(re.search(r"apto cr[eé]dito", it.get_text(" "), re.I)),
        "publisher": agent.get_text(strip=True) if agent else None,
        "modified": None,
        "partial_data": True,
    }


def _sweep(zones, in_caba, newest, max_pages, log, out, failed, band=(None, None)):
    page, last = 1, 1
    while page <= min(last, max_pages):
        try:
            html = http.get(search_url(page, newest, zones, band), via_api=True).text
        except Exception as e:
            log(f"argenprop {'CABA' if in_caba else 'VL'} page {page}: {e}")
            failed.append(page)
            if page == 1:
                raise
            page += 1
            continue
        s = BeautifulSoup(html, "html.parser")
        if page == 1:
            pages = [int(p) for p in re.findall(r"[?&]pagina-(\d+)", html)]
            last = max(pages, default=1)
            lo, hi = band[0] or config.SEARCH["price_min"], band[1] or config.SEARCH["price_ceiling"]
            if last > max_pages and not newest and hi - lo >= 10_000:
                mid = (lo + hi) // 2 // 1000 * 1000
                log(f"argenprop {band}: {last} pages, splitting at {mid}")
                _sweep(zones, in_caba, newest, max_pages, log, out, failed, (band[0], mid))
                _sweep(zones, in_caba, newest, max_pages, log, out, failed, (mid, band[1]))
                return
        items = [c for c in (_card(it, in_caba) for it in s.select("div.listing__item") if not it.find_parent(class_="listing-container--suggested")) if c]
        for c in items:
            out.setdefault(c["id"], c)
        log(f"argenprop {'CABA' if in_caba else 'VL'} {band if band != (None, None) else ''} page {page}/{last}: {len(items)} listings")
        page += 1


def search(max_pages=MAX_PAGES, log=print, newest_only=False):
    """Each group: a full sweep when due (hh/sweeps.py), else its newest pages. search.swept = zones swept in full."""
    out, failed, swept, err = {}, [], set(), None
    for name, zones in groups():
        key = f"argenprop:{name}"
        # with only ScraperAPI, run.py already spaces out full sweeps (newest_only); with ScrapingAnt, once a day
        full = not newest_only and (not http.ANT_KEY or sweeps.due(key, EVERY_HOURS))
        before = len(failed)
        bands = BANDS_CABA if full and name == "caba" else [(None, None)]
        for band in bands:
            try:
                _sweep(zones, name == "caba", not full, max_pages if full else NEW_PAGES, log, out, failed, band)
            except Exception as e:
                failed.append(f"{name}:{band}")
                err = e
        if full and len(failed) == before:
            sweeps.done(key)
            swept |= set(zones)
    search.failed_pages, search.swept = failed, swept
    if not out and failed:
        raise err or RuntimeError("argenprop: no page got through")
    return list(out.values())


def enrich(l):
    """Item page: total/lot m², garage, full description and every photo. No map pin; geocoded from the address."""
    html = http.get(l["url"], via_api=True).text
    s = BeautifulSoup(html, "html.parser")
    main = [" ".join(li.get_text(" ", strip=True).split()) for li in s.select(".property-main-features li")]
    feats = [" ".join(li.get_text(" ", strip=True).split()) for li in s.select(".property-features li")]
    l["total_m2"] = _feat(main, r"m² (total|terreno)") or l.get("total_m2")
    l["covered_m2"] = _feat(main, r"m² cubierta") or l.get("covered_m2")
    l["lot_m2"] = _feat(main + feats, r"m² terreno|sup\. terreno|superficie del terreno") or l.get("lot_m2")
    l["uncovered_m2"] = _feat(main, r"m² descubierta") or l.get("uncovered_m2")
    l["garage"] = _feat(feats, r"cocheras") or _feat(main, r"cochera") or 0
    l["age_years"] = _feat(feats, r"antig") or l.get("age_years")
    l["features_text"] = (main + feats)[:40]
    d = s.select_one(".section-description")
    if d:
        l["description"] = d.get_text("\n", strip=True).replace("Descripción\n", "", 1)
    # the gallery shows up as full URLs, protocol-relative or root-relative paths and in data-src/srcset, so match the path
    paths = re.findall(r"/static-content/\d+/[0-9a-f-]{20,}(?:_u_[a-z]+)?\.(?:jpe?g|webp|png)", html, re.I)
    pics = list(dict.fromkeys(_photo("https://www.argenprop.com" + p) for p in paths))
    own = l["photos"][0].split("/static-content/")[1].split("/")[0] if l.get("photos") else None
    if own:
        pics = [p for p in pics if f"/static-content/{own}/" in p]  # drop agent logos and other listings
    if pics:
        l["photos"] = pics[:60]
    l["partial_data"] = not (l.get("total_m2") and l.get("description"))
    l["enriched"] = True
    return l
