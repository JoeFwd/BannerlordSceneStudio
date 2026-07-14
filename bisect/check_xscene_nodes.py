"""Inspect <terrain><nodes> per-node records in each xscene."""
import xml.etree.ElementTree as ET
from collections import Counter

PATHS = [
    ("GEN", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test\scene.xscene"),
    ("015", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\battle_terrain_015\scene.xscene"),
    ("native_a", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\battle_terrain_a\scene.xscene"),
]

for label, p in PATHS:
    root = ET.parse(p).getroot()
    nodes = root.find(".//terrain/nodes")
    kids = list(nodes)
    print(f"== {label}: {len(kids)} node records ==")
    if kids:
        # unique attribute profiles
        profiles = Counter()
        for k in kids:
            profiles[tuple(sorted(k.attrib.items()))] += 1
        for prof, cnt in profiles.most_common(6):
            print(f"  x{cnt}: <{kids[0].tag}> {dict(prof)}")
        # any children of node records?
        sub = Counter(g.tag for k in kids for g in k)
        if sub:
            print("  node children:", dict(sub))
