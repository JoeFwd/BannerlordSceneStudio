"""Round-trip validation against the two shipped sample scenes.

1. Original RNM1 header fields match what blnav.rnm1.write would emit
   (modulo runtime-pointer garbage).
2. NMG9 parse -> serialize is byte-identical to the decompressed original.
3. write -> read gives back the identical payload (LZ4 re-encode is valid).
4. rebuild_edges() reproduces the original edge topology (same undirected
   edge set per face).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav import nmg9, rnm1

MODULES = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
SAMPLES = {
    "empire_town_s": MODULES + r"\SandBoxCore\SceneObj\empire_town_s\navmesh.bin",
    "Main_map": MODULES + r"\SandBox\SceneObj\Main_map\navmesh.bin",
}


def check(name, path, tmpdir):
    raw = open(path, "rb").read()
    size_m8, version, pad = struct.unpack_from("<III", raw, 0x04)
    usz, size_m8b = struct.unpack_from("<QQ", raw, 0x10)
    assert size_m8 == len(raw) - 8, (name, "hdr size", size_m8, len(raw))
    assert size_m8b == len(raw) - 8, (name, "hdr size @0x18", size_m8b, len(raw))
    assert version == 3 and pad == 0, (name, version, pad)
    print(f"[{name}] hdr OK; runtime-garbage @0x20: {raw[0x20:0x30].hex(' ')}")

    payload = rnm1.read(path)
    mesh = nmg9.NavMesh.parse(payload)
    out = mesh.serialize()
    assert out == payload, (name, "NMG9 reserialize mismatch", len(out), len(payload))
    print(f"[{name}] NMG9 parse->serialize byte-identical ({len(payload):,} B), "
          f"v={len(mesh.vertices):,} e={len(mesh.edges):,} f={len(mesh.faces):,}")

    tmp = str(tmpdir / f"{name}_rt.bin")
    rnm1.write(tmp, out)
    back = rnm1.read(tmp)
    assert back == payload, (name, "container round-trip mismatch")
    print(f"[{name}] RNM1 write->read OK (recompressed {Path(tmp).stat().st_size:,} B vs orig {len(raw):,} B)")

    orig_face_edges = [
        sorted((min(mesh.edges[e].va, mesh.edges[e].vb), max(mesh.edges[e].va, mesh.edges[e].vb))
               for e in f.edge_ids)
        for f in mesh.faces
    ]
    mesh.rebuild_edges()
    rebuilt_face_edges = [
        sorted((min(mesh.edges[e].va, mesh.edges[e].vb), max(mesh.edges[e].va, mesh.edges[e].vb))
               for e in f.edge_ids)
        for f in mesh.faces
    ]
    assert rebuilt_face_edges == orig_face_edges, (name, "rebuild_edges topology mismatch")
    print(f"[{name}] rebuild_edges reproduces topology ({len(mesh.edges):,} edges)")


def main():
    tmpdir = Path(__file__).parent / "_tmp"
    tmpdir.mkdir(exist_ok=True)
    for name, path in SAMPLES.items():
        check(name, path, tmpdir)
    print("ALL ROUND-TRIP CHECKS PASSED")


if __name__ == "__main__":
    main()
