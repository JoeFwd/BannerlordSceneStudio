"""Tests for blnav.flora: reader and writer."""
import struct
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav.flora import Flora, FloraRecord, MAGIC

KHUZAIT = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\SandBox\SceneObj\khuzait_village_e\flora.bin"
)


# ---------------------------------------------------------------------------
# Empty file round-trip
# ---------------------------------------------------------------------------

def test_empty_roundtrip(tmp_path):
    """Empty FLR2 (12 bytes) loads and re-encodes byte-identically."""
    # Build a minimal 12-byte empty file
    empty = MAGIC + struct.pack("<II", 4, 0)
    src = tmp_path / "empty.bin"
    src.write_bytes(empty)

    flora = Flora.load(str(src))
    assert flora.records == []
    assert flora.to_bytes() == empty


# ---------------------------------------------------------------------------
# khuzait_village_e round-trip
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not Path(KHUZAIT).exists(), reason="Bannerlord not installed")
def test_khuzait_roundtrip():
    """Load khuzait_village_e/flora.bin and re-encode byte-identically."""
    orig_bytes = Path(KHUZAIT).read_bytes()
    flora = Flora.load(KHUZAIT)

    assert len(flora.records) == 1
    rec = flora.records[0]
    assert rec.name == "tree_acacia"
    assert rec.kind == 0
    # identity rotation/scale matrix
    assert rec.matrix[:3] == pytest.approx([1.0, 0.0, 0.0])
    assert rec.matrix[4:7] == pytest.approx([0.0, 1.0, 0.0])
    assert rec.matrix[8:11] == pytest.approx([0.0, 0.0, 1.0])
    # world position is plausible (non-zero x/y, small z)
    assert 0 < rec.position[0] < 2000
    assert 0 < rec.position[1] < 2000
    # default extra = all 1.0
    assert rec.extra == pytest.approx([1.0, 1.0, 1.0, 1.0, 1.0])

    assert flora.to_bytes() == orig_bytes


@pytest.mark.skipif(not Path(KHUZAIT).exists(), reason="Bannerlord not installed")
def test_khuzait_save_reload(tmp_path):
    """save() then load() returns the same data."""
    flora = Flora.load(KHUZAIT)
    out = str(tmp_path / "flora.bin")
    flora.save(out)
    flora2 = Flora.load(out)
    assert len(flora2.records) == len(flora.records)
    for r1, r2 in zip(flora.records, flora2.records):
        assert r1.name == r2.name
        assert r1.kind == r2.kind
        assert r1.matrix == pytest.approx(r2.matrix, abs=1e-7)
        assert r1.position == pytest.approx(r2.position, abs=1e-7)
        assert r1.extra == pytest.approx(r2.extra, abs=1e-7)


# ---------------------------------------------------------------------------
# Synthetic build-then-parse test
# ---------------------------------------------------------------------------

def test_synthetic_build_parse():
    """Build a Flora from scratch, encode, decode, check fields survive."""
    rec = FloraRecord(
        name="tree_test",
        kind=3,
        matrix=[
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 2.0, 0.0,
        ],
        position=[100.0, 200.0, 5.0],
        extra=[1.0, 0.5, 0.75, 0.25, 1.0],
    )
    flora = Flora(records=[rec])
    encoded = flora.to_bytes()

    # Validate header
    assert encoded[:4] == MAGIC
    total_size = struct.unpack_from("<I", encoded, 4)[0]
    assert total_size == len(encoded) - 8
    record_count = struct.unpack_from("<I", encoded, 8)[0]
    assert record_count == 1

    # Round-trip through a temp file
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(encoded)
        tmp = f.name

    flora2 = Flora.load(tmp)
    assert len(flora2.records) == 1
    r = flora2.records[0]
    assert r.name == "tree_test"
    assert r.kind == 3
    assert r.matrix == pytest.approx(rec.matrix, abs=1e-7)
    assert r.position == pytest.approx(rec.position, abs=1e-7)
    assert r.extra == pytest.approx(rec.extra, abs=1e-7)


def test_synthetic_multi_record():
    """Multiple records encode/decode correctly and total_size is exact."""
    records = [
        FloraRecord("grass_a", 0, [1.0, 0.0, 0.0, 0.0,
                                    0.0, 1.0, 0.0, 0.0,
                                    0.0, 0.0, 1.0, 0.0],
                    [10.0, 20.0, 0.0], [1.0, 1.0, 1.0, 1.0, 1.0]),
        FloraRecord("rock_b", 2, [-1.0, 0.0, 0.0, 0.0,
                                   0.0, -1.0, 0.0, 0.0,
                                   0.0, 0.0, 1.5, 0.0],
                    [500.0, 600.0, 3.5], [1.0, 0.8, 0.6, 0.4, 1.0]),
    ]
    flora = Flora(records=records)
    data = flora.to_bytes()

    assert data[:4] == MAGIC
    assert struct.unpack_from("<I", data, 4)[0] == len(data) - 8
    assert struct.unpack_from("<I", data, 8)[0] == 2

    flora2 = Flora.load_bytes(data)
    assert len(flora2.records) == 2
    for r1, r2 in zip(records, flora2.records):
        assert r1.name == r2.name
        assert r1.kind == r2.kind
        assert r1.matrix == pytest.approx(r2.matrix, abs=1e-7)
        assert r1.position == pytest.approx(r2.position, abs=1e-7)
        assert r1.extra == pytest.approx(r2.extra, abs=1e-7)


def test_bad_magic_raises():
    """load() raises ValueError for wrong magic."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"XXXX" + struct.pack("<II", 4, 0))
        tmp = f.name
    with pytest.raises(ValueError, match="bad magic"):
        Flora.load(tmp)
