"""Argenprop: server-rendered cards (div.listing__item). Its WAF blocks cloud IPs, so requests go through ScraperAPI."""
import re
from bs4 import BeautifulSoup
from .. import http, config

BASE = "https://www.argenprop.com"
FULL_EVERY_HOURS = 24 * 7  # newest pages daily, full sweep weekly; see zonaprop.py for the free API quota
NEW_PAGES = 2


def search_url(page, newest=False):
    s = config.SEARCH
    zones = "-o-".join(z.lower().replace(" ", "-") for z in s["zones"])
    q = (["orden-masnuevos"] if newest else []) + ([f"pagina-{page}"] if page > 1 else [])
    return f"{BASE}/casas-o-ph/venta/{zones}/dolares-{s['price_min']}-{s['price_ceiling']}" + ("?" + "&".join(q) if q else "")


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


def _card(it):
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
        "geocode_query": f"{re.sub(r' al ', ' ', street.strip(), flags=re.I)}, {next((z for z in config.SEARCH["zones"] if z.lower() in zone.lower()), zone.strip())}, Vicente López, Buenos Aires",
        "zone": next((z for z in config.SEARCH["zones"] if z.lower() in zone.lower()), zone.strip()),
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


def search(max_pages=40, log=print, newest_only=False):
    if newest_only:
        max_pages = NEW_PAGES
    out, failed, page, last = {}, [], 1, 1
    while page <= min(last, max_pages):
        try:
            html = http.get(search_url(page, newest_only), via_api=True).text
        except Exception as e:
            log(f"argenprop page {page}: {e}")
            failed.append(page)
            if page == 1:
                raise
            page += 1
            continue
        s = BeautifulSoup(html, "html.parser")
        if page == 1:
            pages = [int(p) for p in re.findall(r"[?&]pagina-(\d+)", html)]
            last = max(pages, default=1)
        items = [c for c in (_card(it) for it in s.select("div.listing__item") if not it.find_parent(class_="listing-container--suggested")) if c]
        for c in items:
            out.setdefault(c["id"], c)
        log(f"argenprop page {page}/{last}: {len(items)} listings")
        page += 1
    search.failed_pages = failed
    return list(out.values())


def enrich(l):
    """Item page: total/lot m², garage, full description and every photo. No map pin; geocoded from the address."""
    html = http.get(l["url"], via_api=True).text
    s = BeautifulSoup(html, "html.parser")
    main = [" ".join(li.get_text(" ", strip=True).split()) for li in s.select(".property-main-features li")]
    feats = [" ".join(li.get_text(" ", strip=True).split()) for li in s.select(".property-features li")]
    l["total_m2"] = _feat(main, r"m² (total|terreno)") or l.get("total_m2")
    l["covered_m2"] = _feat(main, r"m² cubierta") or l.get("covered_m2")
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
