"""Compare <terrain> subtree structure + attrs across generated and native xscenes."""
import xml.etree.ElementTree as ET
from collections import Counter

PATHS = [
    ("GEN", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test\scene.xscene"),
    ("015", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\battle_terrain_015\scene.xscene"),
    ("native_a", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\battle_terrain_a\scene.xscene"),
]

terrains = {}
for label, p in PATHS:
    root = ET.parse(p).getroot()
    terr = root.find(".//terrain")
    terrains[label] = terr
    print(f"== {label} ==")
    c = Counter(ch.tag for ch in terr)
    print("  children:", dict(c))
    for ch in terr:
        if ch.tag != "layer":
            attrs = dict(list(ch.attrib.items())[:14])
            print(f"  <{ch.tag}> {attrs}")

print("\n== terrain attr diff (GEN vs 015 vs native_a) ==")
keys = set()
for t in terrains.values():
    keys |= set(t.attrib)
for k in sorted(keys):
    vals = {lbl: t.attrib.get(k, "<absent>") for lbl, t in terrains.items()}
    if len(set(vals.values())) > 1:
        print(f"  {k}: GEN={vals['GEN']} 015={vals['015']} a={vals['native_a']}")
