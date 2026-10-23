"""Mercado Libre Inmuebles: search pages embed 'polycard' JSON. Detail pages sit behind a login wall,
so we only get what the card shows (price, ambientes, covered m2, address, one photo)."""
import json, re
from .. import http, config

BASE = "https://inmuebles.mercadolibre.com.ar"
ZONE_SLUGS = {"Olivos": "olivos", "Florida": "florida", "La Lucila": "la-lucila"}
_dec = json.JSONDecoder()


def search_url(kind, zone_slug, offset):
    s = config.SEARCH
    page = "" if offset == 0 else f"_Desde_{offset + 1}"
    return f"{BASE}/{kind}/venta/bsas-gba-norte/vicente-lopez/{zone_slug}/{page}_PriceRange_{s['price_min']}USD-{s['price_max']}USD_NoIndex_True"


def _cards(html):
    for m in re.finditer(r'"polycard":\{', html):
        try:
            yield _dec.raw_decode(html[m.end() - 1:])[0]
        except ValueError:
            continue


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
        "url": "https://" + meta.get("url", "").replace("\\u002F", "/"),
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
    out = {}
    for kind in ("casas", "ph"):
        for zone, slug in ZONE_SLUGS.items():
            for page in range(max_pages):
                try:
                    html = http.get(search_url(kind, slug, page * 48)).text
                except RuntimeError as e:
                    log(f"mercadolibre {kind}/{slug} p{page + 1}: {e}")
                    break
                cards = [c for c in _cards(html) if c.get("metadata", {}).get("id")]
                for c in cards:
                    item = _normalize(c, kind, zone)
                    out[item["id"]] = item
                log(f"mercadolibre {kind}/{slug} page {page + 1}: {len(cards)} listings")
                if len(cards) < 48:
                    break
    return list(out.values())
