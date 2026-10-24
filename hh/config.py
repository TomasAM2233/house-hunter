"""Search criteria and scoring weights. Edit this file to change what the hunter looks for."""

SEARCH = {
    "price_min": 140_000,      # USD
    "price_max": 210_000,      # USD
    "ppm2_min": 1_000,         # USD per total m2
    "ppm2_max": 2_000,
    "min_ambientes": 3,
    "min_total_m2": 100,
    "types": ["casa", "ph"],
    "zones": ["Olivos", "Florida", "La Lucila"],
}

# Geography, in "cuadras". One cuadra is taken as 100 m of straight-line distance.
BLOCK_M = 100
MAIPU_MIN_BLOCKS = 3        # closer than this to Av. Maipú is too noisy
MAIPU_MAX_BLOCKS = 15       # farther than this is out of the zone
MAIPU_IDEAL_BLOCKS = 8      # inside this (or this close to a train) is preferred
PUENTE_SAAVEDRA = (-34.5383, -58.4762)
PUENTE_MIN_BLOCKS = 5

# Lines that actually get you to Palermo / Belgrano / Recoleta / Centro.
# Tren de la Costa stations count, but with a penalty since you need a transfer.
STATION_LINE_PENALTY_BLOCKS = {"Mitre": 0, "Belgrano Norte": 1, "Belgrano": 1, "Tren de la Costa": 3}
TREN_DE_LA_COSTA = {"Avenida Maipú", "Borges", "Libertador"}

REFORM_BUDGET_USD = 20_000

# Weights add up to 100, in the order of importance Tomás gave.
WEIGHTS = {
    "price": 22,        # effective price (asking + estimated reform) and $/m2
    "space": 18,        # total m2, covered m2, ambientes
    "location": 15,     # walking distance to Av. Maipú or a train station
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
]
