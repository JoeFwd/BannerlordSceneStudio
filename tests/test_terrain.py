"""Terrain reader validation on both sample scenes."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav.terrain import Terrain

MODULES = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
SAMPLES = {
    "empire_town_s": MODULES + r"\SandBoxCore\SceneObj\empire_town_s\terrain.bin",
    "Main_map": MODULES + r"\SandBox\SceneObj\Main_map\terrain.bin",
}

for name, path in SAMPLES.items():
    print(f"=== {name}")
    t = Terrain.load(path)
    for tag, sec in t.sections.items():
        print(f"  {tag}: {len(sec.data):,} B decompressed, {len(sec.node_offsets)} nodes, consumed {sec.consumed:,} B")
    from PIL import Image
    png = t.heightmap_node_png(0)
    img = Image.open(io.BytesIO(png))
    print(f"  HGHT node0 PNG: {img.size} mode={img.mode}")
    grid = t.heightmap_grid()
    print(f"  heightmap grid: {grid.shape} dtype={grid.dtype} min={grid.min()} max={grid.max()}")
print("TERRAIN CHECKS PASSED")
