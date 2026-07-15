"""Tests for blnav.terrain_write: round-trip and generation."""
import io
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav.terrain import Terrain
from blnav.terrain_write import generate_terrain, write_terrain, node_layer_usage

BT015 = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\SandBoxCore\SceneObj\battle_terrain_015\terrain.bin"
)

VLANDIA = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\SandBoxCore\SceneObj\vlandia_town_c\terrain.bin"
)
COVENTRY = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\DellarteDellaGuerraScenes\SceneObj\Coventry\terrain.bin"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _roundtrip(src_path: str) -> tuple[Terrain, Terrain]:
    """Load vanilla, write to tmp, reload, return (original, reloaded)."""
    original = Terrain.load(src_path)
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        tmp_path = f.name
    write_terrain(original, tmp_path)
    reloaded = Terrain.load(tmp_path)
    return original, reloaded


def _assert_sections_equal(orig: Terrain, reloaded: Terrain) -> None:
    """Assert that all 5 sections have equal data and node_offsets."""
    for tag in ("MIDX", "HGHT", "NRML", "WGHT", "PHYM"):
        o = orig.sections[tag]
        r = reloaded.sections[tag]
        assert o.node_offsets == r.node_offsets, f"{tag}: node_offsets differ"
        assert o.data == r.data, f"{tag}: decompressed data differs (len {len(o.data)} vs {len(r.data)})"


# ---------------------------------------------------------------------------
# (a) Round-trip tests on vanilla samples
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not Path(VLANDIA).exists(), reason="vlandia sample not available")
def test_roundtrip_vlandia():
    orig, reloaded = _roundtrip(VLANDIA)
    _assert_sections_equal(orig, reloaded)


@pytest.mark.skipif(not Path(COVENTRY).exists(), reason="Coventry sample not available")
def test_roundtrip_coventry():
    orig, reloaded = _roundtrip(COVENTRY)
    _assert_sections_equal(orig, reloaded)


# ---------------------------------------------------------------------------
# (b) generate_terrain tests
# ---------------------------------------------------------------------------

def _make_flat_heights(nx: int, ny: int, value_m: float = 50.0) -> np.ndarray:
    H = ny * 128 + 1
    W = nx * 128 + 1
    return np.full((H, W), value_m, dtype=np.float32)


def _make_sloped_heights(nx: int, ny: int, min_m: float = 0.0, max_m: float = 100.0) -> np.ndarray:
    H = ny * 128 + 1
    W = nx * 128 + 1
    xs = np.linspace(min_m, max_m, W, dtype=np.float32)
    ys = np.linspace(min_m, max_m, H, dtype=np.float32)
    return xs[np.newaxis, :] * 0.5 + ys[:, np.newaxis] * 0.5


def _check_terrain_parses(t: Terrain) -> None:
    """Assert all 5 sections exist and HGHT nodes parse as PNG."""
    assert set(t.sections.keys()) == {"MIDX", "HGHT", "NRML", "WGHT", "PHYM"}
    hght = t.sections["HGHT"]
    assert len(hght.node_offsets) > 0
    for i in range(len(hght.node_offsets)):
        blob = hght.node(i)
        (png_sz,) = struct.unpack_from("<I", blob, 0)
        img = Image.open(io.BytesIO(blob[4 : 4 + png_sz]))
        assert img.size == (129, 129)


def _check_heights_roundtrip(
    heights_in: np.ndarray,
    node_dim: tuple[int, int],
    min_h: float,
    max_h: float,
    tmp_path: str,
) -> None:
    """Write + reload + decode heights, check within 1/65535 quantisation."""
    t = generate_terrain(heights_in, node_dim=node_dim, min_height=min_h, max_height=max_h)
    write_terrain(t, tmp_path)
    t2 = Terrain.load(tmp_path)

    # Reassemble heightmap from reloaded terrain
    from blnav.xscene import TerrainParams
    params = TerrainParams(
        node_dim_x=node_dim[0],
        node_dim_y=node_dim[1],
        node_size=128.0,
        min_height=min_h,
        max_height=max_h,
    )
    grid = t2.heightmap_grid(node_dim)
    heights_out = params.decode_heights(grid)

    tol = (max_h - min_h) / 65535.0
    diff = np.abs(heights_out - heights_in)
    assert diff.max() <= tol + 1e-5, (
        f"Height max error {diff.max():.6f} > tolerance {tol:.6f}"
    )


@pytest.fixture
def tmp_bin(tmp_path):
    return str(tmp_path / "test.bin")


def test_generate_flat_6x6(tmp_bin):
    heights = _make_flat_heights(6, 6, value_m=50.0)
    t = generate_terrain(heights, node_dim=(6, 6), min_height=0.0, max_height=100.0)
    _check_terrain_parses(t)
    assert len(t.sections["HGHT"].node_offsets) == 36


def test_generate_sloped_6x6(tmp_bin):
    heights = _make_sloped_heights(6, 6, min_m=0.0, max_m=100.0)
    t = generate_terrain(heights, node_dim=(6, 6), min_height=0.0, max_height=100.0)
    _check_terrain_parses(t)


def test_generate_write_reload_flat_6x6(tmp_bin):
    heights = _make_flat_heights(6, 6, value_m=50.0)
    _check_heights_roundtrip(heights, (6, 6), 0.0, 100.0, tmp_bin)


def test_generate_write_reload_sloped_6x6(tmp_bin):
    heights = _make_sloped_heights(6, 6, 0.0, 200.0)
    _check_heights_roundtrip(heights, (6, 6), 0.0, 200.0, tmp_bin)


def test_generate_all_sections_parse_6x6(tmp_bin):
    """After write+reload, all 5 sections should have correct node counts."""
    nx, ny = 6, 6
    heights = _make_sloped_heights(nx, ny)
    t = generate_terrain(heights, node_dim=(nx, ny), min_height=0.0, max_height=100.0)
    write_terrain(t, tmp_bin)
    t2 = Terrain.load(tmp_bin)

    n = nx * ny
    assert len(t2.sections["MIDX"].node_offsets) == 0  # no node table for MIDX
    assert len(t2.sections["HGHT"].node_offsets) == n
    assert len(t2.sections["NRML"].node_offsets) == n
    assert len(t2.sections["WGHT"].node_offsets) == n
    assert len(t2.sections["PHYM"].node_offsets) == n

    # PHYM nodes should each be 66596 bytes
    phym = t2.sections["PHYM"]
    for i in range(n):
        blob = phym.node(i)
        assert len(blob) == 66596, f"PHYM node[{i}] len={len(blob)} != 66596"

    # WGHT node 0 must contain exactly 16 slot tokens (fixed 16-slot format).
    # Walk: read u32 flag; flag=1 → read u32 png_size + skip png bytes; flag=0 → empty.
    # Total tokens must be 16 and the walk must consume the node exactly.
    wght = t2.sections["WGHT"]
    blob = wght.node(0)
    off = 0
    tokens = 0
    while off < len(blob):
        assert off + 4 <= len(blob), f"WGHT node0: ran out of bytes reading flag at off={off}"
        (flag,) = struct.unpack_from("<I", blob, off)
        off += 4
        tokens += 1
        if flag == 1:
            assert off + 4 <= len(blob), f"WGHT node0: ran out of bytes reading png_size at off={off}"
            (png_sz,) = struct.unpack_from("<I", blob, off)
            off += 4
            off += png_sz
        elif flag == 0:
            pass  # empty slot, nothing follows
        else:
            raise AssertionError(f"WGHT node0: unexpected flag={flag} at off={off-4}")
    assert tokens == 16, f"WGHT node0: expected 16 slot tokens, got {tokens}"
    assert off == len(blob), f"WGHT node0: walk consumed {off} bytes but node is {len(blob)} bytes"


def test_generate_write_reload_internal_roundtrip_6x6(tmp_bin):
    """Write generated terrain, reload it; all section data must survive."""
    heights = _make_sloped_heights(6, 6)
    t = generate_terrain(heights, node_dim=(6, 6), min_height=0.0, max_height=100.0)
    write_terrain(t, tmp_bin)
    t2 = Terrain.load(tmp_bin)
    _assert_sections_equal(t, t2)


def test_generate_wrong_shape_raises():
    with pytest.raises(ValueError, match="shape"):
        generate_terrain(np.zeros((10, 10), dtype=np.float32), node_dim=(2, 2))


# ---------------------------------------------------------------------------
# (c) Multi-layer WGHT / PHYM
# ---------------------------------------------------------------------------

def _walk_wght_slots(blob: bytes):
    """Return {slot_index: L-mode np.ndarray} for present slots; assert 16 slots."""
    off = 0
    present = {}
    for slot in range(16):
        (flag,) = struct.unpack_from("<I", blob, off)
        off += 4
        if flag == 1:
            (png_sz,) = struct.unpack_from("<I", blob, off)
            off += 4
            img = Image.open(io.BytesIO(blob[off : off + png_sz]))
            off += png_sz
            present[slot] = np.array(img)
        elif flag != 0:
            raise AssertionError(f"bad slot flag {flag}")
    assert off == len(blob), f"WGHT walk consumed {off} of {len(blob)}"
    return present


def _phym_cells(blob: bytes) -> np.ndarray:
    """Return (res, res, 4) uint8 cell array; assert zero 24B header."""
    hdr0, cc = struct.unpack_from("<II", blob, 0)
    assert hdr0 == 0
    assert blob[8:32] == b"\x00" * 24, "PHYM 24B header expected all-zero"
    res = int(round(cc ** 0.5))
    return np.frombuffer(blob[32:], dtype=np.uint8).reshape(res, res, 4)


def test_single_layer_default_wght_phym_unchanged(tmp_bin):
    """layer_weights=None must reproduce the legacy uniform WGHT/PHYM bytes exactly."""
    heights = _make_sloped_heights(2, 2)
    legacy = generate_terrain(heights, node_dim=(2, 2), min_height=0.0, max_height=100.0)
    explicit_none = generate_terrain(
        heights, node_dim=(2, 2), min_height=0.0, max_height=100.0, layer_weights=None
    )
    for tag in ("WGHT", "PHYM"):
        assert legacy.sections[tag].data == explicit_none.sections[tag].data
        assert legacy.sections[tag].node_offsets == explicit_none.sections[tag].node_offsets
    # WGHT node0: only slot 0 present; PHYM all cells 0
    w = _walk_wght_slots(legacy.sections["WGHT"].node(0))
    assert set(w.keys()) == {0}
    assert (w[0] == 255).all()
    cells = _phym_cells(legacy.sections["PHYM"].node(0))
    assert (cells == 0).all()


def test_multilayer_wght_slots_and_weights():
    """Two-layer split: base-only node has slot 0; a straddling node has both slots.

    Rock band over cols [50, 200) on a 2x2 grid (node cols [idx*128, idx*128+129]):
      node 0 (idx=0) covers cols [0,129]   → straddles rock edges → both layers
      node 1 (idx=1) covers cols [128,257] → beyond the band      → base only
    """
    nx = ny = 2
    H, W = ny * 128 + 1, nx * 128 + 1
    rock = np.zeros((H, W), dtype=np.float32)
    rock[:, 50:200] = 1.0
    heights = _make_flat_heights(nx, ny, 50.0)
    t = generate_terrain(heights, node_dim=(nx, ny), min_height=0.0, max_height=100.0,
                         layer_weights={1: rock})
    w0 = _walk_wght_slots(t.sections["WGHT"].node(0))  # straddles → base + rock
    w1 = _walk_wght_slots(t.sections["WGHT"].node(1))  # cols 128..256 in [50,200) partly
    assert 0 in w0 and 1 in w0, "straddling node must have both base and rock slots"
    # complementary: base + rock ≈ 255 everywhere in a node that has both
    s = w0[0].astype(int) + w0[1].astype(int)
    assert np.abs(s - 255).max() <= 1
    # node 1 covers cols [128,257]; rock is 1 for cols<200, 0 for >=200 → both present
    assert 0 in w1 and 1 in w1


def test_multilayer_phym_uniform():
    """Multi-layer output keeps PHYM uniform material 0 (non-uniform PHYM cell
    encodings are engine-internal and crash the loader — see terrain_write)."""
    nx = ny = 1
    H, W = ny * 128 + 1, nx * 128 + 1
    rock = np.zeros((H, W), dtype=np.float32)
    rock[:, W // 2 :] = 1.0  # right half rock (layer 1), left half base (layer 0)
    heights = _make_flat_heights(nx, ny, 50.0)
    t = generate_terrain(heights, node_dim=(nx, ny), min_height=0.0, max_height=100.0,
                         layer_weights={1: rock})
    cells = _phym_cells(t.sections["PHYM"].node(0))
    assert (cells == 0).all()


def test_multilayer_uint8_weights_accepted():
    """uint8 (0-255) weight arrays are scaled and produce the same slots as float."""
    nx = ny = 1
    H, W = ny * 128 + 1, nx * 128 + 1
    rock_u8 = np.zeros((H, W), dtype=np.uint8)
    rock_u8[:, W // 2 :] = 255
    heights = _make_flat_heights(nx, ny, 50.0)
    t = generate_terrain(heights, node_dim=(nx, ny), min_height=0.0, max_height=100.0,
                         layer_weights={1: rock_u8})
    w = _walk_wght_slots(t.sections["WGHT"].node(0))
    assert set(w.keys()) == {0, 1}


def test_node_layer_usage_single_and_multi():
    nx = ny = 2
    H, W = ny * 128 + 1, nx * 128 + 1
    assert node_layer_usage(None, (H, W), (nx, ny)) == {
        (0, 0): [0], (0, 1): [0], (1, 0): [0], (1, 1): [0]
    }
    # rock only in the far-right node column (idx=1 covers cols [128,257])
    rock = np.zeros((H, W), dtype=np.float32)
    rock[:, 200:] = 1.0
    usage = node_layer_usage({1: rock}, (H, W), (nx, ny))
    # idx=0 covers cols [0,129] (no rock) → base only
    # idx=1 covers cols [128,257] → base + rock (right side fully rock so base=0
    #   on the far edge but nonzero near col 128, so both present)
    assert usage[(0, 0)] == [0]
    assert usage[(1, 0)] == [0, 1]


@pytest.mark.skipif(not Path(BT015).exists(), reason="battle_terrain_015 not available")
def test_roundtrip_bt015_wght_phym_byte_identical():
    """Reader→writer round-trip of native battle_terrain_015 WGHT+PHYM is byte-identical
    at the decompressed-section level (compressed pointer garbage aside)."""
    orig, reloaded = _roundtrip(BT015)
    for tag in ("WGHT", "PHYM"):
        assert orig.sections[tag].node_offsets == reloaded.sections[tag].node_offsets
        assert orig.sections[tag].data == reloaded.sections[tag].data
