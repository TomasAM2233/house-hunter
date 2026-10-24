"""One-off: is the Gemini key there, and which models answer?"""
import os, requests
k = os.environ.get("GEMINI_API_KEY", "")
print("key set:", bool(k), len(k))
r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={k}&pageSize=200", timeout=30)
print("list", r.status_code, r.text[:300] if r.status_code != 200 else "")
if r.ok:
    ms = [m["name"] for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    print([m for m in ms if "flash" in m or "pro" in m][:40])
for m in ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-flash-lite"]:
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}", json={"contents": [{"parts": [{"text": "Decí hola en una palabra."}]}]}, timeout=60)
    print(m, r.status_code, r.text[:300].replace("\n", " "))
