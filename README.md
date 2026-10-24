# House Hunter

Command center for finding a house in Olivos, Florida and La Lucila (Vicente López).
Scrapes listings, throws out the ones that break hard rules, reads the photos and text with a free
vision AI, and ranks the rest with our own weighted score. Runs for free on GitHub Actions + Pages.

## How it works

```
run.py
  hh/sources/zonaprop.py      search pages -> normalized listings (price, m², coords, photos)
  hh/sources/mercadolibre.py  search cards + item pages (older browser profiles get past the login wall)
  hh/sources/tokko.py         local agencies on Tokko Broker: public web key -> JSON API, or their Tokko site
  hh/geo.py                   cuadras to Av. Maipú, Puente Saavedra, nearest train (OSM data in geo/)
  hh/score.py                 hard filters + 10 weighted criteria
  hh/ai.py                    Gemini free tier reads up to 12 photos + description, cached per listing
build.py                      web/index.html for GitHub Pages (reads web/listings.json)
.github/workflows/hunt.yml    3 runs a day, commits data/, deploys Pages
```

## The rules (edit `hh/config.py`)

Hard filters, a listing is discarded if it breaks any:
- USD 140k–210k, USD 1,000–2,000 per total m²
- Casa or PH, 3+ ambientes, 100+ m² totales
- 3 to 15 cuadras from Av. Maipú, 5+ cuadras from Puente Saavedra
- Has a patio or garden (AI), is not a PH al fondo por pasillo (AI)
- Reform estimate under ~USD 35k (AI)
- Not a duplicate of another agency's post (same price and m², within 200 m)

Score out of 100, in our order of importance:

| Criterion | Pts | What it looks at |
|---|---|---|
| Price | 22 | asking + estimated reform, and USD/m² |
| Space | 18 | total m², covered m², ambientes |
| Location | 15 | min(cuadras to Maipú, cuadras to a Mitre/Belgrano station); ≤8 is preferred |
| Condition | 13 | AI condition 1–5 and reform estimate vs the USD 20k budget |
| Patio | 10 | AI patio size, or m² descubiertos from the text |
| Build upwards | 7 | AI read: own lot, one storey, no consorcio |
| Apto crédito | 6 | text, listing pill, AI |
| Garage | 4 | listing data or mention |
| Quiet | 3 | distance from Maipú + AI read of the street |
| Light | 2 | AI + listing tags |

## Sources

| Source | How | Notes |
|---|---|---|
| Zonaprop | search pages embed the listing JSON | blocks cloud IPs (403); fetched through ScrapingAnt (1 credit a page, full sweep every full run, newest page every hour). Fallback: ScraperAPI renders (10 credits a page), spaced out to fit its free plan |
| Mercado Libre | search grid + item pages | most fingerprints hit an account wall; `PROFILES` in the module are the ones that pass |
| Agencies (Tokko) | `AGENCIES` in `hh/config.py` | add an agency with its site URL; if the site ships a Tokko key, add `key` too |
| Argenprop | search cards + item pages | WAF blocks cloud IPs; same APIs as Zonaprop (photos through ScraperAPI), full sweep every full run, 2 newest pages every hour |

The same house usually shows up on several of these. `run.py` treats listings with the same price, total m²
within 3% and the same street (or under 250 m apart) as one, keeps the best-documented copy, and reuses its AI read.

## Setup (one time)

1. Repo Settings → Pages → Source: **GitHub Actions**.
2. Get a free Gemini key at https://aistudio.google.com/apikey and add it as the repo secret `GEMINI_API_KEY`.
3. Actions → hunt → Run workflow.

## Running locally

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
GEMINI_API_KEY=... .venv/bin/python run.py
.venv/bin/python build.py && open web/index.html   # or python -m http.server -d web
```

## AI reads without a key

With no `GEMINI_API_KEY`, `run.py` queues each new candidate to `data/ai_pending/` (a photo contact sheet
plus the text). Results written by hand or by another model go in a JSON file keyed by listing id and are
saved with `python ai_fill.py results.json --analyst claude`. The first batch (`ai_batches/`) was read this way.

## Runs and alerts

- **Full runs** at 08:17, 14:17 and 20:17 (Buenos Aires): every source, full sweeps.
- **Quick runs** every hour from 07:47 to 23:47: only the newest pages of Zonaprop and Argenprop, so a new listing
  is scored, read by the AI and alerted within the hour.
- **Alerts:** set the `NTFY_TOPIC` secret and subscribe to that topic in the free ntfy app. New listings at or above
  the alert thresholds (90th percentile or AI score 70+ by default; editable in the app, saved in `data/settings.json`) send a push notification.
