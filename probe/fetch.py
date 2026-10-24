"""One-off: demo phone notification through the NTFY_TOPIC secret."""
import os, requests
t = os.environ.get("NTFY_TOPIC", "")
print("topic set:", bool(t), len(t))
r = requests.post("https://ntfy.sh/", timeout=20, json={"topic": t, "title": "Demo · P97 · 74/100 · USD 185.000 · Olivos",
    "message": "Prueba de House Hunter: así te va a llegar una casa nueva del top 10%. Tocá para abrir la app.",
    "click": "https://tomasam2233.github.io/house-hunter/", "priority": 4, "tags": ["house"]})
print(r.status_code, r.text[:200])
# resend 1792820590
