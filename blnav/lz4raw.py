"""Minimal pure-Python LZ4 raw-block decoder.

Unlike lz4.block.decompress, this tolerates trailing input: it decodes
sequences until the output reaches the expected size and reports how many
input bytes were consumed. Used to find exact stream boundaries inside
terrain.bin sections; hot paths should use lz4.block with the discovered
boundaries.
"""
from __future__ import annotations


def decompress_prefix(data: bytes, expected_size: int) -> tuple[bytes, int]:
    """Decode an LZ4 raw block from the start of *data*.

    Returns (output, input_bytes_consumed). Stops as soon as the output
    reaches expected_size.
    """
    out = bytearray()
    i = 0
    n = len(data)
    while len(out) < expected_size:
        if i >= n:
            raise ValueError(f"input exhausted at out={len(out)}/{expected_size}")
        token = data[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = data[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += data[i : i + lit]
        i += lit
        if len(out) >= expected_size:
            break
        if i + 2 > n:
            raise ValueError(f"truncated offset at out={len(out)}/{expected_size}")
        offset = data[i] | (data[i + 1] << 8)
        i += 2
        if offset == 0:
            raise ValueError(f"zero match offset at out={len(out)}")
        mlen = token & 15
        if mlen == 15:
            while True:
                b = data[i]
                i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(out) - offset
        if start < 0:
            raise ValueError(f"match offset {offset} before start at out={len(out)}")
        for _ in range(mlen):
            out.append(out[start])
            start += 1
    return bytes(out), i
