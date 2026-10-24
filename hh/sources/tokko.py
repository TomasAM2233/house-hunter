"""Local agencies that run on Tokko Broker, the CRM most zona norte inmobiliarias use.

Two flavours, both listed in config.AGENCIES:
- "key": sites built on MediaCore/Gatsby ship the agency's public Tokko web key in the page, so we
  query the Tokko JSON API with it (exact coordinates, m², apto crédito, every photo).
- "site": Tokko's own website template ("tfw"). We run the site's search and parse each /p/ page.
The Tokko property id is shared across both, so the same property seen twice keeps one id.
"""
import html as htmllib, json, re
from .. import http, config

API = "https://www.tokkobroker.com/api/v1/property/search/"
VICENTE_LOPEZ = 25818
LOCATIONS = {"Olivos": 25836, "Florida": 25820, "La Lucila": 25829}
PTYPES = {3: "casa", 13: "ph"}


def _zone(name):
    for z in LOCATIONS:
        if z.lower() in (name or "").lower():
            return z
    return None


def _f(x):
    try:
        v = float(str(x).replace(",", "."))
        return v or None
    except (TypeError, ValueError):
        return None


# ---------- API flavour ----------

def _from_api(o, agency):
    price = None
    for op in o.get("operations") or []:
        if op.get("operation_type") == "Venta":
            for p in op.get("prices") or []:
                if p.get("currency") == "USD":
                    price = p.get("price")
    loc = o.get("location") or {}
    total = max(_f(o.get("total_surface")) or 0, _f(o.get("surface")) or 0) or None
    lat, lng = _f(o.get("geo_lat")), _f(o.get("geo_long"))
    return {
        "id": f"tk-{o['id']}",
        "source": "tokko",
        "url": o.get("public_url"),
        "title": o.get("publication_title"),
        "type": "ph" if (o.get("type") or {}).get("name") == "PH" else "casa",
        "price_usd": price,
        "total_m2": total,
        "covered_m2": _f(o.get("roofed_surface")),
        "uncovered_m2": _f(o.get("unroofed_surface")),
        "ambientes": o.get("room_amount") or None,
        "bedrooms": o.get("suite_amount") or None,
        "bathrooms": o.get("bathroom_amount") or None,
        "garage": o.get("parking_lot_amount") or 0,
        "age_years": o.get("age") if (o.get("age") or 0) > 0 else None,
        "address": f"{(o.get('fake_address') or o.get('address') or '').strip()}, {loc.get('name', '')}",
        "zone": _zone(loc.get("full_location") or loc.get("name")),
        "address_exact": lat is not None,
        "lat": lat,
        "lng": lng,
        "description": htmllib.unescape(o.get("description") or ""),
        "photos": [p.get("image") for p in o.get("photos") or [] if p.get("image")],
        "tags": {t.get("name"): True for t in o.get("tags") or []},
        "features_text": [o.get("property_condition") or "", o.get("disposition") or "", o.get("orientation") or ""],
        "credit_pill": o.get("credit_eligible") == "Apto crédito",
        "apto_credito_field": {"Apto crédito": True, "No apto crédito": False}.get(o.get("credit_eligible")),
        "publisher": agency["name"],
        "modified": o.get("created_at"),
        "enriched": True,
    }


def search_api(agency, log=print):
    s = config.SEARCH
    data = {"current_localization_id": VICENTE_LOPEZ, "current_localization_type": "division",
            "price_from": s["price_min"], "price_to": s["price_ceiling"], "currency": "USD",
            "operation_types": [1], "property_types": list(PTYPES), "filters": []}
    out, offset = [], 0
    while True:
        r = http.get(API + "?" + http.urlencode({"key": agency["key"], "format": "json", "lang": "es_ar", "limit": 50,
                                                 "offset": offset, "data": json.dumps(data)}))
        d = r.json()
        for o in d.get("objects", []):
            if _zone((o.get("location") or {}).get("full_location")):
                out.append(_from_api(o, agency))
        offset += 50
        if not d.get("meta", {}).get("next"):
            return out


# ---------- tfw website flavour ----------

def _text(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    for _ in range(2):  # descriptions come HTML-escaped inside the HTML
        t = re.sub(r"<br\s*/?>|</p>|</div>", "\n", t)
        t = re.sub(r"<[^>]+>", " ", t)
        t = htmllib.unescape(t)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


def _after(label, txt, pat=r"([\d.,]+)"):
    m = re.search(label + r"\s*:?\s*\n?\s*" + pat, txt, re.I)
    return m.group(1) if m else None


def _num(s):
    """'1.234' is thousands, '222.05' or '222,05' is decimals."""
    if not s:
        return None
    s = s.strip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return _f(s)


def _from_page(pid, slug, html, agency):
    txt = _text(html)
    price = None
    m = re.search(r"USD\s*([\d.]+)", txt)
    if m:
        price = _f(m.group(1).replace(".", ""))
    covered = _num(_after(r"Superficie cubierta", txt) or _after(r"Cubierta", txt))
    uncovered = _num(_after(r"Descubierta", txt))
    built = _num(_after(r"Total construido", txt))
    land = _num(_after(r"Superficie del terreno", txt) or _after(r"Terreno", txt))
    total = max(x for x in (built, land, (covered or 0) + (uncovered or 0), 0) if x is not None) or None
    ll = re.search(r"(-3[45]\.\d{4,})\s*,\s*(-58\.\d{4,})", html)
    desc = txt.split("DESCRIPCIÓN", 1)[1] if "DESCRIPCIÓN" in txt else ""
    desc = re.split(r"\nMás propiedades|\nPropiedades similares|\nContacto\n", desc)[0].strip()
    credit = _after(r"Crédito", txt, r"([^\n]+)") or ""
    photos = list(dict.fromkeys(re.findall(r"https://static\.tokkobroker\.com/(?:w_pics|w_pictures|pictures|pics)/[^\"' )]+?\.(?:jpe?g|png)", html)))
    address = (re.search(r"Dirección\s*\n\s*([^\n]+)", txt) or [None, ""])[1].strip()
    where = (re.search(r"Ubicación\s*\n\s*([^\n]+)", txt) or [None, ""])[1].strip()
    cond = _after(r"Condición", txt, r"([^\n]+)") or ""
    return {
        "id": f"tk-{pid}",
        "source": "tokko",
        "url": f"{agency['site']}/p/{pid}-{slug}",
        "title": slug.replace("-", " "),
        "type": "ph" if slug.lower().startswith("ph-") else "casa",
        "price_usd": price,
        "total_m2": total,
        "covered_m2": covered,
        "uncovered_m2": uncovered,
        "ambientes": _num(_after(r"Ambientes", txt)),
        "bedrooms": _num(_after(r"Dormitorios", txt)),
        "bathrooms": _num(_after(r"Baños", txt)),
        "garage": _num(_after(r"Cocheras?", txt)) or 0,
        "age_years": _num(_after(r"Antigüedad", txt)),
        "address": f"{address}, {where}",
        "zone": _zone(where) or _zone(slug),
        "address_exact": ll is not None,
        "geocode_query": None if ll else f"{re.sub(r' al ', ' ', address, flags=re.I)}, {_zone(where) or where}, Vicente López, Buenos Aires",
        "lat": float(ll.group(1)) if ll else None,
        "lng": float(ll.group(2)) if ll else None,
        "description": desc,
        "photos": photos[:30],
        "tags": {},
        "features_text": [cond],
        "credit_pill": "apto" in credit.lower() and "no" not in credit.lower(),
        "publisher": agency["name"],
        "modified": None,
        "enriched": True,
    }


def search_site(agency, log=print, max_pages=10):
    s = config.SEARCH
    base = (f"{agency['site']}/Buscar?operation=1&ptypes={','.join(map(str, PTYPES))}"
            f"&locations={','.join(map(str, LOCATIONS.values()))}"
            f"&min-price={s['price_min']}&max-price={s['price_ceiling']}&currency=USD&o=2,2")
    found = {}
    for page in range(1, max_pages + 1):
        body = http.get(base + (f"&p={page}" if page > 1 else "")).text
        new = dict(re.findall(r'href="/p/(\d+)-([^"]+)"', body))
        if not new or (page > 1 and "--NoMoreProperties--" in body):
            break
        found.update(new)
    out = []
    for pid, slug in found.items():
        try:
            l = _from_page(pid, slug, http.get(f"{agency['site']}/p/{pid}-{slug}").text, agency)
            if l["zone"]:
                out.append(l)
        except Exception as e:
            log(f"tokko {agency['name']} {pid}: {e}")
    return out


def search(log=print):
    seen, failed = {}, []
    for agency in config.AGENCIES:
        try:
            got = search_api(agency, log) if agency.get("key") else search_site(agency, log)
            log(f"tokko {agency['name']}: {len(got)}")
            for l in got:
                seen.setdefault(l["id"], l)
        except Exception as e:
            log(f"tokko {agency['name']} failed: {e}")
            failed.append(agency["name"])
    search.failed_pages = failed
    if failed and not seen:
        raise RuntimeError("every agency failed")
    return list(seen.values())
