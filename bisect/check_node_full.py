"""Print full XML of node(0,0) for GEN and 015."""
import xml.etree.ElementTree as ET

PATHS = [
    ("GEN", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test\scene.xscene"),
    ("015", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\battle_terrain_015\scene.xscene"),
]

for label, p in PATHS:
    root = ET.parse(p).getroot()
    n0 = root.find(".//terrain/nodes")[0]
    print(f"== {label} ==")
    print(ET.tostring(n0, encoding="unicode"))
