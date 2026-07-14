"""Survey native scenes: xscene node_size vs terrain.bin per-node HGHT resolution.

Fast prober: decompresses only the first bytes of the HGHT stream (PNG IHDR).
"""
import glob
import re
import struct

from blnav import lz4raw

GAME = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"


def probe_res(path: str) -> int:
    data = open(path, "rb").read()
    if data[:8] != b"ZGR6RTRN":
        raise ValueError("bad magic")
    j = 0x0C
    for _ in range(5):
        tag = data[j : j + 4].decode()
        count, off, csz, usz = struct.unpack_from("<4I", data, j + 4)
        j += 20
        if tag != "HGHT":
            continue
        k = off
        table = []
        while True:
            (v,) = struct.unpack_from("<I", data, k)
            if (table and v <= table[-1]) or (not table and v != 0):
                break
            table.append(v)
            k += 4
        # stream header then 8B garbage then LZ4
        body = k + 32 + 8
        # need node0 payload start (offset 0) + 4 (png size) + 16 (up to IHDR w) + 8
        out, _ = lz4raw.decompress_prefix(data[body:], 4 + 33)
        png = out[4:]
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        w = struct.unpack(">I", png[16:20])[0]
        return w
    raise ValueError("no HGHT")


rows = []
for p in sorted(glob.glob(GAME + r"\Modules\*\SceneObj\*\terrain.bin")):
    xs = p.replace("terrain.bin", "scene.xscene")
    try:
        head = open(xs, encoding="utf-8", errors="ignore").read(20000)
        m = re.search(r'node_size="([\d.]+)"', head)
        if not m:
            continue
        res = probe_res(p)
        name = p.split("SceneObj\\")[1].split("\\")[0]
        mod = p.split("Modules\\")[1].split("\\")[0]
        rows.append((float(m.group(1)), res, f"{mod}/{name}"))
    except Exception:
        pass

for ns, res, name in sorted(rows):
    print(f"node_size={ns:7.1f} res={res:4d} ratio={(ns/(res-1)):.5f} {name}")
print(f"\n{len(rows)} scenes probed")
