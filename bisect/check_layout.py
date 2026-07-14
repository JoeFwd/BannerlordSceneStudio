"""Compare node layout + content sanity of native vs generated terrain.bin."""
import io
import struct

from blnav.terrain import Terrain

for label, path in [
    ("native battle_terrain_a", r"bisect\native\terrain.bin"),
    ("generated", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test\terrain.bin"),
]:
    t = Terrain.load(path)
    print(f"== {label} ==")
    for tag, sec in t.sections.items():
        print(f"  {tag}: nodes={len(sec.node_offsets)} usz={len(sec.data)}")
    # HGHT node PNG dims
    from PIL import Image
    png = t.heightmap_node_png(0)
    img = Image.open(io.BytesIO(png))
    print(f"  HGHT node0 PNG: {img.size} mode={img.mode}")
    # PHYM node 0 header
    blob = t.sections["PHYM"].node(0)
    z, cells = struct.unpack_from("<II", blob, 0)
    print(f"  PHYM node0: lead={z} cells={cells} (res={int(cells**0.5)}) node_bytes={len(blob)}")
    # height range check via full grid
    grid = t.heightmap_grid()
    print(f"  grid shape={grid.shape} u16 min={grid.min()} max={grid.max()}")
