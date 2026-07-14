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
from blnav.terrain_write import generate_terrain, write_terrain

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
