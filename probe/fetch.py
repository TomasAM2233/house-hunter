"""One-off: Zonaprop rendered through ScraperAPI, and a Brokian agency listing page."""
import os
from urllib.parse import quote
from curl_cffi import requests
K = os.environ["SCRAPER_API_KEY"]
ZP = "https://www.zonaprop.com.ar/casas-ph-venta-olivos-florida-la-lucila-mas-de-3-ambientes-140000-210000-dolar.html"
acct = lambda: requests.get(f"https://api.scraperapi.com/account?api_key={K}", timeout=30).json().get("creditsLeft")
print("credits", acct())
for extra in ["&render=true", "&render=true&premium=true"]:
    r = requests.get(f"https://api.scraperapi.com/?api_key={K}&country_code=ar&url={quote(ZP, safe='')}{extra}", timeout=150)
    print("zp", extra, r.status_code, len(r.text), "credits", acct())
    open(f"probe/zp{extra.replace('&', '_').replace('=', '')}.html", "w").write(r.text)
for u in ["https://carloscastano.com.ar/propiedades", "https://carloscastano.com.ar/propiedades?operation=venta"]:
    r = requests.get(u, impersonate="chrome", timeout=40)
    print(u, r.status_code, len(r.text))
    open("probe/brokian_" + str(len(u)) + ".html", "w").write(r.text)
