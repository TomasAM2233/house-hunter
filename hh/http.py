"""Polite HTTP with a real-browser TLS fingerprint (curl_cffi) and retries on bot-wall responses."""
import os, random, time
from urllib.parse import quote
from urllib.parse import urlencode  # noqa: F401  (re-exported for sources)
from curl_cffi import requests

HEADERS = {"Accept-Language": "es-AR,es;q=0.9,en;q=0.8"}


API_KEY = os.environ.get("SCRAPER_API_KEY")


def get(url, tries=5, impersonate="chrome", pause=(1.5, 3.5), blocked=None, via_api=False, render=False):
    """impersonate may be a list of browser profiles, tried in turn. blocked(r) -> True marks a 200 as a bot wall.
    via_api=True sends the request through ScraperAPI when SCRAPER_API_KEY is set (for sites that block cloud IPs).
    render=True has ScraperAPI load the page in a browser (10 credits instead of 1)."""
    if via_api and API_KEY:
        url = f"https://api.scraperapi.com/?api_key={API_KEY}&country_code=ar&url={quote(url, safe='')}" + ("&render=true" if render else "")
        tries, pause = min(tries, 2), (0, 0)
    profiles = [impersonate] if isinstance(impersonate, str) else list(impersonate)
    last = None
    for attempt in range(tries):
        time.sleep(random.uniform(*pause) * (1 + attempt))
        try:
            r = requests.get(url, impersonate=profiles[attempt % len(profiles)], timeout=150 if via_api else 40, headers=HEADERS)
        except Exception as e:  # network hiccup
            last = e
            continue
        if r.status_code == 200 and not (blocked and blocked(r)):
            return r
        last = f"HTTP {r.status_code}" + (" (bot wall)" if r.status_code == 200 else "")
        if r.status_code == 404:
            break
    raise RuntimeError(f"GET {url.split('url=')[-1] if via_api else url} failed: {last}")
