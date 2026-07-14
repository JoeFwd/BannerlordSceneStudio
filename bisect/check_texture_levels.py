"""Dump <texture_levels> content for node (0,0) in each xscene."""
import xml.etree.ElementTree as ET

PATHS = [
    ("GEN", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test\scene.xscene"),
    ("015", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\battle_terrain_015\scene.xscene"),
    ("native_a", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\battle_terrain_a\scene.xscene"),
]

for label, p in PATHS:
    root = ET.parse(p).getroot()
    nodes = root.find(".//terrain/nodes")
    n0 = nodes[0]
    tl = n0.find("texture_levels")
    print(f"== {label} node(0,0) texture_levels: attrib={tl.attrib} ==")
    for ch in tl:
        print(f"  <{ch.tag}> {ch.attrib} text={ (ch.text or '').strip()[:80]!r}")
