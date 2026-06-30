"""Seeds all university JSON files into Supabase universities table."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from api.database import upsert_university

here = Path(__file__).parent
files = ["universities_seed.json", "universities_expansion.json"]

ok, fail = 0, 0
for fname in files:
    fpath = here / fname
    if not fpath.exists():
        print(f"  SKIP {fname} (not found)")
        continue
    print(f"\n--- {fname} ---")
    data = json.loads(fpath.read_text(encoding="utf-8"))
    for uni in data:
        try:
            upsert_university(uni)
            print(f"  OK  {uni['name']}")
            ok += 1
        except Exception as e:
            print(f"  FAIL {uni['name']}: {e}")
            fail += 1

print(f"\nDone: {ok} inserted/updated, {fail} failed")
