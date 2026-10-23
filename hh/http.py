"""Polite HTTP with a real-browser TLS fingerprint (curl_cffi) and retries on bot-wall responses."""
import random, time
from curl_cffi import requests

HEADERS = {"Accept-Language": "es-AR,es;q=0.9,en;q=0.8"}


def get(url, tries=5, impersonate="chrome", pause=(1.5, 3.5)):
    last = None
    for attempt in range(tries):
        time.sleep(random.uniform(*pause) * (1 + attempt))
        try:
            r = requests.get(url, impersonate=impersonate, timeout=40, headers=HEADERS)
        except Exception as e:  # network hiccup
            last = e
            continue
        if r.status_code == 200:
            return r
        last = f"HTTP {r.status_code}"
        if r.status_code == 404:
            break
    raise RuntimeError(f"GET {url} failed: {last}")
