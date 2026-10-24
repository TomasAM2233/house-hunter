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
