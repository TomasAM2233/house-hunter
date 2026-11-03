"""Cheap signals pulled out of listing text with regexes, before (and alongside) the AI."""
import re, unicodedata


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _num(s):
    return float(s.replace(",", "."))


def lot_dims(text):
    """'lote de 8,66 x 18,06' -> (8.66, 18.06), front first."""
    t = norm(text)
    m = re.search(r"(?:lote|terreno|frente)[^.\n]{0,40}?(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:m(?:ts|etros)?\.?)?\s*[x×]\s*(\d{1,3}(?:[.,]\d{1,2})?)", t)
    if not m:
        return None
    a, b = _num(m.group(1)), _num(m.group(2))
    if not (4 <= a <= 60 and 8 <= b <= 120):
        return None
    return (a, b)


def lot_m2(text):
    """Lot surface from the text: 'terreno de 350 m2', 'lote: 8,66 x 30' -> m2."""
    t = norm(text)
    m = re.search(r"(?:lote|terreno)\s*(?:propio\s*)?(?:de|:)?\s*(?:aprox\.?\s*)?(\d\.\d{3}|\d{3,4}(?:[.,]\d{1,2})?)\s*(?:m2|m²|mts2|mts\.? ?cuadrados|metros cuadrados)", t)
    if m:
        v = _num(m.group(1).replace(".", "") if re.fullmatch(r"\d\.\d{3}", m.group(1)) else m.group(1))
        if 80 <= v <= 3_000:
            return round(v)
    d = lot_dims(text)
    return round(d[0] * d[1]) if d else None


def usd_price(text):
    """Asking price written in the description ('antes U$D 187.000 ahora U$D 178.000' -> 178000): the last one wins."""
    found = [int(m.replace(".", "")) for m in re.findall(r"(?:u\$[sd]|usd|us\$)\s*(\d{2,3}\.\d{3})\b", norm(text))]
    found = [v for v in found if 30_000 <= v <= 900_000]
    return found[-1] if found else None


def uncovered_m2(text):
    m = re.search(r"(\d{2,4})\s*m(?:2|²|ts2| ?cuadrados)?\s*(?:de\s+)?(?:descubiert|libres|de (?:patio|jardin|parque))", norm(text))
    return int(m.group(1)) if m else None


def apto_credito(text):
    t = norm(text)
    if re.search(r"no\s+(?:es\s+)?apt[oa]\s+(?:para\s+)?credito", t):
        return False
    if re.search(r"apt[oa]\s+(?:a\s+|para\s+)?credito|acepta\s+credito|credito\s+hipotecario", t):
        return True
    return None


def has_patio_words(text):
    return bool(re.search(r"\b(patio|jardin|parque|fondo libre|pileta|quincho|terraza)", norm(text)))


def pasillo_words(text):
    t = norm(text)
    return bool(re.search(r"(por pasillo|pasillo (?:de )?(?:ingreso|entrada|comun|largo)|al fondo por pasillo|unidad al fondo|ph al fondo|interno por pasillo)", t))


def single_storey(text):
    t = norm(text)
    return bool(re.search(r"(una sola planta|en una planta|todo en planta baja|desarrollad[oa] en 1 planta|una planta)", t))


def own_lot(text):
    return bool(re.search(r"(lote propio|terreno propio|sobre lote)", norm(text)))


def corner(text):
    return bool(re.search(r"\b(en esquina|esquina|lote esquina|ochava)\b", norm(text)))


def ph_stacked(text):
    """A PH upstairs (or with another unit on top): the kind Tomás rules out."""
    t = norm(text)
    return bool(re.search(r"((ph|unidad)[^.]{0,40}(en planta alta|en (el )?primer piso|en (el )?1 ?(er|°|º)? piso|en altura|superpuest)"
                          r"|(se accede|acceso|ingreso)[^.]{0,20}por escalera|ph de altos|ph en pa\b)", t))


# ── apartments ──
def balcony(text):
    """True when the text says it has a balcony (or a terrace of its own), False when it says it has none, else None."""
    t = norm(text)
    if re.search(r"\bsin\s+balcon", t):
        return False
    if re.search(r"\b(balcon|balcones|terraza propia|terraza privada|terraza exclusiva|balcon terraza)", t):
        return True
    return None


def french_balcony(text):
    return bool(re.search(r"balcon(cito)? frances|balcones franceses", norm(text)))


def garage(text):
    """'fixed' (cochera / cochera fija / cubierta), 'optional' (se vende aparte / opcional), False (sin cochera) or None."""
    t = norm(text)
    if re.search(r"\bsin\s+(cochera|garage|garaje)|no\s+(tiene|posee|incluye)\s+(cochera|garage)", t):
        return False
    if re.search(r"(cochera|garage|garaje)s?\s+(opcional|aparte|a la venta|en venta|se vende|con valor adicional|adicional|a convenir)"
                 r"|(opcion|posibilidad) de (comprar |adquirir )?(cochera|garage)|(cochera|garage) por separado", t):
        return "optional"
    if re.search(r"\b(cochera|cocheras|garage|garaje)\b", t):
        return "fixed"
    return None


def floor_number(text):
    """Floor from the text ('piso 8', '8° piso', 'octavo piso'), or None. Planta baja = 0."""
    t = norm(text)
    if re.search(r"\b(planta baja|en pb)\b", t) and not re.search(r"\bpiso\s+\d", t):
        return 0
    m = re.search(r"\b(?:piso|p\.)\s*(\d{1,2})\b|\b(\d{1,2})\s*(?:°|º|o|er|do|to|vo|no|mo)?\s*piso\b", t)
    if m:
        v = int(m.group(1) or m.group(2))
        return v if v <= 40 else None
    words = {"primer": 1, "segundo": 2, "tercer": 3, "cuarto": 4, "quinto": 5, "sexto": 6, "septimo": 7, "octavo": 8,
             "noveno": 9, "decimo": 10}
    m = re.search(r"\b(" + "|".join(words) + r")\s+piso\b", t)
    return words[m.group(1)] if m else None


def view_words(text):
    """+1 for words that promise a view, -1 for ones that rule it out, 0 when it doesn't say."""
    t = norm(text)
    if re.search(r"\bcontrafrente\b[^.]{0,30}(pulmon|pared|medianera)|vista a (pared|medianera)|(departamento|depto|unidad) intern[oa]\b", t):
        return -1
    if re.search(r"vista (abierta|panoramica|despejada|al (rio|parque|verde|bosque|jardin)|a la ciudad|increible|unica)"
                 r"|\bpanoramic|piso alto|frente al (parque|bosque|jardin)|sin edificios enfrente|vista al rio", t):
        return 1
    return 0
