"""One-off: find the websites of the agencies Tomás photographed, and fetch two Zonaprop avisos."""
import json, re, sys
sys.path.insert(0, ".")
import requests
from hh import http

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
CANDIDATES = {
    "Diego Lopez Pereyra": ["lopezpereyraprop.com.ar", "www.lopezpereyraprop.com.ar"],
    "Di Nardo": ["www.dinardoprop.com.ar"],
    "Marolla": ["www.marollainmobiliaria.com.ar", "marollainmobiliaria.com.ar"],
    "Martin Fonseca": ["www.martinfonsecaprop.com", "martinfonsecaprop.com"],
    "Lencke": ["www.lencke.com.ar", "www.lencke.com"],
    "Houghton": ["www.houghtonpropiedades.com.ar", "www.houghtonpropiedades.com", "houghton.com.ar"],
    "Barbini": ["www.barbini.com.ar", "www.barbinipropiedades.com.ar", "www.apbarbini.com.ar", "www.barbinipropiedades.com"],
    "Braulio": ["www.braulioinmuebles.com", "www.braulioinmuebles.com.ar", "www.braulio.com.ar"],
    "Martin Pinus": ["www.martinpinus.com", "www.martinpinus.com.ar"],
    "Ambito Urbano": ["www.ambitourbano.com.ar", "www.ambitourbanoinmobiliaria.com.ar", "www.ambitourbano.com"],
    "MP Bienes Raices": ["www.mpbienesraices.com.ar", "www.mpbienesraices.com", "www.monicapaschetti.com.ar"],
    "Canali": ["www.canalipropiedades.com.ar", "www.canalipropiedades.com", "www.canali.com.ar"],
    "Inguer": ["www.inguer.com.ar", "www.inguerpropiedades.com.ar", "www.inguer.com"],
    "f+f studio": ["www.ffstudio.com.ar", "www.ffcasasdediseno.com", "www.ffstudio.ar"],
    "RE/MAX": ["www.remax.com.ar"],
}
MARK = ["tokko", "wp-content", "xintel", "kiteprop", "wasi", "inmoweb", "witei", "2clics", "mapaprop", "mediacore", "__NEXT_DATA__", "gatsby"]
report = {}
for name, hosts in CANDIDATES.items():
    report[name] = []
    for h in hosts:
        try:
            r = requests.get("https://" + h, headers=UA, timeout=20)
            t = r.text
            key = re.search(r"[\"'=:]([0-9a-f]{40})[\"'&]", t)
            row = {"host": h, "status": r.status_code, "final": r.url, "bytes": len(t),
                   "title": (re.search(r"<title>([^<]*)", t, re.I) or [None, ""])[1].strip()[:80],
                   "marks": {m: t.lower().count(m.lower()) for m in MARK if m.lower() in t.lower()},
                   "key40": key.group(1) if key else None,
                   "p_links": len(set(re.findall(r'href="/p/(\d+)-', t)))}
            if row["status"] == 200:
                open(f"probe/ag_{h.replace('.', '_')}.html", "w").write(t)
                if "tokko" in t.lower():
                    b = requests.get(r.url.rstrip("/") + "/Buscar?operation=1&ptypes=3,13&locations=25836,25820,25829&currency=USD", headers=UA, timeout=25)
                    row["buscar"] = [b.status_code, len(set(re.findall(r'href="/p/(\d+)-', b.text)))]
        except Exception as e:
            row = {"host": h, "error": str(e)[:120]}
        report[name].append(row)
        print(name, row)
json.dump(report, open("probe/agencies.json", "w"), indent=1, ensure_ascii=False)

for zid, u in {"53020994": "https://www.zonaprop.com.ar/propiedades/clasificado/veclcain-chalet-en-1-planta-reciclado-jardin-cochera.-53020994.html",
               "58852278": "https://www.zonaprop.com.ar/propiedades/clasificado/veclcain-chalet-al-frente-3-amb-c-cochera-y-patio-unidad-al-58852278.html"}.items():
    try:
        r = requests.get("https://api.scrapingant.com/v2/general", params={"url": u, "x-api-key": http.ANT_KEY, "browser": "false"}, timeout=90)
        open(f"probe/zp_{zid}.html", "w").write(r.text)
        print("zp", zid, r.status_code, len(r.text))
    except Exception as e:
        print("zp", zid, e)
