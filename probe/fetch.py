"""One-off: which Gemini models still have free quota today, and what the limits are."""
import os, re, requests
k = os.environ["GEMINI_API_KEY"]
for m in ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-pro-latest"]:
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}", json={"contents": [{"parts": [{"text": "Respondé solo: ok"}]}]}, timeout=60)
    lim = re.findall(r'"quotaId": "([^"]+)".{0,200}?"quotaValue": "(\d+)"', r.text, re.S)
    print(m, r.status_code, lim[:4] if lim else r.text[:160].replace("\n", " "))
