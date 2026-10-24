"""One-off: does ScrapingAnt get through Zonaprop, and in which mode?"""
import os, re, time
from urllib.parse import quote
from curl_cffi import requests
K = os.environ["SCRAPINGANT_API_KEY"]
ZP = "https://www.zonaprop.com.ar/casas-ph-venta-olivos-florida-la-lucila-mas-de-3-ambientes-140000-210000-dolar-orden-publicado-descendente.html"
def usage():
    try: return requests.get(f"https://api.scrapingant.com/v2/usage?x-api-key={K}", timeout=30).text[:200]
    except Exception as e: return str(e)
print("usage", usage())
for mode in ["browser=false", "browser=false&proxy_country=AR", "browser=true&proxy_country=AR", "browser=false&proxy_type=residential&proxy_country=AR", "browser=true&proxy_type=residential&proxy_country=AR"]:
    t = time.time()
    try:
        r = requests.get(f"https://api.scrapingant.com/v2/general?url={quote(ZP, safe='')}&x-api-key={K}&{mode}", timeout=180)
        h = r.text
        print(mode, r.status_code, len(h), round(time.time() - t), "STATE" if "__PRELOADED_STATE__" in h else "", len(re.findall(r'data-qa="posting PROPERTY"', h)), "cards",
              (re.search(r"<title>(.*?)</title>", h, re.S).group(1)[:70] if "<title>" in h else h[:150].replace("\n", " ")))
        if "__PRELOADED_STATE__" in h or 'posting PROPERTY' in h:
            open("probe/ant_" + re.sub(r"\W", "_", mode) + ".html", "w").write(h)
    except Exception as e:
        print(mode, "ERR", str(e)[:150])
    print("  usage", usage())
