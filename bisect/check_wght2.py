"""Fully parse WGHT node0 record stream: native vs generated."""
import io
import struct

from blnav.terrain import Terrain
from PIL import Image

def walk(label, path):
    t = Terrain.load(path)
    blob = t.sections["WGHT"].node(0)
    print(f"== {label}: WGHT node0 {len(blob)} bytes ==")
    off = 0
    i = 0
    while off < len(blob) and i < 20:
        if off + 8 > len(blob):
            print(f"  tail {len(blob)-off} bytes at {off}: {blob[off:off+16].hex()}")
            break
        a, b = struct.unpack_from("<II", blob, off)
        if blob[off+8:off+16] == b"\x89PNG\r\n\x1a\n":
            img = Image.open(io.BytesIO(blob[off+8:off+8+b]))
            print(f"  rec[{i}] @ {off}: u32a={a} png_size={b} -> PNG {img.size} {img.mode}")
            off += 8 + b
        elif blob[off+4:off+12] == b"\x89PNG\r\n\x1a\n":
            img = Image.open(io.BytesIO(blob[off+4:off+4+a]))
            print(f"  rec[{i}] @ {off}: png_size={a} -> PNG {img.size} {img.mode}")
            off += 4 + a
        else:
            print(f"  rec[{i}] @ {off}: not PNG, next16={blob[off:off+16].hex()}")
            break
        i += 1

walk("native battle_terrain_a", r"bisect\native\terrain.bin")
walk("generated", r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraScenes\SceneObj\dadg_gen_battle_test\terrain.bin")
