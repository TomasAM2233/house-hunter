"""AI read of photos + description. Results are cached per listing so each house is analysed once.

Provider: Google Gemini free tier (set GEMINI_API_KEY). Without a key, listings are queued in
data/ai_pending/ as a photo contact sheet + text, so any vision model (or a human) can fill them in
and save the answer with save_result()."""
import base64, datetime, hashlib, io, json, os, re, time, zoneinfo
import requests
from PIL import Image
from . import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "ai_cache.json")
PENDING = os.path.join(ROOT, "data", "ai_pending")
MAX_PHOTOS = 12
# Gemini's free tier allows ~20 requests a day *per model*, so calls walk down this list as each model's daily
# quota runs out (best first). GEMINI_MODEL is whichever one answered last.
MODELS = os.environ.get("GEMINI_MODELS", "gemini-flash-latest,gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,"
                        "gemini-3-flash-preview,gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",")
GEMINI_MODEL = MODELS[0]

PROMPT_VERSION = 2
PROMPT = f"""Sos un tasador y arquitecto en Vicente López (GBA Norte). Analizá esta publicación de venta
(fotos + texto) para una pareja que quiere mudarse pronto y puede invertir como máximo
USD {config.REFORM_BUDGET_USD:,} en reformas antes de entrar. Un patio o jardín propio a nivel del suelo es
obligatorio para ellos: miralo en las fotos con mucho cuidado. Respondé SOLO un JSON con estas claves:
- "condition": 1-5 (1 = ruina / a demoler, 3 = habitable con arreglos, 5 = impecable / a estrenar)
- "reform_usd": estimación en USD de lo necesario para que quede habitable y digna (no lujos)
- "reform_notes": qué habría que hacer, breve
- "patio": "none" | "small" | "medium" | "large"  (small < 15 m2, medium 15-40, large > 40). Solo patio o
  jardín propio en planta baja; una terraza o balcón NO cuenta como patio
- "patio_m2_est": número o null
- "patio_seen": true solo si en las fotos se ve efectivamente el patio o jardín de la propiedad
- "terrace": true si tiene terraza o azotea propia
- "corner": true si la casa está en una esquina (fotos de fachada en ochava o el texto lo dice)
- "ph_stacked": true si es un PH en planta alta, con otra unidad arriba o abajo (superpuesto); false si es en planta baja con todo el lote propio
- "pasillo_ph": true si es un PH al fondo por pasillo largo o una unidad muy alargada y angosta
- "natural_light": 1-5
- "quiet": 1-5 (según lo que se vea de la calle y el texto; 3 si no se sabe)
- "vertical_potential": 0-1 (posibilidad real de construir hacia arriba: lote propio, losa, una planta, sin consorcio)
- "apto_credito": true | false | null
- "highlights": hasta 3 puntos fuertes cortos
- "red_flags": hasta 3 problemas (humedad, grietas, techo de chapa, instalaciones viejas, etc.)
- "summary": una frase en castellano rioplatense
Sé escéptico con las fotos de inmobiliaria: ángulos abiertos y filtros esconden problemas. Las casas en
esquina casi nunca tienen patio: si no lo ves en las fotos, poné "patio": "none" y "patio_seen": false."""

KEYS = ["condition", "reform_usd", "reform_notes", "patio", "patio_m2_est", "patio_seen", "terrace", "corner", "ph_stacked",
        "pasillo_ph", "natural_light", "quiet", "vertical_potential", "apto_credito", "highlights", "red_flags", "summary"]


def _text(resp):
    """The answer text, skipping the thinking parts newer models return first."""
    parts = resp["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _load():
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def _photos_key(listing):
    return hashlib.sha1("|".join(listing["photos"][:MAX_PHOTOS]).encode()).hexdigest()[:12]


def _note_key(note):
    return hashlib.sha1(note.strip().encode()).hexdigest()[:8] if note and note.strip() else ""


def cached(listing, current=False, note=""):
    """current=True also requires a read made with the current prompt and Tomás's current note."""
    hit = _load().get(listing["id"])
    if not hit or hit.get("photos_key") != _photos_key(listing):
        return None
    if not current:
        return hit
    return hit if hit.get("prompt_version", 1) >= PROMPT_VERSION and hit.get("note_key", "") == _note_key(note) else None


def save_result(listing_id, result, photos_key, analyst, note=""):
    cache = _load()
    result = {k: result.get(k) for k in KEYS}
    result.update(photos_key=photos_key, analyst=analyst, analysed_at=time.strftime("%Y-%m-%d"), prompt_version=PROMPT_VERSION,
                  note_key=_note_key(note), ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    cache[listing_id] = result
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=1)
    return result


def _download(urls, max_seconds=120):
    imgs, start = [], time.time()
    for u in urls[:MAX_PHOTOS]:
        if time.time() - start > max_seconds and imgs:
            break  # a slow unblocking API shouldn't hold the run: read with the photos we have
        try:
            if "argenprop.com/" in u:  # its WAF blocks cloud IPs for photos too
                from . import http
                r = http.get(u, via_api=True, binary=True, timeout=45, api_tries=1)
            else:
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


NOTE_PROMPT = """NOTAS DE TOMÁS SOBRE ESTA CASA: lo que él averiguó (visita, llamado a la inmobiliaria, fotos propias).
Es información verificada y tiene prioridad sobre el aviso y las fotos: si algo choca, creele a él."""


def _gemini(listing, note=""):
    parts = [{"text": PROMPT + "\n\n" + _listing_text(listing) + (f"\n\n{NOTE_PROMPT}\n{note.strip()}" if note.strip() else "")}]
    for im in _download(listing["photos"]):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=75)
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})
    return _call({"contents": [{"parts": parts}], "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}}, 90)


EXHAUSTED = None  # set to the error once the free quota runs out, so the rest of the run doesn't wait on it
DOWN = None       # set when Gemini keeps timing out: the automatic run stops asking and moves on (next run retries)
FAILS = 0         # consecutive calls that got no answer at all (timeouts, connection errors, 5xx)
MAX_FAILS = 3


def _call(body, timeout):
    global EXHAUSTED, GEMINI_MODEL, FAILS, DOWN
    while True:
        if EXHAUSTED:
            raise RuntimeError(EXHAUSTED)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={os.environ['GEMINI_API_KEY']}"
        for attempt in range(3):
            try:
                r = requests.post(url, json=body, timeout=timeout)
            except requests.RequestException:
                FAILS += 1
                if FAILS >= MAX_FAILS:
                    DOWN = f"Gemini didn't answer {FAILS} times in a row"
                raise
            FAILS = 0 if r.status_code < 500 else FAILS + 1
            if r.status_code == 429 and "PerDay" in r.text:
                break  # this model is done for today; try the next one
            if r.status_code == 429:
                wait = re.search(r'"retryDelay":\s*"(\d+)', r.text)
                time.sleep(min(65, int(wait.group(1)) + 1 if wait else 20))
                continue
            if r.status_code == 404 or r.status_code >= 500:
                time.sleep(5 if r.status_code >= 500 else 0)
                if r.status_code == 404:
                    break
                continue
            r.raise_for_status()
            out = json.loads(_text(r.json()))
            return out[0] if isinstance(out, list) and out else out
        i = MODELS.index(GEMINI_MODEL)
        if i + 1 >= len(MODELS):
            EXHAUSTED = "Gemini free quota used up for today on every model"
        else:
            GEMINI_MODEL = MODELS[i + 1]


FINAL = os.path.join(ROOT, "data", "ai_final.json")
FINAL_PROMPT = f"""Sos el asesor inmobiliario de Tomás. Abajo están sus preferencias escritas por él, sus notas sobre
esta casa (si las hay), los datos del aviso, la lectura de las fotos y el puntaje que calculó nuestro algoritmo
con su desglose. Tu evaluación final reemplaza a ese puntaje, así que tené en cuenta todo: sus criterios en orden
de importancia, lo subjetivo de sus preferencias y sus notas, y lo que el algoritmo no ve. Sus notas son datos que
él verificó (visitas, llamados a la inmobiliaria) y mandan sobre el aviso, las fotos y el algoritmo: si una nota
corrige algo (patio, estado, precio, expensas, m², ubicación), puntuá con lo que dice la nota y mencionalo en los
motivos. Si algo choca con un
requisito obligatorio suyo, bajá mucho el puntaje.
Además, Tomás quiere comprar una casa donde quiera vivir que también sea una buena inversión. Ponderá cuánto
valor va a sostener al revenderla: que el precio esté abajo del mercado (USD/m² de lote y cubierto contra la zona); el terreno, que no
se deprecia (lote grande y barato por m², buen frente, m² que todavía se pueden construir según el FOT de su zona
oficial: R1 0,8 veces el lote, R2 1,0, R3 1,1; una zona más densa también vale más como terreno); no pagar el sobreprecio
de una casa nueva o recién reciclada, que se pierde en pocos años; que una reforma razonable sume m², baños o
cocina en planos aprobados; la ubicación (de 4 a 8 cuadras de Maipú o del tren, cerca de una plaza, calle
tranquila); y que se pueda vender fácil: apta crédito, planos y papeles en regla, y nada que achique la lista de
compradores (pasillo, planta rara, construcciones sin declarar). Esto pesa menos que sus criterios de vida, pero
mueve el puntaje. Usá la misma escala que el algoritmo: entre las candidatas
que pasan los filtros, 45 es floja, 55 buena, 65 muy buena y 75 o más solo para una oportunidad excepcional que
Tomás tendría que ir a ver hoy. Partí del puntaje calculado y movete solo con motivos concretos (cada motivo
vale entre 3 y 15 puntos). Sé exigente: la mayoría de los avisos no son excepcionales. Respondé SOLO un JSON:
{{"score": 0-100 (entero), "brief": "resumen de {config.BRIEF_MAX_CHARS} caracteres como máximo, en castellano
rioplatense, con lo que más le importa a Tomás a favor y en contra, con números concretos, sin adjetivos de
inmobiliaria ni la dirección", "reasons": ["hasta 3 motivos cortos de por qué tu puntaje difiere del calculado"],
"investment": {{"score": 1-10 (qué tan buena inversión es: valor que sostiene al revender), "why": "una oración
con los números que lo explican"}},
"questions": [hasta 6 preguntas para que Tomás haga en la visita o al llamar a la inmobiliaria, cuya respuesta
cambiaría tu puntaje: lo que hoy no se sabe o asumiste (patio real, humedad, estado del techo y las instalaciones,
m² y planos aprobados, expensas, si es apto crédito, ruido, orientación, qué hay al fondo o al lado, etc.), las más
importantes primero, cada una {{"q": "la pregunta, corta y concreta", "impact": "cómo movería el puntaje según la
respuesta, con puntos (ej.: si hay humedad de cimientos -10; si está seca +3)"}}],
"general_questions": [hasta 6 preguntas que igual conviene hacer aunque no cambien el puntaje (papeles, deudas,
plazos de escritura y entrega, qué queda con la casa, por qué venden, si aceptan oferta, gastos de mantenimiento,
vecinos, etc.), específicas para esta casa]}}
Sus notas pueden tener preguntas de visitas anteriores con su respuesta ("pregunta → respuesta"): esas respuestas
son datos verificados, usalas para afinar el puntaje y no las vuelvas a preguntar; una pregunta sin respuesta sigue
pendiente."""


def calls_today():
    """Gemini calls made since the free quota last reset (midnight Pacific), counted from the two caches' timestamps."""
    pacific = zoneinfo.ZoneInfo("America/Los_Angeles")
    today = datetime.datetime.now(pacific).date()
    n = 0
    for path in (CACHE, FINAL):
        for v in (json.load(open(path)) if os.path.exists(path) else {}).values():
            try:
                n += datetime.datetime.fromisoformat(v["ts"].replace("Z", "+00:00")).astimezone(pacific).date() == today
            except (KeyError, TypeError, ValueError):
                pass
    return n


def budget_left():
    """Calls the automatic runs may still make today, keeping the reserve for the app's on-demand assessments."""
    return config.AI_DAILY_CALLS - config.AI_MANUAL_RESERVE - calls_today()


def _final_text(l, prefs, note):
    a, g = l.get("ai") or {}, l.get("geo") or {}
    st = g.get("station") or {}
    ppm2 = round(l["price_usd"] / l["total_m2"]) if l.get("price_usd") and l.get("total_m2") else None
    # only numbers that stay put between runs: the verdict is cached by its input, and the side percentiles
    # move a little with every new listing
    z = g.get("zoning") or {}
    zone = (f"zona {z['code']} ({z['name']}; FOS {z['fos']}, FOT {z['fot']}" if z.get("fot") else
            f"zona {z['code']} ({z['name']}" if z else f"zona desconocida (FOT {config.FOT_ASSUMED} supuesto")
    zone += f"; en el límite con {z['edge']}, confirmar)" if z.get("edge") else ")"
    inv = (f"{zone}, ~{l.get('build_m2')} m² por construir, "
           f"percentil del puntaje {l.get('pct')} | {(l.get('components') or {}).get('investment', {}).get('why', '')}")
    comps = "; ".join(f"{k}: {c['points']:.1f}/{c['max']} ({c['why']})" for k, c in (l.get("components") or {}).items())
    return (f"PREFERENCIAS DE TOMÁS:\n{prefs}\n\nNOTAS DE TOMÁS SOBRE ESTA CASA: {note or '(ninguna)'}\n\n"
            f"AVISO ({l.get('source')}):\n" + _listing_text(l) + f"\nUSD/m² total: {ppm2} | Cochera: {l.get('garage')} | "
            f"Cuadras a Maipú: {g.get('maipu_blocks')} | Tren: {st.get('name')} ({st.get('line')}) a {st.get('blocks')} cuadras | "
            f"Cuadras a Puente Saavedra: {g.get('puente_blocks')}\n"
            f"INVERSIÓN: {inv}\n"
            f"LECTURA DE FOTOS: {json.dumps({k: a.get(k) for k in KEYS if k != 'summary'}, ensure_ascii=False)}\n"
            f"PUNTAJE CALCULADO: {l.get('score')}/100 — {comps}\nAlertas: {', '.join(l.get('flags') or []) or 'ninguna'}")


def _investment(x):
    """{score 1-10, why} or None, from whatever the model answered."""
    try:
        return {"score": max(1, min(10, int(round(float(x["score"]))))), "why": str(x.get("why") or "").strip()[:300]}
    except (TypeError, KeyError, ValueError):
        return None


def _questions(qs):
    """[{q, impact}] for the visit, from whatever shape the model answered with (plain strings get no impact)."""
    out = []
    for x in (qs if isinstance(qs, list) else [])[:6]:
        q, impact = (x.get("q") or x.get("question"), x.get("impact")) if isinstance(x, dict) else (x, None)
        if str(q or "").strip():
            out.append({"q": str(q).strip(), "impact": str(impact).strip() if impact else ""})
    return out


def final(listing, prefs, note="", compute=True, force=False, log=print):
    """The overall AI verdict: score 0-100 that overrides ours, a <=250 char brief and the reasons.
    Cached per listing and keyed by everything it reads, so it reruns only when something changed (or force=True,
    when Tomás asks for it from the app)."""
    text = _final_text(listing, prefs, note)
    h = hashlib.sha1((FINAL_PROMPT + text).encode()).hexdigest()[:12]
    cache = json.load(open(FINAL)) if os.path.exists(FINAL) else {}
    hit = cache.get(listing["id"])
    if hit and hit.get("input_key") == h and not force:
        return hit
    key = os.environ.get("GEMINI_API_KEY")
    if not compute or not key or (DOWN and not force):
        return hit  # stale verdict is better than none until the next run with a key
    try:
        res = _call({"contents": [{"parts": [{"text": FINAL_PROMPT + "\n\n" + text}]}],
                     "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}}, 90)
        brief = str(res.get("brief") or "").strip()
        if len(brief) > config.BRIEF_MAX_CHARS:
            brief = brief[:config.BRIEF_MAX_CHARS - 1].rsplit(" ", 1)[0] + "…"
        out = {"score": max(0, min(100, int(round(float(res["score"]))))), "brief": brief,
               "reasons": [str(x) for x in (res.get("reasons") or [])][:3],
               "investment": _investment(res.get("investment")),
               "questions": _questions(res.get("questions")), "general_questions": _questions(res.get("general_questions")),
               "input_key": h,
               "model": GEMINI_MODEL, "at": time.strftime("%Y-%m-%d"), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    except Exception as e:
        log(f"final verdict failed for {listing['id']}: {e}")
        if force:
            raise
        return hit
    cache = json.load(open(FINAL)) if os.path.exists(FINAL) else {}
    cache[listing["id"]] = out
    json.dump(cache, open(FINAL, "w"), ensure_ascii=False, indent=1)
    time.sleep(4)
    return out


def analyse(listing, note="", force=False, log=print):
    """Photo + text read. Tomás's note goes in the prompt, and a changed note means a fresh read.
    force=True (asked for from the app) always reads again and raises on failure."""
    hit = None if force else cached(listing, current=True, note=note)
    if hit:
        return hit
    if os.environ.get("GEMINI_API_KEY"):
        if (EXHAUSTED or DOWN) and not force:
            return None  # quota's gone (or Gemini isn't answering) for this run; don't spend photo downloads on it
        try:
            t = time.time()
            res = _gemini(listing, note)
            log(f"AI read {listing['id']}: ok in {time.time() - t:.0f}s ({GEMINI_MODEL})")
            time.sleep(6)  # stay under the free tier's requests-per-minute
            return save_result(listing["id"], res, _photos_key(listing), f"gemini:{GEMINI_MODEL}", note)
        except Exception as e:
            log(f"AI failed for {listing['id']}: {e}")
            if DOWN and not force:
                log(f"{DOWN}: no more AI reads this run")
            if force:
                raise
        return None
    if force:
        raise RuntimeError("no GEMINI_API_KEY")
    queue(listing)  # no key: leave a contact sheet for a human or another model
    return None
