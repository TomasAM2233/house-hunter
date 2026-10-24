"""Zonaprop: search pages embed window.__PRELOADED_STATE__ with full posting data incl. coordinates."""
import json, re
from bs4 import BeautifulSoup
from .. import http, config

BASE = "https://www.zonaprop.com.ar"
# Zonaprop blocks cloud IPs, so requests go through ScraperAPI when SCRAPER_API_KEY is set.
# Its free plan has 1,000 requests a month, so run.py scrapes Zonaprop at most once every API_EVERY_HOURS.
API_EVERY_HOURS = 20
_dec = json.JSONDecoder()


def search_url(page):
    s = config.SEARCH
    zones = "-".join(z.lower().replace(" ", "-") for z in s["zones"])
    suffix = "" if page == 1 else f"-pagina-{page}"
    return f"{BASE}/casas-ph-venta-{zones}-mas-de-{s['min_ambientes']}-ambientes-{s['price_min']}-{s['price_max']}-dolar{suffix}.html"


def _state(html):
    i = html.index("window.__PRELOADED_STATE__ =") + len("window.__PRELOADED_STATE__ =")
    return _dec.raw_decode(html[i:].lstrip())[0]


def _feat(p, fid):
    f = (p.get("mainFeatures") or {}).get(fid)
    try:
        return float(f["value"]) if f else None
    except (TypeError, ValueError):
        return None


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
        "zone": (loc.get("location") or {}).get("name"),
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


def search(max_pages=20, log=print):
    out, page, total_pages, failed = [], 1, 1, []
    while page <= min(total_pages, max_pages):
        try:
            st = _state(http.get(search_url(page), pause=(3, 7), via_api=True).text)["listStore"]
        except Exception as e:
            log(f"zonaprop page {page}: {e}")
            failed.append(page)
            if page == 1:
                raise
            page += 1
            continue
        total_pages = st["paging"]["totalPages"]
        items = [_normalize(p) for p in st["listPostings"] if p.get("postingType") == "PROPERTY"]
        out += items
        log(f"zonaprop page {page}/{total_pages}: {len(items)} listings")
        page += 1
    if failed:
        log(f"zonaprop: pages {failed} were blocked; their listings keep their previous state")
    search.failed_pages = failed
    return out


def enrich(listing):
    """Fetch the detail page for the full description and every photo."""
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
