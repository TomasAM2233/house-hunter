"""Zonaprop: search pages embed window.__PRELOADED_STATE__ with full posting data incl. coordinates."""
import json, re, time
from bs4 import BeautifulSoup
from .. import http, config, sweeps

BASE = "https://www.zonaprop.com.ar"
# Zonaprop blocks cloud IPs, so requests go through the unblocking APIs in http.py. With ScrapingAnt the page
# arrives whole (JSON state included) for 1 credit. With only ScraperAPI it must be rendered (10 credits a page),
# so to fit its free 1,000 credits a month the full sweep (~11 pages) runs every FULL_EVERY_HOURS and other days
# only the newest page (NEW_PAGES, sorted by publication date). Quick runs always check just the newest pages.
FULL_EVERY_HOURS = 24 * 14
NEW_PAGES = 1
_dec = json.JSONDecoder()


# Zonaprop answers pages 10+ of a search with a bot wall (HTTP 423 through ScrapingAnt), so the full sweep
# splits the price range into bands that each fit in fewer pages (and splits a band again if it still overflows).
BANDS = [(None, 150_000), (150_000, 185_000), (185_000, 210_000), (210_000, None)]
# The CABA barrios along Subte B/D: ~1.200 listings in one search (2026-11-02), mostly at the top of the range.
BANDS_CABA = [(None, 140_000), (140_000, 160_000), (160_000, 175_000), (175_000, 190_000), (190_000, 205_000),
              (205_000, 215_000), (215_000, 228_000), (228_000, None)]
MAX_PAGES = 9


# Zonaprop's slug for the Vicente López barrio. Combined with other barrios in one URL it widens to the whole
# partido (Munro, Carapachay…), so it gets a search of its own; it fits in 2 pages, no price bands needed.
OWN_SEARCH = {"Vicente López": "vicente-lopez-vicente-lopez"}
CABA_SLUGS = {"Núñez": "nunez", "Villa Ortúzar": "villa-ortuzar", "San Nicolás": "san-nicolas"}
# Each group gets a full sweep once every EVERY_HOURS (see hh/sweeps.py); the other runs read its newest page.
EVERY_HOURS = 24


def _slug(z):
    return CABA_SLUGS.get(z) or z.lower().replace(" ", "-")


def zone_groups():
    """[(slug, price bands)]: the regular Vicente López barrios together, each OWN_SEARCH one on its own, and the
    CABA barrios together (Zonaprop keeps a multi-barrio CABA search within those barrios)."""
    zs = config.SEARCH["zones_gba"]
    together = "-".join(_slug(z) for z in zs if z not in OWN_SEARCH)
    caba = "-".join(_slug(z) for z in config.SEARCH["zones_caba"])
    return (([(together, BANDS)] if together else []) + [(OWN_SEARCH[z], [(None, None)]) for z in zs if z in OWN_SEARCH]
            + ([(caba, BANDS_CABA)] if caba else []))


def group_zones(slug):
    """The search zones a group covers, for marking what a complete sweep didn't see as gone."""
    if slug in OWN_SEARCH.values():
        return {z for z, v in OWN_SEARCH.items() if v == slug}
    return {z for z in config.SEARCH["zones"] if z not in OWN_SEARCH and re.search(rf"(^|-){_slug(z)}(-|$)", slug)}


def search_url(page, newest=False, band=(None, None), zones=None):
    s = config.SEARCH
    lo, hi = band[0] or s["price_min"], band[1] or s["price_ceiling"]
    zones = zones or zone_groups()[0][0]
    if lo >= hi:
        raise ValueError(f"empty band {band}")
    suffix = ("-orden-publicado-descendente" if newest else "") + ("" if page == 1 else f"-pagina-{page}")
    return f"{BASE}/casas-ph-venta-{zones}-mas-de-{s['min_ambientes']}-ambientes-{lo}-{hi}-dolar{suffix}.html"


def _state(html):
    i = html.index("window.__PRELOADED_STATE__ =") + len("window.__PRELOADED_STATE__ =")
    return _dec.raw_decode(html[i:].lstrip())[0]


def _feat(p, fid):
    f = (p.get("mainFeatures") or {}).get(fid)
    try:
        return float(f["value"]) if f else None
    except (TypeError, ValueError):
        return None


def _zone(loc):
    """Search zone from Zonaprop's location chain ("Palermo Soho" < "Palermo" < "Capital Federal"), or its own name."""
    chain, l = [], loc
    while l:
        chain.append(l.get("name"))
        l = l.get("parent")
    return config.barrio(*chain) or loc.get("name")


def _normalize(p):
    price = None
    for op in p.get("priceOperationTypes") or []:
        for pr in op.get("prices") or []:
            if pr.get("currency") == "USD":
                price = pr.get("amount")
    loc = p.get("postingLocation") or {}
    geo = ((loc.get("postingGeolocation") or {}).get("geolocation")) or {}
    tags = {f.get("label"): f.get("value") for f in (p.get("mainFeatures") or {}).values()}
    pics = [x.get("url730x532") for x in (p.get("visiblePictures") or {}).get("pictures", []) if x.get("url730x532")]
    rtype = (p.get("realEstateType") or {}).get("name", "")
    pills = " ".join([p.get("triggerPill") or ""] + [str(x) for x in p.get("trigger_pills") or []])
    return {
        "id": f"zp-{p['postingId']}",
        "source": "zonaprop",
        "url": BASE + p["url"],
        "title": p.get("title") or p.get("generatedTitle"),
        "type": "ph" if rtype == "PH" else "casa" if rtype == "Casas" else rtype.lower(),
        "price_usd": price,
        "total_m2": _feat(p, "CFT100"),
        "covered_m2": _feat(p, "CFT101"),
        "ambientes": _feat(p, "CFT1"),
        "bedrooms": _feat(p, "CFT2"),
        "bathrooms": _feat(p, "CFT3"),
        "garage": _feat(p, "CFT7") or 0,
        "age_years": _feat(p, "CFT5"),
        "address": ((loc.get("address") or {}).get("name") or "") + ", " + ((loc.get("location") or {}).get("name") or ""),
        "zone": _zone(loc.get("location") or {}),
        "address_exact": (loc.get("address") or {}).get("visibility") == "EXACT",
        "lat": geo.get("latitude"),
        "lng": geo.get("longitude"),
        "description": p.get("descriptionNormalized") or "",
        "photos": pics,
        "tags": tags,
        "credit_pill": "credito" in pills.lower() or "crédito" in pills.lower(),
        "publisher": (p.get("publisher") or {}).get("name"),
        "modified": p.get("modified_date"),
    }


def _num(text):
    m = re.search(r"\d+(?:[.,]\d+)*", text or "")
    return float(m.group(0).replace(".", "").replace(",", ".")) if m else None


def _dom_cards(html):
    """Rendered search page (the API path): the JSON state is gone, the cards carry the essentials."""
    s = BeautifulSoup(html, "html.parser")
    for c in s.select('[data-qa="posting PROPERTY"]'):
        href = c.get("data-to-posting", "").split("?")[0]
        feats = [x.get_text(" ", strip=True) for x in c.select('[data-qa="POSTING_CARD_FEATURES"] span')]
        f = lambda pat: next((_num(x) for x in feats if re.search(pat, x)), None)
        price = c.select_one('[data-qa="POSTING_CARD_PRICE"]')
        price = price.get_text(" ", strip=True) if price else ""
        street = c.select_one('[class*="location-address"]')
        where = c.select_one('[data-qa="POSTING_CARD_LOCATION"]')
        where = where.get_text(" ", strip=True) if where else ""
        street = street.get_text(" ", strip=True) if street else ""
        zone = config.barrio(*[w.strip() for w in where.split(",")]) or where.split(",")[0]
        imgs = [i.get("src") or i.get("data-flickity-lazyload") or "" for i in c.select('[data-qa="POSTING_CARD_GALLERY"] img')]
        alt = (c.select_one('[data-qa="POSTING_CARD_GALLERY"] img') or {}).get("alt", "") if c.select_one('[data-qa="POSTING_CARD_GALLERY"] img') else ""
        logo = c.select_one('[data-qa="POSTING_CARD_PUBLISHER"] img, [class*="publisher"] img')
        desc = c.select_one('[data-qa="POSTING_CARD_DESCRIPTION"]')
        pills = c.get("data-to-posting", "")
        yield {
            "id": f"zp-{c['data-id']}",
            "source": "zonaprop",
            "url": BASE + href,
            "title": alt.split(" · ")[-1] if alt else "",
            "type": "ph" if "-ph-" in href or alt.startswith("PH") else "casa",
            "price_usd": _num(price) if "USD" in price else None,
            "total_m2": f(r"m² tot"),
            "covered_m2": f(r"m² cub"),
            "ambientes": f(r"amb"),
            "bedrooms": f(r"dorm"),
            "bathrooms": f(r"baño"),
            "garage": f(r"coch"),
            "age_years": None,
            "address": f"{street}, {zone}",
            "geocode_query": f"{re.sub(r' al ', ' ', street, flags=re.I)}, {config.geocode_suffix(zone)}" if street else None,
            "zone": zone,
            "address_exact": bool(re.search(r"\d", street)) and " al " not in street,
            "lat": None,
            "lng": None,
            "description": desc.get_text(" ", strip=True) if desc else "",
            "photos": list(dict.fromkeys(re.sub(r"/\d+x\d+/", "/720x532/", u.split("?")[0]) for u in imgs if "zonapropcdn" in u)),
            "tags": {},
            "credit_pill": "cr%C3%A9dito" in pills or "credito" in pills.lower(),
            "publisher": logo.get("alt") if logo else None,
            "modified": None,
            "card_only": True,
        }


def _sweep(zones, band, newest, max_pages, log, out, failed):
    """Read one search (a group, a price band) page by page. A band that doesn't fit in max_pages is split in two."""
    page, total_pages = 1, 1
    while page <= min(total_pages, max_pages):
        try:
            st = _state(http.get(search_url(page, newest, band, zones), pause=(3, 7), via_api=True).text)["listStore"]
        except Exception as e:
            log(f"zonaprop {zones[:40]} {band} page {page}: {e}")
            failed.append((zones, band, page))
            if page == 1 and newest:
                raise
            page += 1
            continue
        total_pages = st["paging"]["totalPages"]
        if page == 1 and total_pages > max_pages and not newest:
            lo, hi = band[0] or config.SEARCH["price_min"], band[1] or config.SEARCH["price_ceiling"]
            if hi - lo >= 10_000:
                mid = (lo + hi) // 2 // 1000 * 1000
                log(f"zonaprop {zones[:40]} {band}: {total_pages} pages, splitting at {mid}")
                _sweep(zones, (band[0], mid), newest, max_pages, log, out, failed)
                _sweep(zones, (mid, band[1]), newest, max_pages, log, out, failed)
                return
            failed.append((zones, band, "overflow"))
        items = [_normalize(p) for p in st["listPostings"] if p.get("postingType") == "PROPERTY"]
        out += items
        log(f"zonaprop {zones[:40]} {band} page {page}/{total_pages}: {len(items)} listings")
        page += 1


def search(max_pages=MAX_PAGES, log=print, newest_only=False):
    """Every group: a full sweep when it's due (hh/sweeps.py), else its newest page. search.swept = the zones of
    the groups swept in full without failures, the only ones where a listing not seen means it's gone."""
    if http.API_KEY and not http.ANT_KEY:
        return search_rendered(20 if not newest_only else NEW_PAGES, log, newest_only)
    out, failed, swept, err = [], [], set(), None
    for zones, bands in zone_groups():
        key = f"zonaprop:{zones}"
        full = not newest_only and sweeps.due(key, EVERY_HOURS)
        before = len(failed)
        for band in bands if full else [(None, None)]:
            try:
                _sweep(zones, band, not full, max_pages if full else NEW_PAGES, log, out, failed)
            except Exception as e:  # a newest page that didn't come through; the other groups still get read
                err = e
        if full:
            sweeps.done(key)  # even with a failed page: one full sweep a day is what the free credits allow
        if full and len(failed) == before:
            swept |= group_zones(zones)
    if failed:
        log(f"zonaprop: pages {failed} failed; their listings keep their previous state")
    search.failed_pages, search.swept = failed, swept
    if not out and failed:
        raise err or RuntimeError("zonaprop: no page got through")
    return out


def search_rendered(max_pages=20, log=print, newest=False):
    out, failed = {}, []
    for g, (zones, _) in enumerate(zone_groups()):
        page, total_pages = 1, 1
        while page <= min(total_pages, max_pages):
            try:
                html = http.get(search_url(page, newest, zones=zones), via_api=True, render=True).text
                cards = list(_dom_cards(html))
                if not cards:
                    raise RuntimeError("no cards in rendered page")
            except Exception as e:
                log(f"zonaprop {zones} page {page}: {e}")
                failed.append((zones, page))
                if page == 1 and g == 0:
                    raise
                if page == 1:
                    break
                page += 1
                continue
            if page == 1:
                n = re.search(r"<title>\s*([\d.]+)", html)  # "306 Casas o PH ..."; the pager only shows 5 pages
                total_pages = -(-int(n.group(1).replace(".", "")) // 30) if n else 1
            for c in cards:
                out.setdefault(c["id"], c)
            log(f"zonaprop {zones} page {page}/{total_pages}: {len(cards)} listings (rendered via API)")
            page += 1
    search_rendered.failed_pages = search.failed_pages = failed
    return list(out.values())


def enrich(listing):
    """Fetch the detail page for the full description and every photo.
    When only ScraperAPI is available a detail page would cost 10 credits, so the card's data is kept as is."""
    if http.API_KEY and not http.ANT_KEY:
        listing["enriched"] = True
        return listing
    html = http.get(listing["url"], via_api=True).text
    s = BeautifulSoup(html, "html.parser")
    d = s.select_one("#reactDescription") or s.select_one("#longDescription")
    if d:
        text = d.get_text("\n", strip=True)
        listing["description"] = text.split("Ver datos")[0].strip()
    seen = list(dict.fromkeys(re.findall(r"https://imgar\.zonapropcdn\.com/avisos/[^\"' ]+?/1200x1200/(\d+)\.jpg", html)))
    base = listing["photos"][0].rsplit("/", 2)[0] if listing["photos"] else None
    if base:
        photos = [f"{base}/720x532/{pid}.jpg" for pid in seen]
        # keep the search page's cover photo first
        cover = listing["photos"][0].split("?")[0]
        listing["photos"] = [cover] + [p for p in photos if p != cover]
    feats = [" ".join(li.get_text(" ", strip=True).split()) for li in s.select("#section-icon-features-property li, ul.section-general-features li")]
    if feats:
        listing["features_text"] = feats
    listing["enriched"] = True
    return listing
