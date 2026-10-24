"""One-off: agency homepages, and whether Argenprop photos load directly from a GitHub runner."""
import re, sys
sys.path.insert(0, ".")
from curl_cffi import requests
import requests as plain

for site in ["carloscastano.com.ar", "o-duch.com.ar", "syrpropiedades.ar", "bellagamba.com", "mparrinello.com.ar"]:
    try:
        r = requests.get("https://" + site, impersonate="chrome", timeout=40)
        open(f"probe/site_{site}.html", "w").write(r.text)
        print(site, r.status_code, r.url, len(r.text), sorted(set(re.findall(r"tokko\w*|ficha\.info|wp-content|wix|xintel|kiteprop|properati|2clics|mapaprop|inmovilla|witei", r.text, re.I)))[:10])
    except Exception as e:
        print(site, "ERR", e)
r = plain.get("https://www.argenprop.com/static-content/67353881/28532505-d193-4d77-b0ee-39087104f592.jpg", timeout=30, headers={"User-Agent": "Mozilla/5.0"})
print("argenprop photo", r.status_code, r.headers.get("content-type"), len(r.content))
