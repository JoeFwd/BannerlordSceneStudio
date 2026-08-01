"""Build the scene corpus index over the Bannerlord Modules directory.

Writes corpus.json and corpus_terrain.npz at the repo root, then prints
summary statistics.

Usage (from repo root)::

    $env:PYTHONPATH="."; python examples/build_corpus.py
"""
import sys
import time
import os
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from blscene.corpus import build_corpus, save_corpus

    MODULES_DIR = (
        r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
    )
    OUTPUT_PATH = str(Path(__file__).resolve().parents[1] / "corpus.json")
    TERRAIN_NPZ_PATH = str(Path(__file__).resolve().parents[1] / "corpus_terrain.npz")

    t0 = time.perf_counter()
    print(f"Scanning: {MODULES_DIR}")
    corpus = build_corpus(MODULES_DIR, workers=4)
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

    scenes_with_terrain = sum(
        1 for s in scenes
        if s.get("terrain") and s["terrain"].get("terrain_grid_key") is not None
    )
    scenes_with_terrain_error = sum(
        1 for s in scenes
        if s.get("terrain") and s["terrain"].get("terrain_error") is not None
    )
    scenes_with_navmesh = sum(
        1 for s in scenes
        if s.get("navmesh") and "navmesh_error" not in s["navmesh"]
    )
    scenes_with_navmesh_error = sum(
        1 for s in scenes
        if s.get("navmesh") and "navmesh_error" in s["navmesh"]
    )

    print(f"\nIndexed       : {len(scenes):,} scenes")
    print(f"Skipped       : {len(skipped):,} dirs (no scene.xscene)")
    print(f"Errors        : {len(errors):,} parse failures")
    print(f"Entities      : {total_entities:,} total top-level entities")
    print(f"Prefabs       : {unique_prefabs:,} unique prefab names across corpus")
    print(f"Terrain grids : {scenes_with_terrain:,} scenes with grid | {scenes_with_terrain_error:,} terrain errors")
    print(f"Navmesh stats : {scenes_with_navmesh:,} scenes with navmesh | {scenes_with_navmesh_error:,} navmesh errors")
    print(f"Runtime       : {elapsed:.1f}s")

    print("\nTop 10 most-used prefabs:")
    for rank, (name, count) in enumerate(top10, 1):
        print(f"  {rank:2}. {name!r}  ({count} scenes)")

    print(f"\nWriting: {OUTPUT_PATH}")
    print(f"Writing: {TERRAIN_NPZ_PATH}")
    save_corpus(corpus, OUTPUT_PATH, terrain_npz_path=TERRAIN_NPZ_PATH)

    json_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    npz_mb = os.path.getsize(TERRAIN_NPZ_PATH) / (1024 * 1024) if os.path.exists(TERRAIN_NPZ_PATH) else 0.0
    print(f"corpus.json        : {json_mb:.1f} MB")
    print(f"corpus_terrain.npz : {npz_mb:.1f} MB")

    if errors:
        print(f"\nParse failures ({len(errors)}):")
        for e in errors:
            print(f"  {e['scene_dir']}: {e['error']}")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
