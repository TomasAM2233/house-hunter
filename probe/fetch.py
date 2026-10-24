"""One-off: the full photo gallery of Argenprop 20602045."""
import io, os, re, sys, requests
sys.path.insert(0, ".")
from PIL import Image
from hh import http
G = "https://www.argenprop.com/aviso/gallerypartial?idAviso=20602045&tipo=fotos"
r = requests.get("https://api.scrapingant.com/v2/general", params={"url": G, "x-api-key": http.ANT_KEY, "browser": "false"}, timeout=90)
open("probe/gallery.html", "w").write(r.text)
pics = list(dict.fromkeys(re.sub(r"_u_[a-z]+\.jpg", ".jpg", "https://www.argenprop.com/" + p) for p in re.findall(r"static-content/54020602/[0-9a-f-]+(?:_u_[a-z]+)?\.jpg", r.text)))
print("gallery", r.status_code, len(r.text), "photos", len(pics))
os.makedirs("probe/photos", exist_ok=True)
for i, u in enumerate(pics):
    if os.path.exists(f"probe/photos/g{i:02d}.jpg"):
        continue
    for _ in range(2):
        try:
            b = requests.get("https://api.scrapingant.com/v2/general", params={"url": u, "x-api-key": http.ANT_KEY, "browser": "false"}, timeout=60).content
            im = Image.open(io.BytesIO(b)).convert("RGB"); im.thumbnail((900, 900))
            im.save(f"probe/photos/g{i:02d}.jpg", "JPEG", quality=70); break
        except Exception as e:
            print("photo", i, str(e)[:80])
print("saved", len(os.listdir("probe/photos")))
