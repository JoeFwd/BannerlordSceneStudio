"""terrain.bin (ZGR6) reader.

    0x00 'ZGR6' 'RTRN' u32 version=2
    0x0C 5 section descriptors, 20 B each:
         [4-char tag][u32 count=1][u32 off][u32 csz][u32 usz]
         tags: MIDX, HGHT, NRML, WGHT, PHYM
    section at off:
         optional node offset table (u32s, strictly increasing, starts 0;
         offsets into the UNCOMPRESSED stream)
         32 B header {u32 mode=3, u32 pad, u64 usz, u64 csz, u64 runtime_ptr}
         8 B  runtime garbage {u32 ptr_low, u32 tag}
         LZ4 raw block stream

    HGHT nodes decode to {u32 png_size, PNG bytes} — 129x129 16-bit grayscale.
    MIDX decodes to a single PNG.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field

from . import lz4raw

MAGIC = b"ZGR6RTRN"
TAGS = ("MIDX", "HGHT", "NRML", "WGHT", "PHYM")


@dataclass
class Section:
    tag: str
    node_offsets: list[int]          # into decompressed stream; empty if none
    data: bytes                      # decompressed stream
    consumed: int                    # compressed bytes consumed (for info)

    def node(self, idx: int) -> bytes:
        if not self.node_offsets:
            raise ValueError(f"{self.tag}: no node table")
        end = (
            self.node_offsets[idx + 1]
            if idx + 1 < len(self.node_offsets)
            else len(self.data)
        )
        return self.data[self.node_offsets[idx] : end]


@dataclass
class Terrain:
    sections: dict[str, Section] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "Terrain":
        data = open(path, "rb").read()
        if data[:8] != MAGIC:
            raise ValueError(f"{path}: bad magic {data[:8]!r}")
        t = cls()
        j = 0x0C
        for _ in range(5):
            tag = data[j : j + 4].decode()
            count, off, csz, usz = struct.unpack_from("<4I", data, j + 4)
            j += 20
            if count != 1:
                raise ValueError(f"{tag}: unexpected count {count}")
            k = off
            table: list[int] = []
            while True:
                (v,) = struct.unpack_from("<I", data, k)
                if (table and v <= table[-1]) or (not table and v != 0):
                    break
                table.append(v)
                k += 4
            mode, _pad, inner_usz, _inner_csz, _ptr = struct.unpack_from("<IIQQQ", data, k)
            if mode != 3:
                raise ValueError(f"{tag}: unexpected stream mode {mode}")
            body = k + 32 + 8  # skip {ptr_low, tag} runtime garbage
            out, consumed = lz4raw.decompress_prefix(data[body:], inner_usz)
            t.sections[tag] = Section(tag, table, out, consumed)
        return t

    # ---- heightmap ----------------------------------------------------

    def heightmap_node_png(self, node_idx: int) -> bytes:
        """Raw PNG bytes of one 129x129 16-bit heightmap node."""
        blob = self.sections["HGHT"].node(node_idx)
        (png_size,) = struct.unpack_from("<I", blob, 0)
        return blob[4 : 4 + png_size]

    def heightmap_grid(self, node_dim: tuple[int, int] | None = None):
        """Assemble all HGHT nodes into one uint16 numpy array.

        Nodes are 129x129 with 1-pixel overlap (128 unique + shared border).
        node_dim (nx, ny): if None, assumes a square grid.
        """
        import numpy as np
        from PIL import Image

        sec = self.sections["HGHT"]
        n = len(sec.node_offsets)
        if node_dim is None:
            side = int(round(n ** 0.5))
            if side * side != n:
                raise ValueError(f"{n} nodes is not square; pass node_dim")
            node_dim = (side, side)
        nx, ny = node_dim
        tiles = []
        for i in range(n):
            img = Image.open(io.BytesIO(self.heightmap_node_png(i)))
            tiles.append(np.array(img))
        th, tw = tiles[0].shape
        grid = np.zeros(((th - 1) * ny + 1, (tw - 1) * nx + 1), dtype=tiles[0].dtype)
        for i, tile in enumerate(tiles):
            gx, gy = i % nx, i // nx
            grid[gy * (th - 1) : gy * (th - 1) + th, gx * (tw - 1) : gx * (tw - 1) + tw] = tile
        return grid
