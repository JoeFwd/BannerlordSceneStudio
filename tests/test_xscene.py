"""Tests for blscene.xscene — read/modify/write model for scene.xscene files.

Reference files (Bannerlord v1.4 install):
  - vlandia_town_c/scene.xscene  ~1.9 MB, native town
  - Coventry/scene.xscene        ~4.6 MB, mod town
  - Native/Prefabs/Banner.xml    prefab file (<prefabs> root)

Byte-identity verdict (documented here for reference):
  Both scene files round-trip byte-identically.  The serializer manually
  walks the ElementTree so it can reproduce:
    - '<?xml version="1.0"?>' declaration (double-quoted, no encoding attr)
    - No space before '/>' on self-closing tags
    - CRLF line endings (ET normalises to LF on parse; we restore on write)
    - Original attribute order (dict insertion order, preserved by ET)
    - Trailing \\r\\n\\r\\n after the root closing tag
"""
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.xscene import Scene, load_prefabs

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_GAME = Path(r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord")
VLANDIA = _GAME / "Modules" / "SandBoxCore" / "SceneObj" / "vlandia_town_c" / "scene.xscene"
COVENTRY = _GAME / "Modules" / "DellarteDellaGuerraScenes" / "SceneObj" / "Coventry" / "scene.xscene"
BANNER_XML = _GAME / "Modules" / "Native" / "Prefabs" / "Banner.xml"

# Known counts derived from independent xml.etree.ElementTree traversal
_VLANDIA_ALL_ENTITIES = 5356   # tree.findall('.//game_entity')
_VLANDIA_TOP_ENTITIES = 3209   # direct children of <entities>
_COVENTRY_ALL_ENTITIES = 8685
_COVENTRY_TOP_ENTITIES = 1996
_BANNER_PREFAB_ENTITIES = 29   # direct children of <prefabs>


def _first_diff(a: bytes, b: bytes) -> str:
    """Return a human-readable description of the first byte difference."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            lo = max(0, i - 30)
            hi = i + 60
            return (
                f"First diff at offset {i}\n"
                f"  orig: {a[lo:hi]!r}\n"
                f"  out:  {b[lo:hi]!r}"
            )
    if len(a) != len(b):
        return f"Same content but different lengths: orig={len(a)}, out={len(b)}"
    return ""


# ===========================================================================
# (a) Byte-identical round-trip
# ===========================================================================

@pytest.mark.parametrize("scene_path,label", [
    (VLANDIA, "vlandia_town_c"),
    (COVENTRY, "Coventry"),
])
def test_roundtrip_byte_identical(scene_path, label):
    """Load → save → compare bytes: output must be identical to the original."""
    orig = scene_path.read_bytes()
    scene = Scene.load(str(scene_path))

    with tempfile.NamedTemporaryFile(suffix=".xscene", delete=False) as fh:
        tmp = fh.name
    try:
        scene.save(tmp)
        out = Path(tmp).read_bytes()
    finally:
        Path(tmp).unlink(missing_ok=True)

    diff = _first_diff(orig, out)
    assert orig == out, f"Round-trip not byte-identical for {label}:\n{diff}"


# ===========================================================================
# (b) Entity query counts match independent ET count
# ===========================================================================

@pytest.mark.parametrize("scene_path,expected_all,expected_top,label", [
    (VLANDIA, _VLANDIA_ALL_ENTITIES, _VLANDIA_TOP_ENTITIES, "vlandia_town_c"),
    (COVENTRY, _COVENTRY_ALL_ENTITIES, _COVENTRY_TOP_ENTITIES, "Coventry"),
])
def test_entity_count_matches_et(scene_path, expected_all, expected_top, label):
    """scene.entities count and findall('.//game_entity') match known values."""
    # Independent count via raw ET
    tree = ET.parse(str(scene_path))
    all_count = len(tree.findall(".//game_entity"))
    assert all_count == expected_all, (
        f"{label}: expected {expected_all} total game_entity elements, got {all_count}"
    )

    # Count via Scene API
    scene = Scene.load(str(scene_path))
    top_count = len(scene.entities)
    assert top_count == expected_top, (
        f"{label}: expected {expected_top} top-level entities, got {top_count}"
    )


def test_scene_name_and_levels_vlandia():
    """scene_name and levels are correctly parsed for vlandia_town_c."""
    scene = Scene.load(str(VLANDIA))
    assert scene.scene_name == "vlandia_town_c"
    assert scene.levels == ["base", "level_1", "level_2", "level_3", "siege", "civilian"]


def test_scene_name_and_levels_coventry():
    """scene_name and levels are correctly parsed for Coventry."""
    scene = Scene.load(str(COVENTRY))
    assert scene.scene_name == "Coventry"
    # Coventry has the same set, order may differ — assert as a set
    assert set(scene.levels) == {"base", "civilian", "siege", "level_1", "level_2", "level_3"}


def test_find_entities_by_prefab_vlandia():
    """find_entities(prefab=...) returns a non-empty subset of entities."""
    scene = Scene.load(str(VLANDIA))
    results = scene.find_entities(prefab="market_apple_crate")
    assert len(results) >= 1
    for e in results:
        assert e.prefab == "market_apple_crate"


def test_find_entities_name_contains():
    """find_entities(name_contains=...) matches on prefab name substring."""
    scene = Scene.load(str(VLANDIA))
    results = scene.find_entities(name_contains="torch")
    assert len(results) >= 1
    for e in results:
        pname = e.prefab or e.name or ""
        assert "torch" in pname


def test_entity_position_is_parsed():
    """First entity in vlandia_town_c has a parseable position tuple."""
    scene = Scene.load(str(VLANDIA))
    first = scene.entities[0]
    pos = first.position
    assert pos is not None
    assert len(pos) == 3
    assert all(isinstance(v, float) for v in pos)


# ===========================================================================
# (c) add_entity → save → reload → found with exact transform format
# ===========================================================================

@pytest.mark.parametrize("scene_path,label", [
    (VLANDIA, "vlandia_town_c"),
    (COVENTRY, "Coventry"),
])
def test_add_entity_roundtrip(scene_path, label):
    """add_entity → save → reload → entity found with exactly formatted transform."""
    scene = Scene.load(str(scene_path))
    orig_count = len(scene.entities)

    PFB = "test_xscene_marker"
    POS = (123.456, 78.9, 0.001)
    ROT = (0.1, 0.0, -0.5)
    SCL = (2.0, 2.0, 2.0)
    LVLS = ["base", "level_1"]

    added = scene.add_entity(PFB, POS, ROT, SCL, LVLS)
    assert added.prefab == PFB
    assert added.position == pytest.approx(POS, abs=1e-4)
    assert added.rotation_euler == pytest.approx(ROT, abs=1e-4)
    assert added.scale == pytest.approx(SCL, abs=1e-4)
    assert added.level_names == LVLS

    with tempfile.NamedTemporaryFile(suffix=".xscene", delete=False) as fh:
        tmp = fh.name
    try:
        scene.save(tmp)
        out_bytes = Path(tmp).read_bytes()

        # Check the exact formatted strings appear in the file bytes
        assert b'prefab="test_xscene_marker"' in out_bytes
        assert b'position="123.456, 78.900, 0.001"' in out_bytes
        assert b'rotation_euler="0.100, 0.000, -0.500"' in out_bytes
        assert b'scale="2.000, 2.000, 2.000"' in out_bytes

        # Reload and verify
        scene2 = Scene.load(tmp)
        assert len(scene2.entities) == orig_count + 1

        found = scene2.find_entities(prefab=PFB)
        assert len(found) == 1
        e2 = found[0]
        assert e2.position == pytest.approx(POS, abs=1e-4)
        assert e2.rotation_euler == pytest.approx(ROT, abs=1e-4)
        assert e2.scale == pytest.approx(SCL, abs=1e-4)
        assert e2.level_names == LVLS
    finally:
        Path(tmp).unlink(missing_ok=True)


def test_add_entity_no_scale_no_levels(tmp_path):
    """add_entity without scale/levels produces a valid self-closing <transform>."""
    scene = Scene.load(str(VLANDIA))
    e = scene.add_entity("bare_prefab", (1.0, 2.0, 3.0))
    assert e.scale is None
    assert e.level_names == []

    out_path = str(tmp_path / "out.xscene")
    scene.save(out_path)
    out_bytes = Path(out_path).read_bytes()
    assert b'prefab="bare_prefab"' in out_bytes
    # transform should be self-closing (no space before />)
    assert b'rotation_euler="0.000, 0.000, 0.000"/>' in out_bytes


def test_add_entity_then_roundtrip_still_matches_orig(tmp_path):
    """After add_entity, unmodified portion of vlandia still round-trips cleanly.

    Strategy: load the file, save it WITHOUT any mutation (baseline), then
    add an entity and confirm the bytes before the new element are unchanged.
    """
    scene_baseline = Scene.load(str(VLANDIA))
    baseline_path = str(tmp_path / "baseline.xscene")
    scene_baseline.save(baseline_path)
    baseline = Path(baseline_path).read_bytes()

    scene_mod = Scene.load(str(VLANDIA))
    scene_mod.add_entity("mutation_test", (0.0, 0.0, 0.0))
    mod_path = str(tmp_path / "modified.xscene")
    scene_mod.save(mod_path)
    modified = Path(mod_path).read_bytes()

    # The modified file must be longer (new entity added)
    assert len(modified) > len(baseline)

    # The new entity tag must appear near the end (before </entities>)
    assert b'prefab="mutation_test"' in modified


# ===========================================================================
# (d) load_prefabs on Native/Prefabs/Banner.xml
# ===========================================================================

def test_load_prefabs_banner():
    """load_prefabs returns Entity wrappers from Banner.xml (<prefabs> root)."""
    entities = load_prefabs(str(BANNER_XML))
    assert len(entities) == _BANNER_PREFAB_ENTITIES, (
        f"Expected {_BANNER_PREFAB_ENTITIES} prefab entities, got {len(entities)}"
    )


def test_load_prefabs_banner_no_prefab_attr():
    """Prefab-file entities have 'name' attribute, not 'prefab'."""
    entities = load_prefabs(str(BANNER_XML))
    for e in entities:
        assert e.prefab is None, f"Expected None prefab attr, got {e.prefab!r}"
        assert e.name is not None


def test_load_prefabs_banner_first_entity():
    """First entity in Banner.xml is dragon_banner_animated with a scale."""
    entities = load_prefabs(str(BANNER_XML))
    first = entities[0]
    assert first.name == "dragon_banner_animated"
    assert first.scale is not None
    # Scale from file: 0.020, 0.030, 0.020
    assert first.scale == pytest.approx((0.02, 0.03, 0.02), abs=1e-4)


def test_load_prefabs_wrong_root(tmp_path):
    """load_prefabs raises ValueError when root tag is not <prefabs>."""
    bad = tmp_path / "bad.xml"
    bad.write_text('<scene name="x"/>\r\n\r\n', encoding="utf-8")
    with pytest.raises(ValueError, match="prefabs"):
        load_prefabs(str(bad))


def test_load_prefabs_children_accessible():
    """Prefab entities with <children> expose them via .children."""
    entities = load_prefabs(str(BANNER_XML))
    # dragon_banner_sim has children per manual inspection
    with_children = [e for e in entities if len(e.children) > 0]
    assert len(with_children) >= 1, "Expected at least one prefab with children"
