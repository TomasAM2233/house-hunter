"""Lay a run's AI caches over main's after a push race, keeping the newer entry for each listing.

python merge_ai.py SAVED_DIR   # SAVED_DIR holds this run's data/ai_cache.json etc.; the working tree is main
Used by the workflows when a rebase fails, so a hunt run and an "Evaluar con IA" run never erase each other's reads."""
import json, os, sys

FILES = ["data/ai_cache.json", "data/ai_final.json", "data/ai_results.json"]
when = lambda v: (v or {}).get("ts") or (v or {}).get("done_at") or ""

for f in FILES:
    saved = os.path.join(sys.argv[1], f)
    if not os.path.exists(saved):
        continue
    mine = json.load(open(saved))
    main = json.load(open(f)) if os.path.exists(f) else {}
    for k, v in mine.items():
        if k not in main or when(v) >= when(main[k]):
            main[k] = v
    json.dump(main, open(f, "w"), ensure_ascii=False, indent=1)
    print("merged", f)
