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
