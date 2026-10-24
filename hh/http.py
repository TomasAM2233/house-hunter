"""Polite HTTP with a real-browser TLS fingerprint (curl_cffi) and retries on bot-wall responses."""
import os, random, time
from urllib.parse import quote
from urllib.parse import urlencode  # noqa: F401  (re-exported for sources)
from curl_cffi import requests

HEADERS = {"Accept-Language": "es-AR,es;q=0.9,en;q=0.8"}


# Unblocking APIs for sites that block cloud IPs (Zonaprop, Argenprop). ScrapingAnt goes first: its plain fetch
# (1 credit, 10,000 free a month) gets through both. ScraperAPI (1,000 free a month) is the fallback, and the one
# used for images, since ScrapingAnt returns pages as text.
ANT_KEY = os.environ.get("SCRAPINGANT_API_KEY")
API_KEY = os.environ.get("SCRAPER_API_KEY")


def _routes(url, render, binary):
    q = quote(url, safe="")
    ant = [f"https://api.scrapingant.com/v2/general?url={q}&x-api-key={ANT_KEY}&browser=false"] if ANT_KEY and not binary else []
    sa = [f"https://api.scraperapi.com/?api_key={API_KEY}&country_code=ar&url={q}" + ("&render=true" if render else "")] if API_KEY else []
    return ant + sa


def get(url, tries=5, impersonate="chrome", pause=(1.5, 3.5), blocked=None, via_api=False, render=False, binary=False):
    """impersonate may be a list of browser profiles, tried in turn. blocked(r) -> True marks a 200 as a bot wall.
    via_api=True sends the request through the unblocking APIs above, in order, when their keys are set.
    render=True asks ScraperAPI for a browser render (10 credits instead of 1); binary=True is for images."""
    if via_api and _routes(url, render, binary):
        errors = []
        for api in _routes(url, render, binary):
            for attempt in range(2):
                try:
                    r = requests.get(api, timeout=150)
                except Exception as e:
                    errors.append(f"{api.split('/')[2]}: {str(e)[:80]}")
                    continue
                if r.status_code == 200 and not (blocked and blocked(r)):
                    return r
                errors.append(f"HTTP {r.status_code} from {api.split('/')[2]}")
                if r.status_code in (401, 403, 404, 422):
                    break
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"GET {url} failed: {'; '.join(errors)}")
    profiles = [impersonate] if isinstance(impersonate, str) else list(impersonate)
    last = None
    for attempt in range(tries):
        time.sleep(random.uniform(*pause) * (1 + attempt))
        try:
            r = requests.get(url, impersonate=profiles[attempt % len(profiles)], timeout=40, headers=HEADERS)
        except Exception as e:  # network hiccup
            last = e
            continue
        if r.status_code == 200 and not (blocked and blocked(r)):
            return r
        last = f"HTTP {r.status_code}" + (" (bot wall)" if r.status_code == 200 else "")
        if r.status_code == 404:
            break
    raise RuntimeError(f"GET {url} failed: {last}")
