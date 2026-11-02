"""When each search group of the API-fed portals (Zonaprop, Argenprop) was last swept in full, in data/sweeps.json.

The CABA barrios have several times the listings of Vicente López, and every page through the unblocking APIs
costs free credits. So big groups get a full sweep only every so often (their "every" hours), and in between, like
every group in the hourly quick runs, just their newest pages, which is where new listings show up. A group swept
in full and without failures is the only place where a listing that's gone gets marked inactive.
"""
import json, os, time

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sweeps.json")
FMT = "%Y-%m-%d %H:%M"


def _load():
    try:
        return json.load(open(PATH))
    except Exception:
        return {}


def due(key, every_hours):
    """True when the group's last full sweep is older than every_hours (or there was none)."""
    if not every_hours:
        return True
    t = _load().get(key)
    return not t or time.time() - time.mktime(time.strptime(t, FMT)) >= every_hours * 3600 - 1800


def done(key):
    d = _load()
    d[key] = time.strftime(FMT)
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(d, open(PATH, "w"), indent=1, sort_keys=True)
