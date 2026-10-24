"""One-off: which listing system each agency site runs on, seen from a GitHub runner."""
import re
from curl_cffi import requests
SITES = """martinprop.com.ar estudio-garcia.ar dinardoprop.com.ar novoapropiedades.com.ar izr.com.ar molinariprop.com.ar
coldwellbankernova.com beccopropiedades.com lopez.com.ar todoprops.com marininmuebles.com.ar godoyasesores.com yacoub.com.ar
www.depaolapropiedades.com www.dmartinezpropiedades.com.ar www.azarapropiedades.com.ar www.basilioinmobiliaria.com
www.tizado.com/olivos vanesapropi.com www.o-duch.com.ar/Buscar?operation=1 mparrinello.com.ar/propiedades/""".split()
for site in SITES:
    try:
        r = requests.get("https://" + site, impersonate="chrome", timeout=40)
        fn = "probe/site_" + re.sub(r"\W", "_", site) + ".html"
        open(fn, "w").write(r.text)
        keys = sorted(set(re.findall(r'"tokko"\s*:\s*"([0-9a-f]{40})"|key=([0-9a-f]{40})', r.text)))
        sig = sorted(set(m.lower() for m in re.findall(r"tokko\w*|ficha\.info|wp-content|wix|xintel|kiteprop|brokian|2clics|mapaprop|inmovilla|witei|remax|NoMoreProperties", r.text, re.I)))
        print(site, r.status_code, r.url, len(r.text), sig[:8], keys[:2])
    except Exception as e:
        print(site, "ERR", str(e)[:100])

import os
from urllib.parse import quote
K = os.environ["SCRAPER_API_KEY"]
ZP = "https://www.zonaprop.com.ar/casas-ph-venta-olivos-florida-la-lucila-mas-de-3-ambientes-140000-210000-dolar.html"
print("account", requests.get(f"https://api.scraperapi.com/account?api_key={K}", timeout=30).text[:300])
for extra in ["", "&premium=true", "&ultra_premium=true", "&render=true&premium=true"]:
    try:
        r = requests.get(f"https://api.scraperapi.com/?api_key={K}&country_code=ar&url={quote(ZP, safe='')}{extra}", timeout=120)
        print("zp", extra or "plain", r.status_code, len(r.text), "__PRELOADED_STATE__" in r.text, r.text[:150].replace("\n", " ") if r.status_code != 200 else "")
        if "__PRELOADED_STATE__" in r.text:
            break
    except Exception as e:
        print("zp", extra, "ERR", e)
print("account", requests.get(f"https://api.scraperapi.com/account?api_key={K}", timeout=30).text[:300])
