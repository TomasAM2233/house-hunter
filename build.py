"""Build the dashboard.

python build.py            -> web/index.html (static site for GitHub Pages; loads web/listings.json)
python build.py --embed    -> dist/house-hunter.html (single file with data and photo thumbnails inlined)
"""
import argparse, base64, io, json, os
import requests
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(ROOT, "web", "app.html")
DATA = os.path.join(ROOT, "data", "listings.json")
HEAD = '<!doctype html>\n<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'


def thumb(url, size, q=62):
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail(size)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", action="store_true")
    ap.add_argument("--photos", type=int, default=5, help="photos per candidate to inline")
    args = ap.parse_args()
    app = open(APP).read()
    if not args.embed:
        page = app.replace("__HH_DATA__", "")
        head, rest = page.split("</style>", 1)
        open(os.path.join(ROOT, "web", "index.html"), "w").write(HEAD + head + "</style>\n</head><body>\n" + rest + "\n</body></html>\n")
        print("wrote web/index.html")
        return
    data = json.load(open(DATA))
    for l in data["listings"]:
        if not l.get("active", True) or l.get("duplicate_of"):
            continue
        if l["discard"]:
            l["thumbs"] = [thumb(u, (320, 240), q=50) for u in l["photos"][:1]]
        else:
            l["thumbs"] = [thumb(u, (560, 420) if i == 0 else (360, 270), q=58) for i, u in enumerate(l["photos"][:args.photos])]
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", "house-hunter.html")
    open(out, "w").write(app.replace("__HH_DATA__", blob))
    print(f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
