"""Save AI reads produced outside the pipeline (another vision model, or a person) for queued listings.

python ai_fill.py results.json --analyst "claude"
results.json: {"zp-123": {"condition": 3, "reform_usd": 12000, ...}, ...}
"""
import json, os, sys
from hh import ai

path, analyst = sys.argv[1], sys.argv[sys.argv.index("--analyst") + 1] if "--analyst" in sys.argv else "manual"
for lid, res in json.load(open(path)).items():
    meta = json.load(open(os.path.join(ai.PENDING, lid + ".json")))
    ai.save_result(lid, res, meta["photos_key"], analyst)
    print("saved", lid)
