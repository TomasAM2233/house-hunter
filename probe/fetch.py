"""One-off: why is Argenprop 20602045 missing? Fetch the item, parse it like a card, and look for it in the search pages."""
import json, re, sys
sys.path.insert(0, ".")
from bs4 import BeautifulSoup
from hh import http
from hh.sources import argenprop
URL = "https://www.argenprop.com/casa-en-venta-en-olivos-vias-maipu-3-ambientes--20602045"
html = http.get(URL, via_api=True).text
open("probe/ap_item.html", "w").write(html)
s = BeautifulSoup(html, "html.parser")
print("title:", s.title.get_text(strip=True) if s.title else None)
for sel in [".titlebar__price", ".titlebar__address", ".property-main-features", ".property-features", ".titlebar"]:
    e = s.select_one(sel)
    print(sel, "->", " ".join(e.get_text(" ", strip=True).split())[:400] if e else None)
print("price meta:", re.findall(r'(?:montooperacion|idmoneda|"price"|precio)[^,<]{0,60}', html)[:10])
for newest in (False, True):
    for page in range(1, 16):
        u = argenprop.search_url(page, newest)
        try:
            h = http.get(u, via_api=True).text
        except Exception as e:
            print(u, "ERR", e); break
        found = "20602045" in h
        n = h.count('class="listing__item')
        print(("newest " if newest else "full ") + f"p{page}: {n} items, found={found}", u)
        if found or n == 0 or (newest and page >= 3):
            break
