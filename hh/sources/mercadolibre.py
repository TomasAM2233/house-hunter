"""Mercado Libre Inmuebles: search pages embed 'polycard' JSON. Detail pages sit behind a login wall,
so we only get what the card shows (price, ambientes, covered m2, address, one photo)."""
import html as htmllib, json, re
from .. import http, config

BASE = "https://inmuebles.mercadolibre.com.ar"
ZONE_SLUGS = {"Olivos": "olivos", "Florida": "florida", "La Lucila": "la-lucila"}
_dec = json.JSONDecoder()
# ML sends most browser fingerprints to an account-verification wall; these older profiles get the page.
PROFILES = ["edge101", "chrome99", "safari15_5", "edge99"]


def _walled(r):
    return "account-verification" in str(r.url) or "poly-card" not in r.text and "polycard" not in r.text


def fetch(url):
    return http.get(url, impersonate=PROFILES, blocked=_walled, tries=6)


def search_url(kind, zone_slug, offset):
    s = config.SEARCH
    page = "" if offset == 0 else f"_Desde_{offset + 1}"
    return f"{BASE}/{kind}/venta/bsas-gba-norte/vicente-lopez/{zone_slug}/{page}_PriceRange_{s['price_min']}USD-{s['price_ceiling']}USD_NoIndex_True"


def _cards(html):
    for m in re.finditer(r'"polycard":\{', html):
        try:
            yield _dec.raw_decode(html[m.end() - 1:])[0]
        except ValueError:
            continue


def _html_cards(html):
    """Server-rendered grid (what the fallback browser profiles get): rebuild polycard-like dicts."""
    parts = html.split('<li class="ui-search-layout__item')[1:]
    for part in parts:
        a = re.search(r'href="(https://[^"#]*?/(MLA-?\d+)[^"#]*)[^"]*"[^>]*class="poly-component__title"[^>]*>([^<]*)<', part)
        if not a:
            continue
        price = re.search(r'aria-label="([\d.]+) (dólares|pesos)"', part)
        attrs = re.findall(r'poly-attributes_list__item[^>]*>([^<]+)<', part)
        loc = re.search(r'poly-component__location[^>]*>([^<]+)<', part)
        pic = re.search(r'D_NQ_NP_(?:2X_)?(\d+-MLA\d+_\d+)-', part)
        yield {
            "metadata": {"id": a.group(2).replace("-", ""), "url": a.group(1).split("://", 1)[1]},
            "components": [
                {"type": "title", "title": {"text": htmllib.unescape(a.group(3))}},
                {"type": "price", "price": {"current_price": {"value": float(price.group(1)) if price else None,
                                                             "currency": "USD" if price and price.group(2) == "dólares" else "ARS"}}},
                {"type": "attributes_list", "attributes_list": {"texts": [htmllib.unescape(x).strip() for x in attrs]}},
                {"type": "location", "location": {"text": htmllib.unescape(loc.group(1)) if loc else ""}},
            ],
            "pictures": {"pictures": [{"id": pic.group(1)}] if pic else []},
        }


def _num(pattern, texts):
    for t in texts:
        m = re.search(pattern, t.replace(".", ""))
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def _normalize(card, kind, zone):
    meta = card.get("metadata", {})
    comps = {c["type"]: c for c in card.get("components", [])}
    price = ((comps.get("price", {}).get("price") or {}).get("current_price") or {})
    texts = (comps.get("attributes_list", {}).get("attributes_list") or {}).get("texts", [])
    loc = (comps.get("location", {}).get("location") or {}).get("text", "")
    pics = [f"https://http2.mlstatic.com/D_NQ_NP_{p['id']}-O.jpg" for p in (card.get("pictures") or {}).get("pictures", [])]
    title = (comps.get("title", {}).get("title") or {}).get("text", "")
    street = loc.split(",")[0].strip()
    street = re.sub(r"\s+al\s+", " ", street, flags=re.I)
    return {
        "id": f"ml-{meta.get('id')}",
        "source": "mercadolibre",
        "url": "https://" + meta.get("url", "").replace("\\u002F", "/").split("https://")[-1],
        "title": title,
        "type": "ph" if kind == "ph" else "casa",
        "price_usd": price.get("value") if price.get("currency") == "USD" else None,
        "total_m2": _num(r"(\d+(?:,\d+)?)\s*m² totales", texts),
        "covered_m2": _num(r"(\d+(?:,\d+)?)\s*m² cubiertos", texts),
        "ambientes": _num(r"(\d+)\s*amb", texts),
        "bedrooms": _num(r"(\d+)\s*dorm", texts),
        "bathrooms": _num(r"(\d+)\s*baño", texts),
        "garage": None,
        "age_years": None,
        "address": loc,
        "geocode_query": f"{street}, {zone}, Vicente López, Buenos Aires",
        "zone": zone,
        "address_exact": bool(re.search(r"\d", street)),
        "lat": None,
        "lng": None,
        "description": title,
        "photos": pics,
        "tags": {},
        "credit_pill": "credito" in title.lower() or "crédito" in title.lower(),
        "publisher": None,
        "modified": None,
        "partial_data": True,
    }


def search(max_pages=6, log=print):
    out, failed = {}, []
    for kind in ("casas", "ph"):
        for zone, slug in ZONE_SLUGS.items():
            for page in range(max_pages):
                try:
                    html = fetch(search_url(kind, slug, page * 48)).text
                except RuntimeError as e:
                    log(f"mercadolibre {kind}/{slug} p{page + 1}: {e}")
                    failed.append(f"{kind}/{slug}/{page + 1}")
                    break
                cards = [c for c in _cards(html) if c.get("metadata", {}).get("id")] or list(_html_cards(html))
                for c in cards:
                    item = _normalize(c, kind, zone)
                    out[item["id"]] = item
                log(f"mercadolibre {kind}/{slug} page {page + 1}: {len(cards)} listings")
                if len(cards) < 48:
                    break
    search.failed_pages = failed
    if not out:
        raise RuntimeError("no Mercado Libre page got through")
    return list(out.values())


def _specs(html):
    rows = re.findall(r'header__container">([^<]+)</div></th><td[^>]*><span[^>]*>([^<]+)<', html)
    rows += re.findall(r'<span>([^<:]+):</span></span>\s*<span[^>]*><span>([^<]+)</span>', html)
    return {htmllib.unescape(k).strip(): htmllib.unescape(v).strip() for k, v in rows}


def enrich(l):
    """Item pages open with the same browser profiles: full specs, description, photos and map pin."""
    html = fetch_item(l["url"]).text
    sp = _specs(html)

    def n(*keys):
        for k in keys:
            m = re.search(r"[\d.,]+", sp.get(k, ""))
            if m:
                return float(m.group(0).replace(".", "").replace(",", "."))
        return None

    l["total_m2"] = n("Superficie total") or l.get("total_m2")
    l["covered_m2"] = n("Superficie cubierta") or l.get("covered_m2")
    l["ambientes"] = n("Ambientes") or l.get("ambientes")
    l["bedrooms"] = n("Dormitorios") or l.get("bedrooms")
    l["bathrooms"] = n("Baños") or l.get("bathrooms")
    l["garage"] = n("Cocheras") or 0
    l["age_years"] = n("Antigüedad")
    l["features_text"] = [f"{k}: {v}" for k, v in sp.items()][:40]
    d = re.search(r'ui-pdp-description__content"[^>]*>(.*?)</p>', html, re.S)
    if d:
        l["description"] = htmllib.unescape(re.sub(r"<br\s*/?>", "\n", d.group(1))).strip()
    # gallery pictures: image URLs in every size variant (D_NQ_NP_, D_Q_NP_, 2X_) plus the picture ids in the page state
    ids = list(dict.fromkeys(re.findall(r"D_(?:N?Q_)?NP_(?:2X_)?(\d{5,7}-MLA\d+_\d{6})-", html)
                             + re.findall(r'"id":"(\d{5,7}-MLA\d+_\d{6})"', html)))
    if ids:
        l["photos"] = [f"https://http2.mlstatic.com/D_NQ_NP_{i}-O.jpg" for i in ids[:60]]
    c = re.search(r"center=(-3[45]\.\d+)%2C(-58\.\d+)", html)
    if c:
        l["lat"], l["lng"], l["address_exact"] = float(c.group(1)), float(c.group(2)), True
    l["partial_data"] = not (l.get("total_m2") and l.get("description"))
    l["enriched"] = True
    return l


def fetch_item(url):
    return http.get(url, impersonate=PROFILES, blocked=lambda r: "account-verification" in str(r.url), tries=5)
