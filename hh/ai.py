"""AI read of photos + description. Results are cached per listing so each house is analysed once.

Provider: Google Gemini free tier (set GEMINI_API_KEY). Without a key, listings are queued in
data/ai_pending/ as a photo contact sheet + text, so any vision model (or a human) can fill them in
and save the answer with save_result()."""
import base64, hashlib, io, json, os, time
import requests
from PIL import Image
from . import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "ai_cache.json")
PENDING = os.path.join(ROOT, "data", "ai_pending")
MAX_PHOTOS = 12
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

PROMPT = f"""Sos un tasador y arquitecto en Vicente López (GBA Norte). Analizá esta publicación de venta
(fotos + texto) para una pareja que quiere mudarse pronto y puede invertir como máximo
USD {config.REFORM_BUDGET_USD:,} en reformas antes de entrar. Respondé SOLO un JSON con estas claves:
- "condition": 1-5 (1 = ruina / a demoler, 3 = habitable con arreglos, 5 = impecable / a estrenar)
- "reform_usd": estimación en USD de lo necesario para que quede habitable y digna (no lujos)
- "reform_notes": qué habría que hacer, breve
- "patio": "none" | "small" | "medium" | "large"  (small < 15 m2, medium 15-40, large > 40)
- "patio_m2_est": número o null
- "pasillo_ph": true si es un PH al fondo por pasillo largo o una unidad muy alargada y angosta
- "natural_light": 1-5
- "quiet": 1-5 (según lo que se vea de la calle y el texto; 3 si no se sabe)
- "vertical_potential": 0-1 (posibilidad real de construir hacia arriba: lote propio, losa, una planta, sin consorcio)
- "apto_credito": true | false | null
- "highlights": hasta 3 puntos fuertes cortos
- "red_flags": hasta 3 problemas (humedad, grietas, techo de chapa, instalaciones viejas, etc.)
- "summary": una frase en castellano rioplatense
Sé escéptico con las fotos de inmobiliaria: ángulos abiertos y filtros esconden problemas."""

KEYS = ["condition", "reform_usd", "reform_notes", "patio", "patio_m2_est", "pasillo_ph", "natural_light",
        "quiet", "vertical_potential", "apto_credito", "highlights", "red_flags", "summary"]


def _load():
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def _photos_key(listing):
    return hashlib.sha1("|".join(listing["photos"][:MAX_PHOTOS]).encode()).hexdigest()[:12]


def cached(listing):
    hit = _load().get(listing["id"])
    return hit if hit and hit.get("photos_key") == _photos_key(listing) else None


def save_result(listing_id, result, photos_key, analyst):
    cache = _load()
    result = {k: result.get(k) for k in KEYS}
    result.update(photos_key=photos_key, analyst=analyst, analysed_at=time.strftime("%Y-%m-%d"))
    cache[listing_id] = result
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=1)
    return result


def _download(urls):
    imgs = []
    for u in urls[:MAX_PHOTOS]:
        try:
            r = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            im.thumbnail((768, 768))
            imgs.append(im)
        except Exception:
            continue
    return imgs


def _listing_text(l):
    return (f"Tipo: {l['type']} | Precio: USD {l['price_usd']} | Sup. total: {l['total_m2']} m2 | "
            f"Cubierta: {l['covered_m2']} m2 | Ambientes: {l['ambientes']} | Antigüedad: {l.get('age_years')} | "
            f"Dirección: {l['address']}\nTítulo: {l['title']}\nDescripción: {l['description'][:3500]}\n"
            f"Características: {', '.join(l.get('features_text') or [])}")


def contact_sheet(imgs, cols=4, cell=(400, 300)):
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell[0], max(1, rows) * cell[1]), "white")
    for i, im in enumerate(imgs):
        im = im.copy()
        im.thumbnail(cell)
        sheet.paste(im, ((i % cols) * cell[0], (i // cols) * cell[1]))
    return sheet


def queue(listing):
    os.makedirs(PENDING, exist_ok=True)
    base = os.path.join(PENDING, listing["id"])
    if not os.path.exists(base + ".jpg"):
        contact_sheet(_download(listing["photos"])).save(base + ".jpg", quality=80)
    with open(base + ".json", "w") as f:
        json.dump({"id": listing["id"], "photos_key": _photos_key(listing), "text": _listing_text(listing)}, f, ensure_ascii=False, indent=1)


def _gemini(listing):
    key = os.environ["GEMINI_API_KEY"]
    parts = [{"text": PROMPT + "\n\n" + _listing_text(listing)}]
    for im in _download(listing["photos"]):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=75)
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})
    body = {"contents": [{"parts": parts}], "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    for attempt in range(4):
        r = requests.post(url, json=body, timeout=120)
        if r.status_code == 429:
            time.sleep(30 * (attempt + 1))
            continue
        r.raise_for_status()
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    raise RuntimeError("Gemini rate limit")


def analyse(listing, log=print):
    hit = cached(listing)
    if hit:
        return hit
    if os.environ.get("GEMINI_API_KEY"):
        try:
            res = _gemini(listing)
            time.sleep(6)  # stay under the free tier's requests-per-minute
            return save_result(listing["id"], res, _photos_key(listing), f"gemini:{GEMINI_MODEL}")
        except Exception as e:
            log(f"AI failed for {listing['id']}: {e}")
    queue(listing)
    return None
