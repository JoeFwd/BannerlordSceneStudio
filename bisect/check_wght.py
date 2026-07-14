"""Inspect WGHT + NRML node contents: native vs generated."""
import io
import struct

from blnav.terrain import Terrain

def describe(label, path):
    t = Terrain.load(path)
    print(f"== {label} ==")
    for tag in ("WGHT", "NRML"):
        sec = t.sections[tag]
        blob = sec.node(0)
        print(f"  {tag} node0: {len(blob)} bytes, head={blob[:24].hex()}")
        # try PNG-in-node like HGHT: u32 size + PNG
        if len(blob) >= 8:
            (sz,) = struct.unpack_from("<I", blob, 0)
            if blob[4:12] == b"\x89PNG\r\n\x1a\n":
                from PIL import Image
                img = Image.open(io.BytesIO(blob[4:4+sz]))
                print(f"    -> PNG {img.size} mode={img.mode}")
            else:
                print(f"    -> not u32+PNG (first u32={sz})")

describe("native battle_terrain_a", r"bisect\native\terrain.bin")
describe("generated", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test\terrain.bin")
