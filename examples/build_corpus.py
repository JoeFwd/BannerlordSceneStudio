"""Build the scene corpus index over the Bannerlord Modules directory.

Writes corpus.json at the repo root and prints summary statistics.

Usage (from repo root)::

    $env:PYTHONPATH="."; python examples/build_corpus.py
"""
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.corpus import build_corpus, save_corpus

MODULES_DIR = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
)
OUTPUT_PATH = str(Path(__file__).resolve().parents[1] / "corpus.json")

t0 = time.perf_counter()
print(f"Scanning: {MODULES_DIR}")
corpus = build_corpus(MODULES_DIR)
elapsed = time.perf_counter() - t0

scenes = corpus["scenes"]
skipped = corpus["skipped"]
errors = corpus["parse_errors"]

# Aggregate stats
total_entities = sum(s["entity_count"] for s in scenes)

prefab_counter: Counter[str] = Counter()
for s in scenes:
    for p in s["prefab_refs"]:
        prefab_counter[p] += 1

unique_prefabs = len(prefab_counter)
top10 = prefab_counter.most_common(10)

print(f"\nIndexed  : {len(scenes):,} scenes")
print(f"Skipped  : {len(skipped):,} dirs (no scene.xscene)")
print(f"Errors   : {len(errors):,} parse failures")
print(f"Entities : {total_entities:,} total top-level entities")
print(f"Prefabs  : {unique_prefabs:,} unique prefab names across corpus")
print(f"Runtime  : {elapsed:.1f}s")

print("\nTop 10 most-used prefabs:")
for rank, (name, count) in enumerate(top10, 1):
    print(f"  {rank:2}. {name!r}  ({count} scenes)")

print(f"\nWriting: {OUTPUT_PATH}")
save_corpus(corpus, OUTPUT_PATH)
size_mb = Path(OUTPUT_PATH).stat().st_size / (1024 * 1024)
print(f"corpus.json: {size_mb:.1f} MB")

if errors:
    print(f"\nParse failures ({len(errors)}):")
    for e in errors:
        print(f"  {e['scene_dir']}: {e['error']}")
