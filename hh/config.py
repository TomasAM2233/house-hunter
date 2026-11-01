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

# Investment side of a house (see score.investment). m2 still buildable use the FOT of the house's official zone
# (hh/zoning.py: R1 0.8, R2 1.0 times the lot...); FOT_ASSUMED stands in where it isn't known. Land doesn't depreciate and the building does,
# so a cheap m2 of lot and m2 still left to build are what hold value; a high price per covered m2 is mostly a
# new-build premium that's lost within a few years (in the hunt's data: ~USD 2.500/m2 at 0-5 years, ~1.600 at 40-60).
FOT_ASSUMED = 0.9
BUILDABLE_FULL_M2 = 150       # m2 still buildable that count as "a whole extra floor"
# Land holds its value and the building wears out (Tomás, 2026-10-31). A house is split into what its building is
# worth (covered m2 x what it costs to build x what's left of it at its age) and the land it sits on, which is the rest
# of the price. The land is then valued at what nearby houses implicitly pay per m2 of lot (geo/land_market.json, built
# by land_market_build.py) and the building is aged HORIZON_YEARS: "value at the horizon / price" is how much of what
# they pay is still there then, in today's dollars. See score.land_value.
BUILD_COST_M2 = 1_480         # USD per m2 to build a house here today
DEPRECIATION_PER_YEAR = 0.012 # share of the building's value lost each year (straight line, ~80 years of life)...
BUILDING_FLOOR = 0.25         # ...down to this share, which an old house that still stands keeps
AGE_ASSUMED = 40              # years, when the listing doesn't say (the hunt's median; "0" mostly means not given)
HORIZON_YEARS = 10
PH_LAND_SHARE = 0.8           # share of a PH's total m2 taken as its piece of the shared lot
LAND_NEIGHBOURS = 20          # houses around it that set a listing's market price per m2 of lot
VALUE_KEPT = (0.6, 1.2)       # value at the horizon / price: worst .. best for the investment score

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

# Weights add up to 100, in the order of importance Tomás gave. "investment" was added on 2026-10-30, when he
# decided to buy where they want to live but to make it as good an investment as possible, and raised to one of
# the two heaviest on 2026-10-31 (he asked for it), mostly taken from "vertical", which it now covers.
WEIGHTS = {
    "price": 18,        # effective price (asking + estimated reform) and $/m2
    "investment": 18,   # resale value: what's still there in 10 years (land at the area's price + aged building), m2 still buildable
    "space": 14,        # total m2, covered m2, ambientes
    "location": 14,     # cuadras to Av. Maipú (peak at 6) or a train station, plus a nearby plaza/park
    "condition": 11,    # AI: how habitable it is and how much reform it needs
    "patio": 9,         # AI + text: size of garden / patio
    "credit": 6,        # apto crédito hipotecario
    "vertical": 4,      # AI + text: room to build upwards
    "garage": 3,        # highly desirable, not required
    "quiet": 2,         # distance from avenues + AI read of the street
    "light": 1,         # AI + listing tags
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
