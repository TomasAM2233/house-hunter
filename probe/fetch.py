"""One-off: photos of Argenprop 20602045 and the area around it."""
import io, json, os, re, sys, requests
sys.path.insert(0, ".")
from PIL import Image
from hh import http
LAT, LNG = -34.50831, -58.50481
os.makedirs("probe/photos", exist_ok=True)
js = http.get("https://www.argenprop.com/typescripts/dist/property.f6528e5034b0b612c028.js", via_api=True).text
open("probe/property.js", "w").write(js)
for m in re.findall(r".{0,160}(?:/api/|ajax|fetch\(|\.get\(\"/|Galeria|galeria|multimedia\b).{0,200}", js)[:25]:
    print("JS:", m)
html = open("probe/ap_item_rendered.html").read()
base = [re.sub(r"_u_[a-z]+\.jpg", ".jpg", "https://www.argenprop.com/" + p) for p in dict.fromkeys(re.findall(r"static-content/54020602/[0-9a-f-]+(?:_u_[a-z]+)?\.jpg", html))]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36", "Referer": "https://www.argenprop.com/"}
def grab(u, i):
    tries = [("direct", lambda: requests.get(u, headers=UA, timeout=30)),
             ("wsrv", lambda: requests.get("https://wsrv.nl/", params={"url": u.split("://")[1], "w": 1000}, timeout=40)),
             ("ant", lambda: requests.get("https://api.scrapingant.com/v2/general", params={"url": u, "x-api-key": http.ANT_KEY, "browser": "false"}, timeout=60))]
    for name, f in tries:
        try:
            r = f()
            im = Image.open(io.BytesIO(r.content)).convert("RGB"); im.thumbnail((1000, 1000))
            im.save(f"probe/photos/{i:02d}.jpg", "JPEG", quality=72); print("photo", i, "via", name); return name
        except Exception as e:
            print("photo", i, name, "failed", getattr(r, "status_code", "") if "r" in dir() else "", str(e)[:80])
    return None
for i, u in enumerate(base):
    grab(u, i)
q = f"""[out:json][timeout:90];
(
 nwr(around:1800,{LAT},{LNG})[amenity~"^(school|kindergarten|college|university|childcare)$"];
 nwr(around:1500,{LAT},{LNG})[leisure~"^(park|playground|sports_centre|fitness_centre|swimming_pool|stadium|track)$"][name];
 nwr(around:1500,{LAT},{LNG})[club][name];
 nwr(around:2500,{LAT},{LNG})[railway~"^(station|halt)$"];
 nwr(around:1200,{LAT},{LNG})[shop~"^(supermarket|greengrocer|butcher|bakery|mall)$"];
 nwr(around:2000,{LAT},{LNG})[amenity~"^(hospital|clinic|police|fire_station|pharmacy|bank|marketplace|library)$"];
 nwr(around:600,{LAT},{LNG})[highway=bus_stop];
 nwr(around:800,{LAT},{LNG})[route=bus];
);
out center tags;"""
for ep in ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]:
    try:
        r = requests.post(ep, data={"data": q}, headers={"User-Agent": "house-hunter-probe/1.0 (github.com/TomasAM2233/house-hunter)", "Accept": "application/json"}, timeout=120)
        print("overpass", ep, r.status_code)
        if r.ok:
            open("probe/around.json", "w").write(r.text); print("elements", len(r.json()["elements"])); break
    except Exception as e:
        print("overpass err", ep, str(e)[:100])
