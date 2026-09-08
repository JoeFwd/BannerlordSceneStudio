"""NMG9 navigation mesh model: parse / edit / serialize.

Layout (little-endian, decompressed payload of navmesh.bin):

    'NMG9'
    u32 vertex_count
    vertex_count * { f32 x, y, z }
    u32 edge_count
    edge_count * { i32 -1; u32 va; u32 vb; i32 -1; i32 -1; u32 0 }
    u32 face_count
    face_count * { u32 n; n*u32 vertex_ids; n*u32 edge_ids;
                   i32 g1; i32 g2; i32 g3; i32 g4; i32 g5; u8 g6 }
    u32 32; 32 * u64 zeros            (reserved footer)

Face records are NOT 4-byte aligned (21-byte tail).
The -1 slots in edge records are runtime adjacency, always -1 on disk.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAGIC = b"NMG9"
FOOTER = struct.pack("<I", 32) + b"\x00" * 256


@dataclass
class Edge:
    va: int
    vb: int


@dataclass
class Face:
    vertex_ids: list[int]
    edge_ids: list[int]
    g1: int = 2
    g2: int = 0
    g3: int = 0   # dynamic navmesh face id (SetAbilityOfFacesWithId)
    g4: int = 0
    g5: int = -1  # signed scene-level visibility mask; -1 enables all levels
    g6: int = 0   # byte flag


@dataclass
class NavMesh:
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    faces: list[Face] = field(default_factory=list)

    @classmethod
    def parse(cls, data: bytes) -> "NavMesh":
        if data[:4] != MAGIC:
            raise ValueError(f"bad magic {data[:4]!r}, expected {MAGIC!r}")
        mesh = cls()
        i = 4
        (vcount,) = struct.unpack_from("<I", data, i)
        i += 4
        mesh.vertices = [struct.unpack_from("<3f", data, i + k * 12) for k in range(vcount)]
        i += vcount * 12
        (ecount,) = struct.unpack_from("<I", data, i)
        i += 4
        for _ in range(ecount):
            f0, va, vb, f3, f4, f5 = struct.unpack_from("<i2I2iI", data, i)
            if f0 != -1 or f3 != -1 or f4 != -1 or f5 != 0:
                raise ValueError(f"unexpected edge record fields at 0x{i:X}: {(f0, f3, f4, f5)}")
            mesh.edges.append(Edge(va, vb))
            i += 24
        (fcount,) = struct.unpack_from("<I", data, i)
        i += 4
        for k in range(fcount):
            (n,) = struct.unpack_from("<I", data, i)
            if not 3 <= n <= 64:
                raise ValueError(f"face {k}: implausible vertex count {n} at 0x{i:X}")
            verts = list(struct.unpack_from(f"<{n}I", data, i + 4))
            eids = list(struct.unpack_from(f"<{n}I", data, i + 4 + n * 4))
            g1, g2, g3, g4, g5 = struct.unpack_from("<5i", data, i + 4 + n * 8)
            g6 = data[i + 4 + n * 8 + 20]
            mesh.faces.append(Face(verts, eids, g1, g2, g3, g4, g5, g6))
            i += 4 + 8 * n + 21
        if data[i:] != FOOTER:
            raise ValueError(f"unexpected footer at 0x{i:X} ({len(data) - i} bytes)")
        return mesh

    def serialize(self) -> bytes:
        out = bytearray()
        out += MAGIC
        out += struct.pack("<I", len(self.vertices))
        for v in self.vertices:
            out += struct.pack("<3f", *v)
        out += struct.pack("<I", len(self.edges))
        for e in self.edges:
            out += struct.pack("<i2I2iI", -1, e.va, e.vb, -1, -1, 0)
        out += struct.pack("<I", len(self.faces))
        for f in self.faces:
            n = len(f.vertex_ids)
            if len(f.edge_ids) != n:
                raise ValueError("face vertex/edge id count mismatch")
            out += struct.pack("<I", n)
            out += struct.pack(f"<{n}I", *f.vertex_ids)
            out += struct.pack(f"<{n}I", *f.edge_ids)
            out += struct.pack("<5i", f.g1, f.g2, f.g3, f.g4, f.g5)
            out += struct.pack("<B", f.g6)
        out += FOOTER
        return bytes(out)

    # ---- convenience -------------------------------------------------

    def stats(self) -> dict:
        from collections import Counter
        return {
            "vertices": len(self.vertices),
            "edges": len(self.edges),
            "faces": len(self.faces),
            "face_sizes": dict(Counter(len(f.vertex_ids) for f in self.faces)),
            "face_ids_g3": dict(Counter(f.g3 for f in self.faces)),
            "scene_level_masks_g5": dict(Counter(f.g5 for f in self.faces)),
        }

    def to_obj(self) -> str:
        """Wavefront OBJ (faces as polygons; Bannerlord X,Y,Z kept as-is)."""
        lines = ["# blnav NMG9 export"]
        for x, y, z in self.vertices:
            lines.append(f"v {x} {y} {z}")
        for f in self.faces:
            lines.append("f " + " ".join(str(v + 1) for v in f.vertex_ids))
        return "\n".join(lines) + "\n"

    def rebuild_edges(self) -> None:
        """Recompute the edge list and per-face edge ids from face vertex loops.

        Edge direction/order convention: for each face, boundary edge k connects
        vertex_ids[k] -> vertex_ids[(k+1) % n]. Shared edges are stored once.
        """
        edge_map: dict[tuple[int, int], int] = {}
        self.edges = []
        for f in self.faces:
            n = len(f.vertex_ids)
            f.edge_ids = []
            for k in range(n):
                a, b = f.vertex_ids[k], f.vertex_ids[(k + 1) % n]
                key = (min(a, b), max(a, b))
                if key not in edge_map:
                    edge_map[key] = len(self.edges)
                    self.edges.append(Edge(a, b))
                f.edge_ids.append(edge_map[key])
