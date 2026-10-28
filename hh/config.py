"""Search criteria and scoring weights. Edit this file to change what the hunter looks for."""

SEARCH = {
    "price_min": 80_000,       # USD; only bounds what the portals return, never discards (a cheap house is a find)
    "price_max": 210_000,      # USD; the budget
    "price_ceiling": 240_000,  # USD; asking prices up to here are fetched and scored with a penalty (room to negotiate)
    "ppm2_max": 2_000,         # USD per total m2; no floor, for the same reason
    "min_ambientes": 3,
    "min_total_m2": 100,
    "types": ["casa", "ph"],
    # "Vicente López" is the barrio by the river (east of the Mitre/Maipú, down to Gral. Paz), not the whole partido:
    # each source names it its own way (see the sources) so Munro, Carapachay, Florida Oeste etc. stay out.
    "zones": ["Olivos", "Florida", "La Lucila", "Vicente López"],
}

# Geography, in "cuadras". One cuadra is taken as 100 m of straight-line distance.
BLOCK_M = 100
MAIPU_MIN_BLOCKS = 3        # closer than this to Av. Maipú is too noisy
MAIPU_MAX_BLOCKS = 15       # farther than this is out of the zone
MAIPU_SWEET_BLOCKS = 6      # the location score peaks here and falls off on both sides
PUENTE_SAAVEDRA = (-34.5383, -58.4762)
PUENTE_MIN_BLOCKS = 5
# Villa Borges (La Loma de Olivos, around Rosetti y Borges): anything within 4 cuadras of it is discarded.
# Measured from its edge, taken as a circle of VILLA_BORGES_RADIUS_M around this centre. Check it on the app's map.
VILLA_BORGES = (-34.5174, -58.5142)
VILLA_BORGES_RADIUS_M = 100
VILLA_BORGES_MIN_BLOCKS = 4
# Plazas and parks (OSM, geo/parks.json via osm_parks.py): part of the location score, by walking distance to the edge.
PARK_MIN_M2 = 1_500          # smaller green spots (a boulevard, a corner) don't count
PARK_SHARE = 0.25            # share of the location score that comes from the nearest plaza/park

# Lines that actually get you to Palermo / Belgrano / Recoleta / Centro.
# Tren de la Costa stations count, but with a penalty since you need a transfer.
STATION_LINE_PENALTY_BLOCKS = {"Mitre": 0, "Belgrano Norte": 1, "Belgrano": 1, "Tren de la Costa": 3}
TREN_DE_LA_COSTA = {"Avenida Maipú", "Borges", "Libertador"}

REFORM_BUDGET_USD = 20_000

# Gemini free tier: about 20 requests a day per model, across the models in hh/ai.py, resetting at midnight
# Pacific time. Automatic runs spend up to AI_DAILY_CALLS - AI_MANUAL_RESERVE a day, best-ranked candidates first
# (each house costs 2 calls: photo read + verdict); the reserve is left for "Evaluar con IA" from the app
# (3 houses a day plus a retry or two).
AI_DAILY_CALLS = 120
AI_MANUAL_RESERVE = 10
BRIEF_MAX_CHARS = 250

# Phone alerts (ntfy.sh) for new listings at or above either threshold. Tapping one opens the house in the app.
SITE_URL = "https://tomasam2233.github.io/house-hunter/"
ALERT_PERCENTILE = 90
ALERT_AI_SCORE = 70
# ...and, whatever the score, a big lot at a good price around the Maipú sweet spot. The lot surface (terreno)
# is used when the listing or its text gives it, otherwise the total m2.
ALERT_BIG_LOT = {"min_m2": 300, "max_price": 230_000, "maipu_blocks": (4, 8)}

# Weights add up to 100, in the order of importance Tomás gave.
WEIGHTS = {
    "price": 22,        # effective price (asking + estimated reform) and $/m2
    "space": 18,        # total m2, covered m2, ambientes
    "location": 15,     # cuadras to Av. Maipú (peak at 6) or a train station, plus a nearby plaza/park
    "condition": 13,    # AI: how habitable it is and how much reform it needs
    "patio": 10,        # AI + text: size of garden / patio
    "vertical": 7,      # AI + text: room to build upwards
    "credit": 6,        # apto crédito hipotecario
    "garage": 4,        # highly desirable, not required
    "quiet": 3,         # distance from avenues + AI read of the street
    "light": 2,         # AI + listing tags
}
assert sum(WEIGHTS.values()) == 100


# Local agencies on Tokko Broker (see hh/sources/tokko.py). "key" = public web key found in their site,
# "site" = Tokko's own website template, searched and parsed page by page. Add more here.
AGENCIES = [
    {"name": "DIC Propiedades", "key": "23e7c1c635a8a47c413f9d49e464577f1e6b176c", "site": "https://www.dicpropiedades.com.ar"},
    {"name": "Carlos Bezruk Inmuebles", "key": "89557e136aea786f201e20bacfacf769fa96034d", "site": "https://carlosbezruk.com.ar"},
    {"name": "Caneva Propiedades", "site": "https://www.canevaprop.com"},
    {"name": "Álvarez Dupot Propiedades", "site": "https://www.alvarezdupot.com.ar"},
    {"name": "Real Props", "site": "https://www.realprops.com.ar"},
    {"name": "O'Duch Negocios Inmobiliarios", "site": "https://www.o-duch.com.ar"},
    {"name": "Martín Propiedades", "site": "https://www.martinprop.com.ar"},
    {"name": "Estudio García", "site": "https://www.estudio-garcia.ar"},
    {"name": "Molinari Propiedades", "site": "https://www.molinariprop.com.ar"},
    {"name": "Jorge Becco Bienes Raíces", "site": "https://www.beccopropiedades.com"},
    {"name": "Darío Martínez Propiedades", "site": "https://www.dmartinezpropiedades.com.ar"},
    {"name": "Basilio Inmobiliaria", "site": "https://www.basilioinmobiliaria.com"},
    {"name": "Martín Fonseca Propiedades", "site": "https://www.martinfonsecaprop.com"},
    {"name": "Braulio Inmuebles", "site": "https://www.braulioinmuebles.com"},
    {"name": "Bellagamba", "key": "dd0e6daf8ddc52df5b91f3f57224ac4d752c9db7", "site": "https://bellagamba.com"},
]
