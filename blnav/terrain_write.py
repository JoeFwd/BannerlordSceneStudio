"""terrain.bin (ZGR6) writer and terrain generator.

Section payload formats (discovered from vanilla samples):

MIDX (no node table, single stream):
    4 x [u32 png_sz, PNG(nx*256 x ny*256, mode=L, all-255)]
    One PNG per LOD level (always 4 LODs). Pixel value 255 = material index 0.

HGHT (per-node):
    [u32 png_sz, PNG(129x129, mode=I;16, 16-bit grayscale heights)]
    u32 is byte size of PNG data. Nodes in row-major order (left→right, top→bottom).

NRML (per-node):
    [u32 png_sz, PNG(129x129, mode=RGBA, uint8)]
    R = clip(round(127 - dh_dx / 11.75), 0, 255)
    G = clip(round(127 - dh_dy / 11.75), 0, 255)
    B = 63  (constant)
    A = 0   (constant)
    where dh_dx/dh_dy are the central-difference gradients of the raw uint16 heights.

WGHT (per-node):
    Fixed array of 16 material slots. Each slot: u32 flag.
    flag=1: followed by [u32 png_sz, PNG(NxN mode=L, weight 0-255)].
    flag=0: empty slot, nothing follows.
    Every vanilla node has exactly 16 slots (battle_terrain_a: 6 maps + 10 empty;
    vlandia_town_c: 8 maps + 8 empty). The engine reads all 16 flags per node —
    fewer slots makes it read past the node buffer (access violation on load).

PHYM (per-node):
    [u32=0, u32=res², 24B material_header, res²*4 uint8 cell data]
    Total fixed size for 129-res: 8 + 24 + 129*129*4 = 66596 bytes.
    Cell data: res² cells × 4 channels per cell, each channel = uint8 physics
    material index (0-indexed into xscene <layer> list).
    material_header: 24 bytes, each byte = dominant material index for a sub-block
    of the node (same range as cell bytes). Native formula: material index N maps
    directly to byte value N. For uniform single-material terrain, all 24 header
    bytes and all cell bytes equal the material's layer index.
    Height decoding (HGHT): world_h = min_height + u16/65535 * (max_height - min_height)
    where min_height/max_height come from the xscene <terrain> element.

Stream header observations:
    runtime_ptr: NOT constant (varies per file, nonzero in some sections of Coventry).
    ptr_low / tag: NOT constant (differ between vlandia 0xa628e420/0x7ffb and
                   Coventry 0xed7b7a90/0x7ffa). These are runtime garbage — write zeros.
    mode = 3 (constant), pad = 0 (constant).
"""
from __future__ import annotations

import io
import struct
from typing import Sequence

import lz4.block
import numpy as np
from PIL import Image

from .terrain import MAGIC, TAGS, Section, Terrain
from . import lz4raw

_NRML_SCALE = 11.75  # empirical: minimises mean-absolute-error vs vanilla


# ---------------------------------------------------------------------------
# LZ4 encode / decode helpers
# ---------------------------------------------------------------------------

def _lz4_compress(data: bytes) -> bytes:
    """Compress *data* as a single raw LZ4 block (no size prefix).

    Uses LZ4 high-compression level 12, which matches the compression ratio
    and byte patterns produced by the native Bannerlord terrain writer.
    The default fast mode produces oversized blocks for PNG-heavy sections
    (HGHT/NRML) because it finds zero back-references in already-compressed
    PNG payloads; the engine may reject or crash on blocks larger than
    inner_usz + a small slack.
    """
    return lz4.block.compress(data, store_size=False,
                              mode='high_compression', compression=12)


def _lz4_verify(compressed: bytes, expected: bytes) -> None:
    """Assert that our LZ4 block round-trips correctly via lz4raw."""
    out, _ = lz4raw.decompress_prefix(compressed, len(expected))
    assert out == expected, "LZ4 round-trip mismatch"


# ---------------------------------------------------------------------------
# Stream / section serialisation
# ---------------------------------------------------------------------------

def _stream_header(usz: int, csz: int) -> bytes:
    """32B stream header: {u32 mode=3, u32 pad=0, u64 usz, u64 csz, u64 runtime_ptr=0}."""
    return struct.pack("<IIQQQ", 3, 0, usz, csz, 0)


def _runtime_garbage() -> bytes:
    """8B runtime garbage written as zeros (vanilla values vary per run)."""
    return b"\x00" * 8


def _build_section(node_offsets: list[int], data: bytes) -> bytes:
    """Compress *data*, build the full on-disk section bytes.

    Returns: optional node-offset table + 32B stream header + 8B garbage + LZ4 block.
    """
    compressed = _lz4_compress(data)
    _lz4_verify(compressed, data)

    # csz counts from the start of the stream header (native convention):
    # 32 bytes (stream header) + 8 bytes (runtime garbage) + len(LZ4 block).
    csz = len(compressed) + 40
    out = io.BytesIO()
    for off in node_offsets:
        out.write(struct.pack("<I", off))
    out.write(_stream_header(len(data), csz))
    out.write(_runtime_garbage())
    out.write(compressed)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Public: write_terrain
# ---------------------------------------------------------------------------

def write_terrain(terrain: Terrain, path: str) -> None:
    """Serialise *terrain* to *path* in ZGR6 format.

    Round-trip guarantee: Terrain.load of the written file yields byte-equal
    section .data and equal .node_offsets for all 5 sections.
    Compressed bytes may differ from vanilla (same decompressed content).
    """
    # Build each section blob
    section_blobs: dict[str, bytes] = {}
    for tag in TAGS:
        sec = terrain.sections[tag]
        blob = _build_section(sec.node_offsets, sec.data)
        section_blobs[tag] = blob

    # Build file
    out = io.BytesIO()
    out.write(MAGIC)
    out.write(struct.pack("<I", 2))  # version

    # Descriptor table (5 × 20 bytes)
    # We need to know the offsets, so compute them first.
    # File layout: 8B magic + 4B version + 5*20B descriptors + sections
    header_size = 8 + 4 + 5 * 20  # = 112 = 0x70
    offsets: list[int] = []
    pos = header_size
    for tag in TAGS:
        offsets.append(pos)
        pos += len(section_blobs[tag])

    for i, tag in enumerate(TAGS):
        sec = terrain.sections[tag]
        off = offsets[i]
        # Descriptor: 4-char tag + u32 count=1 + u32 off + u32 csz + u32 usz
        # csz/usz here are the *outer* sizes (section blob compressed / uncompressed).
        # From the reader: count=1 is always 1. csz/usz in the descriptor are the
        # sizes used at the descriptor level — but the reader ignores them (uses the
        # inner stream header instead). Write them as 0 to avoid confusion... actually
        # vanilla writes real values. We keep them for symmetry (reader ignores them).
        blob = section_blobs[tag]
        # The inner stream header is at offset (4*len(node_offsets)) into the blob.
        inner_off = 4 * len(sec.node_offsets)
        _, _, inner_usz, inner_csz, _ = struct.unpack_from("<IIQQQ", blob, inner_off)
        out.write(tag.encode())
        out.write(struct.pack("<4I", 1, off, inner_csz, inner_usz))

    # Section bodies
    for tag in TAGS:
        out.write(section_blobs[tag])

    with open(path, "wb") as f:
        f.write(out.getvalue())


# ---------------------------------------------------------------------------
# PNG helpers
# ---------------------------------------------------------------------------

def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=9, dpi=(72, 72))
    return buf.getvalue()


def _heights_to_uint16(
    heights_m: np.ndarray,
    min_h: float,
    max_h: float,
) -> np.ndarray:
    """Float32 world-metre heights → uint16 using native convention.

    Encoding: u16 = round(clip((h - min_h) / (max_h - min_h), 0, 1) * 65535)
    Decoding: h   = min_h + u16 / 65535 * (max_h - min_h)

    min_h / max_h must match the values written to the xscene <terrain> element.
    """
    span = max_h - min_h
    if span == 0:
        return np.zeros_like(heights_m, dtype=np.uint16)
    normed = (heights_m - min_h) / span
    normed = np.clip(normed, 0.0, 1.0)
    return (normed * 65535.0 + 0.5).astype(np.uint16)


# ---------------------------------------------------------------------------
# Per-section node payload builders
# ---------------------------------------------------------------------------

def _build_hght_node(tile_u16: np.ndarray) -> bytes:
    """Build one HGHT node payload: u32 png_size + PNG(129x129 uint16 gray)."""
    assert tile_u16.shape == (129, 129) and tile_u16.dtype == np.uint16
    # PIL I;16 mode = 16-bit little-endian grayscale
    img = Image.fromarray(tile_u16, mode="I;16")
    png = _png_bytes(img)
    return struct.pack("<I", len(png)) + png


def _build_nrml_node(tile_u16: np.ndarray) -> bytes:
    """Build one NRML node payload: u32 png_size + PNG(129x129 RGBA uint8).

    Formula: R = clip(round(127 - dh_dx/K), 0, 255)
             G = clip(round(127 - dh_dy/K), 0, 255)
             B = 63  (constant)
             A = 0   (constant)
    """
    h = tile_u16.astype(np.float32)
    dh_dy, dh_dx = np.gradient(h)
    K = _NRML_SCALE
    R = np.clip(np.round(127 - dh_dx / K), 0, 255).astype(np.uint8)
    G = np.clip(np.round(127 - dh_dy / K), 0, 255).astype(np.uint8)
    B = np.full_like(R, 63)
    A = np.zeros_like(R)
    rgba = np.stack([R, G, B, A], axis=-1)
    img = Image.fromarray(rgba, mode="RGBA")
    png = _png_bytes(img)
    return struct.pack("<I", len(png)) + png


def _build_wght_node_uniform() -> bytes:
    """Build one WGHT node payload for uniform first material (weight=255 everywhere).

    Slot 0 holds the weight map; the remaining 15 of the fixed 16 slots are empty.
    """
    arr = np.full((129, 129), 255, dtype=np.uint8)
    img = Image.fromarray(arr, mode="L")
    png = _png_bytes(img)
    return struct.pack("<II", 1, len(png)) + png + struct.pack("<I", 0) * 15


def _build_wght_node_multi(slot_tiles: dict[int, np.ndarray]) -> bytes:
    """Build one WGHT node payload from a mapping of slot_index -> 129x129 uint8 weight.

    The fixed 16-slot table is always emitted: present slots (a u8 weight tile,
    stored 0-255) get flag=1 + [u32 png_size, L-mode PNG]; the rest get flag=0.
    Writing all 16 slot flags is mandatory (native format; fewer = load crash).
    """
    parts: list[bytes] = []
    for slot in range(16):
        tile = slot_tiles.get(slot)
        if tile is None:
            parts.append(struct.pack("<I", 0))
            continue
        assert tile.shape == (129, 129) and tile.dtype == np.uint8
        img = Image.fromarray(tile, mode="L")
        png = _png_bytes(img)
        parts.append(struct.pack("<II", 1, len(png)) + png)
    return b"".join(parts)


def _build_phym_node_uniform(material_idx: int = 0) -> bytes:
    """Build one PHYM node payload for a uniform single-material terrain.

    Native convention: each cell byte = layer index (0 = first xscene layer).
    The 24-byte sub-header holds the dominant material index for each sub-block.
    For material index 0, all bytes are 0 (confirmed against vlandia_town_c and
    battle_terrain_a vanilla samples).

    Layout: [u32=0][u32=16641][24B material_header][129*129*4 cell bytes]
    Total: 66596 bytes.
    """
    res = 129
    # 24-byte sub-header: per-block dominant material ID (same byte value as cells)
    mat_byte = material_idx & 0xFF
    header = struct.pack("<II", 0, res * res) + bytes([mat_byte] * 24)
    # res² cells × 4 channels, each channel = material_idx
    cell_data = bytes([mat_byte]) * (res * res * 4)
    return header + cell_data


def _build_midx_section(nx: int, ny: int) -> bytes:
    """Build the full MIDX section decompressed data.

    Format: 4 × [u32 png_sz, PNG(nx*256 x ny*256, mode=L, all-255)]
    One PNG per LOD level (4 LODs). Material index 0 = value 255.
    """
    w, h = nx * 256, ny * 256
    arr = np.full((h, w), 255, dtype=np.uint8)
    img = Image.fromarray(arr, mode="L")
    png = _png_bytes(img)
    block = struct.pack("<I", len(png)) + png
    return block * 4  # same PNG for all 4 LODs


# ---------------------------------------------------------------------------
# Public: generate_terrain
# ---------------------------------------------------------------------------

def _normalise_layer_weights(
    layer_weights: dict[int, np.ndarray],
    shape: tuple[int, int],
) -> dict[int, np.ndarray]:
    """Validate + convert layer weights to float32 arrays in [0, 1].

    Accepts float (0-1) or uint8 (0-255) arrays; uint8 is scaled to [0, 1].
    Every array must match *shape* (the full height grid, ny*128+1, nx*128+1).
    """
    out: dict[int, np.ndarray] = {}
    for layer, w in layer_weights.items():
        w = np.asarray(w)
        if w.shape != shape:
            raise ValueError(
                f"layer_weights[{layer}] shape {w.shape} != {shape}"
            )
        if w.dtype == np.uint8:
            wf = w.astype(np.float32) / 255.0
        else:
            wf = w.astype(np.float32)
        out[layer] = np.clip(wf, 0.0, 1.0)
    return out


def generate_terrain(
    heights: np.ndarray,
    node_dim: tuple[int, int] = (1, 1),
    min_height: float = 0.0,
    max_height: float = 100.0,
    layer_weights: dict[int, np.ndarray] | None = None,
) -> Terrain:
    """Generate a Terrain from a float32 world-metre height array.

    Args:
        heights: float32 array of shape (H, W) in world metres.
            Must span exactly (ny*128+1) rows × (nx*128+1) columns, where
            node_dim = (nx, ny), to accommodate 1-pixel overlap between nodes.
        node_dim: (nx, ny) number of nodes in X and Y directions.
        min_height: world-metre minimum used for uint16 encoding.
        max_height: world-metre maximum used for uint16 encoding.
        layer_weights: optional {layer_index: full-map weight array}.  Each array
            has the same shape as *heights* and holds a per-pixel blend weight
            (float 0-1 or uint8 0-255) for that terrain layer.  Layer 0 defaults
            to the base: if omitted it is synthesised as (1 - sum of others),
            clipped to [0, 1].  When None (default), the legacy single-layer path
            runs and output is byte-identical to before.

    Returns:
        A fully populated Terrain with all 5 sections.
    """
    nx, ny = node_dim
    n_nodes = nx * ny
    expected_h = ny * 128 + 1
    expected_w = nx * 128 + 1
    if heights.shape != (expected_h, expected_w):
        raise ValueError(
            f"heights shape {heights.shape} != ({expected_h}, {expected_w}) "
            f"for node_dim={node_dim}"
        )

    # Convert to uint16 grid
    grid_u16 = _heights_to_uint16(heights, min_height, max_height)

    # Extract 129×129 tiles with 1-pixel overlap
    tiles: list[np.ndarray] = []
    for gy in range(ny):
        for gx in range(nx):
            row0 = gy * 128
            col0 = gx * 128
            tile = grid_u16[row0 : row0 + 129, col0 : col0 + 129]
            tiles.append(tile)

    # HGHT section
    hght_nodes: list[bytes] = [_build_hght_node(t) for t in tiles]
    hght_offsets = _offsets(hght_nodes)
    hght_data = b"".join(hght_nodes)

    # NRML section
    nrml_nodes: list[bytes] = [_build_nrml_node(t) for t in tiles]
    nrml_offsets = _offsets(nrml_nodes)
    nrml_data = b"".join(nrml_nodes)

    if layer_weights is None:
        # ---- Legacy single-layer path (byte-identical to previous output) ----
        wght_node = _build_wght_node_uniform()
        wght_nodes = [wght_node] * n_nodes
        wght_offsets = _offsets(wght_nodes)
        wght_data = b"".join(wght_nodes)

        phym_node = _build_phym_node_uniform()
        phym_nodes = [phym_node] * n_nodes
        phym_offsets = _offsets(phym_nodes)
        phym_data = b"".join(phym_nodes)
    else:
        # ---- Multi-layer path ----
        weights = _normalise_layer_weights(layer_weights, heights.shape)
        # Layer 0 defaults to the base (1 - sum of others) if not supplied.
        if 0 not in weights:
            other = np.zeros(heights.shape, dtype=np.float32)
            for layer, w in weights.items():
                if layer != 0:
                    other += w
            weights[0] = np.clip(1.0 - other, 0.0, 1.0)
        layer_ids = sorted(weights)  # ascending layer index

        # PHYM stays uniform material 0.  PHYM cell values are NOT the dominant
        # WGHT layer (native correlation ~26%, chance level) — the encoding is
        # engine-internal and unknown; writing argmax-layer indices crashes the
        # loader at TaleWorlds.Native.dll+0x441700.  Uniform 0 is proven to load
        # with multi-slot WGHT (in-game validated 2026-07-15); the only cost is
        # default footstep/impact physics on non-base layers.
        phym_uniform = _build_phym_node_uniform()

        wght_nodes = []
        phym_nodes = []
        for gy in range(ny):
            for gx in range(nx):
                r0, c0 = gy * 128, gx * 128
                sl = (slice(r0, r0 + 129), slice(c0, c0 + 129))
                slot_tiles: dict[int, np.ndarray] = {}
                for layer in layer_ids:
                    tile = (weights[layer][sl] * 255.0 + 0.5).astype(np.uint8)
                    # A slot is only present when the layer contributes weight in
                    # this node — keeps WGHT-present slots consistent with the
                    # per-node layer-usage bitmask written to the xscene.
                    if bool((tile > 0).any()):
                        slot_tiles[layer] = tile
                if not slot_tiles:  # fully-zero node: keep base slot 0 present
                    slot_tiles[0] = np.zeros((129, 129), dtype=np.uint8)
                wght_nodes.append(_build_wght_node_multi(slot_tiles))
                phym_nodes.append(phym_uniform)
        wght_offsets = _offsets(wght_nodes)
        wght_data = b"".join(wght_nodes)
        phym_offsets = _offsets(phym_nodes)
        phym_data = b"".join(phym_nodes)

    # MIDX section (no node table)
    midx_data = _build_midx_section(nx, ny)

    t = Terrain()
    t.sections["MIDX"] = Section("MIDX", [], midx_data, 0)
    t.sections["HGHT"] = Section("HGHT", hght_offsets, hght_data, 0)
    t.sections["NRML"] = Section("NRML", nrml_offsets, nrml_data, 0)
    t.sections["WGHT"] = Section("WGHT", wght_offsets, wght_data, 0)
    t.sections["PHYM"] = Section("PHYM", phym_offsets, phym_data, 0)
    return t


def _offsets(nodes: list[bytes]) -> list[int]:
    """Compute cumulative byte offsets for a node list."""
    offs = [0]
    for node in nodes[:-1]:
        offs.append(offs[-1] + len(node))
    return offs


def node_layer_usage(
    layer_weights: dict[int, np.ndarray] | None,
    heights_shape: tuple[int, int],
    node_dim: tuple[int, int],
    *,
    threshold: float = 0.5 / 255.0,
) -> dict[tuple[int, int], list[int]]:
    """Compute the set of layers actually used per node, keyed by (idx, idy).

    A layer counts as used in a node if its (0-255-quantised) weight is nonzero
    anywhere in that node's 129x129 tile — this mirrors the WGHT slots the writer
    emits (present slot ⟺ any nonzero weight) and drives the xscene per-node
    seasonal masks + weightmap_levels.

    Returns {(idx, idy): [sorted layer indices]}.  For the single-layer default
    (layer_weights is None) every node maps to [0].
    """
    nx, ny = node_dim
    if layer_weights is None:
        return {(idx, idy): [0] for idx in range(nx) for idy in range(ny)}

    weights = _normalise_layer_weights(layer_weights, heights_shape)
    if 0 not in weights:
        other = np.zeros(heights_shape, dtype=np.float32)
        for layer, w in weights.items():
            if layer != 0:
                other += w
        weights[0] = np.clip(1.0 - other, 0.0, 1.0)
    layer_ids = sorted(weights)

    usage: dict[tuple[int, int], list[int]] = {}
    for idx in range(nx):
        for idy in range(ny):
            r0, c0 = idy * 128, idx * 128
            sl = (slice(r0, r0 + 129), slice(c0, c0 + 129))
            used = [l for l in layer_ids if bool((weights[l][sl] > threshold).any())]
            if not used:
                used = [0]
            usage[(idx, idy)] = used
    return usage
