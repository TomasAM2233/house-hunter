"""One-off: photos and surroundings of Argenprop 20602045 (José Ingenieros 2500, Olivos)."""
import io, json, os, re, sys, requests
sys.path.insert(0, ".")
from PIL import Image
from hh import http
URL = "https://www.argenprop.com/casa-en-venta-en-olivos-vias-maipu-3-ambientes--20602045"
LAT, LNG = -34.50831, -58.50481
os.makedirs("probe/photos", exist_ok=True)
pics = []
try:
    r = requests.get("https://api.scrapingant.com/v2/general", params={"url": URL, "x-api-key": http.ANT_KEY, "browser": "true"}, timeout=120)
    html = r.text
    open("probe/ap_item_rendered.html", "w").write(html)
    pics = list(dict.fromkeys(re.sub(r"_u_[a-z]+\.jpg", ".jpg", "https://www.argenprop.com/" + p) for p in re.findall(r"static-content/54020602/[0-9a-f-]+(?:_u_[a-z]+)?\.jpg", html)))
    print("rendered:", r.status_code, len(html), "photos", len(pics))
except Exception as e:
    print("render failed", e)
if len(pics) < 10:
    js = http.get("https://www.argenprop.com/typescripts/dist/property.f6528e5034b0b612c028.js", via_api=True).text
    for m in sorted(set(re.findall(r"[\"'`](/[A-Za-z0-9_/\-{}$.]*?(?:foto|galer|multimedia|imagen|photo|media)[A-Za-z0-9_/\-{}$.]*)[\"'`]", js, re.I)))[:40]:
        print("js endpoint:", m)
    for m in re.findall(r".{80}(?:galer|multimedia).{120}", js, re.I)[:8]:
        print("js ctx:", m)
for i, u in enumerate(pics[:60]):
    try:
        b = http.get(u, via_api=True, binary=True).content
        im = Image.open(io.BytesIO(b)).convert("RGB"); im.thumbnail((1000, 1000))
        im.save(f"probe/photos/{i:02d}.jpg", "JPEG", quality=70)
    except Exception as e:
        print("photo", i, e)
print("saved photos", len(os.listdir("probe/photos")))
q = f"""[out:json][timeout:90];
(
 nwr(around:1800,{LAT},{LNG})[amenity~"^(school|kindergarten|college|university|childcare)$"];
 nwr(around:1500,{LAT},{LNG})[leisure~"^(park|playground|sports_centre|fitness_centre|swimming_pool|stadium|track)$"][name];
 nwr(around:1500,{LAT},{LNG})[club][name];
 nwr(around:1500,{LAT},{LNG})[leisure=pitch][name];
 nwr(around:2500,{LAT},{LNG})[railway=station];
 nwr(around:1200,{LAT},{LNG})[shop~"^(supermarket|greengrocer|butcher|bakery)$"];
 nwr(around:2000,{LAT},{LNG})[amenity~"^(hospital|clinic|police|fire_station|pharmacy|bank|marketplace|library)$"];
 nwr(around:600,{LAT},{LNG})[highway=bus_stop];
 node(around:2000,{LAT},{LNG})[amenity=police];
);
out center tags;"""
for ep in ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]:
    try:
        r = requests.post(ep, data={"data": q}, timeout=120)
        if r.ok:
            open("probe/around.json", "w").write(r.text); print("overpass ok", len(r.json()["elements"])); break
        print("overpass", r.status_code)
    except Exception as e:
        print("overpass err", e)
qr = f"""[out:json][timeout:60];(way(around:2500,{LAT},{LNG})[highway~"^(primary|trunk|secondary)$"][name];);out tags center;"""
try:
    r = requests.post("https://overpass-api.de/api/interpreter", data={"data": qr}, timeout=90)
    open("probe/roads.json", "w").write(r.text); print("roads ok")
except Exception as e:
    print("roads err", e)
try:
    r = requests.get("https://nominatim.openstreetmap.org/reverse", params={"lat": LAT, "lon": LNG, "format": "json", "zoom": 18}, headers={"User-Agent": "house-hunter-probe"}, timeout=30)
    print("reverse:", r.json().get("display_name"))
except Exception as e:
    print("reverse err", e)
