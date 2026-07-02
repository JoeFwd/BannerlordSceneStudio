"""NMG8 navmesh prefab: loaded at runtime via Scene.ImportNavigationMeshPrefab.

    u32 file_size - 4
    'NMG8'
    u32 vertex_count
    vertex_count * { f32 x, y, z }
    u32 tri_count
    tri_count * { u32 a, b, c }
"""
from __future__ import annotations

import struct

MAGIC = b"NMG8"


def read(path: str) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    data = open(path, "rb").read()
    if data[4:8] != MAGIC:
        raise ValueError(f"{path}: bad magic {data[4:8]!r}")
    (vcount,) = struct.unpack_from("<I", data, 8)
    i = 12
    verts = [struct.unpack_from("<3f", data, i + k * 12) for k in range(vcount)]
    i += vcount * 12
    (tcount,) = struct.unpack_from("<I", data, i)
    i += 4
    tris = [struct.unpack_from("<3I", data, i + k * 12) for k in range(tcount)]
    return verts, tris


def write(path: str, verts, tris) -> None:
    body = bytearray()
    body += MAGIC
    body += struct.pack("<I", len(verts))
    for v in verts:
        body += struct.pack("<3f", *v)
    body += struct.pack("<I", len(tris))
    for t in tris:
        body += struct.pack("<3I", *t)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<I", len(body)))
        fh.write(body)
