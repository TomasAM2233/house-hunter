"""One-off: save an Argenprop search page and one listing page fetched through ScraperAPI, to write the parser."""
import re, sys
sys.path.insert(0, ".")
from hh import http

u = "https://www.argenprop.com/casas-o-ph/venta/olivos-o-florida-o-la-lucila/dolares-140000-210000"
html = http.get(u, via_api=True).text
open("probe/argenprop_search.html", "w").write(html)
links = list(dict.fromkeys(re.findall(r'href="(/[a-z0-9-]+--\d+)"', html)))
print(len(html), len(links), links[:3])
if links:
    open("probe/argenprop_item.html", "w").write(http.get("https://www.argenprop.com" + links[0], via_api=True).text)
