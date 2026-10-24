"""One-off: newest-first sort URLs for Zonaprop and Argenprop, through ScraperAPI."""
import os, re
from urllib.parse import quote
from curl_cffi import requests
K = os.environ["SCRAPER_API_KEY"]
api = lambda u, extra="": requests.get(f"https://api.scraperapi.com/?api_key={K}&country_code=ar&url={quote(u, safe='')}{extra}", timeout=150)
for u in ["https://www.argenprop.com/casas-o-ph/venta/olivos-o-florida-o-la-lucila/dolares-140000-210000?orden-masnuevos"]:
    r = api(u); h = r.text
    print("AP", r.status_code, re.search(r"<title>(.*?)</title>", h, re.S).group(1)[:90] if "<title>" in h else h[:200])
    print("  first ids", re.findall(r'idaviso="(\d+)"', h)[:8])
    print("  order options", sorted(set(re.findall(r'\?(orden-[a-z-]+)', h)))[:10])
u = "https://www.zonaprop.com.ar/casas-ph-venta-olivos-florida-la-lucila-mas-de-3-ambientes-140000-210000-dolar-orden-publicado-descendente.html"
r = api(u, "&render=true"); h = r.text
print("ZP", r.status_code, re.search(r"<title>(.*?)</title>", h, re.S).group(1)[:120] if "<title>" in h else h[:200])
print("  first ids", re.findall(r'data-qa="posting PROPERTY" data-id="(\d+)"', h)[:8])
print("  sort links", sorted(set(re.findall(r'orden-[a-z-]+', h)))[:10])
print("credits", requests.get(f"https://api.scraperapi.com/account?api_key={K}", timeout=30).json().get("creditsLeft"))
