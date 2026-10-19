"""RNM1 container (navmesh.bin): LZ4-block-compressed NMG8/NMG9 scene payload.

    0x00 'RNM1'
    0x04 u32  file_size - 8
    0x08 u32  version (3)
    0x0C u32  pad
    0x10 u64  uncompressed_size
    0x18 u64  file_size - 8 (again)
    0x20 ...  16 bytes of runtime pointer garbage (ignored by loader;
              33 at 0x2C in empire_town_s, 0x7FF9 in Main_map)
    0x30 ...  LZ4 raw block stream
"""
from __future__ import annotations

import struct

import lz4.block

MAGIC = b"RNM1"
HEADER_SIZE = 0x30
VERSION = 3


def read(path: str) -> bytes:
    """Return decompressed NMG8/NMG9 scene payload from a navmesh.bin file."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != MAGIC:
        raise ValueError(f"{path}: bad magic {data[:4]!r}")
    (version,) = struct.unpack_from("<I", data, 0x08)
    if version != VERSION:
        raise ValueError(f"{path}: unsupported RNM1 version {version}")
    (usz,) = struct.unpack_from("<Q", data, 0x10)
    return lz4.block.decompress(data[HEADER_SIZE:], uncompressed_size=usz)


def write(path: str, payload: bytes) -> None:
    """Compress a scene navmesh payload and write a navmesh.bin container."""
    comp = lz4.block.compress(payload, mode="high_compression", store_size=False)
    total = HEADER_SIZE + len(comp)
    hdr = struct.pack(
        "<4sIIIQQQII",
        MAGIC,
        total - 8,
        VERSION,
        0,
        len(payload),
        total - 8,
        0,
        0,
        33,
    )
    assert len(hdr) == HEADER_SIZE
    with open(path, "wb") as fh:
        fh.write(hdr)
        fh.write(comp)
