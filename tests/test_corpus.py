"""Tests for blscene.corpus — scene corpus indexer."""
import sys
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.corpus import build_corpus, load_corpus, save_corpus, load_terrain_grids

# ---------------------------------------------------------------------------
# Paths to real game scenes used for spot-checks
# ---------------------------------------------------------------------------

_GAME = Path(r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord")
_MODULES = _GAME / "Modules"
_BATTLE_A = _MODULES / "SandBoxCore" / "SceneObj" / "battle_terrain_a"
_BATTLE_015 = _MODULES / "SandBoxCore" / "SceneObj" / "battle_terrain_015"
_DARTMOUTH = _MODULES / "DellarteDellaGuerraScenes" / "SceneObj" / "Dartmouth_castle"

# Minimal synthetic scene XML (no terrain.bin / navmesh.bin on disk)
_SYNTHETIC_XSCENE = """\
<?xml version="1.0"?>
<scene name="test_scene">
\t<terrain node_dimension_x="2" node_dimension_y="3" node_size="100.000" min_height="10.000" max_height="50.000">
\t\t<layers version="1">
\t\t\t<layer name="grass"/>
\t\t\t<layer name="rock"/>
\t\t</layers>
\t\t<nodes>
\t\t\t<node idx="0" idy="0">
\t\t\t\t<texture_levels>
\t\t\t\t\t<variable name="heightmap_level" value="5"/>
\t\t\t\t</texture_levels>
\t\t\t</node>
\t\t\t<node idx="0" idy="1">
\t\t\t\t<texture_levels>
\t\t\t\t\t<variable name="heightmap_level" value="7"/>
\t\t\t\t</texture_levels>
\t\t\t</node>
\t\t\t<node idx="1" idy="0">
\t\t\t\t<texture_levels>
\t\t\t\t\t<variable name="heightmap_level" value="5"/>
\t\t\t\t</texture_levels>
\t\t\t</node>
\t\t</nodes>
\t</terrain>
\t<entities>
\t\t<game_entity prefab="rock_a">
\t\t\t<transform position="10.000, 20.000, 5.000" rotation_euler="0.000, 0.000, 0.000"/>
\t\t</game_entity>
\t\t<game_entity prefab="rock_a">
\t\t\t<transform position="30.000, 40.000, 6.000" rotation_euler="0.000, 0.000, 1.000"/>
\t\t</game_entity>
\t\t<game_entity name="border_soft" old_prefab_name="">
\t\t\t<tags>
\t\t\t\t<tag name="walk_area_vertex"/>
\t\t\t</tags>
\t\t\t<transform position="50.000, 60.000, 7.000" rotation_euler="0.000, 0.000, 0.000"/>
\t\t\t<children>
\t\t\t\t<game_entity prefab="child_a"/>
\t\t\t\t<game_entity prefab="child_b"/>
\t\t\t</children>
\t\t</game_entity>
\t</entities>
</scene>
"""


def _make_modules_dir(tmp_path: Path) -> tuple[Path, str]:
    """Create a fake modules dir with one scene; return (modules_dir, scene_name)."""
    modules_dir = tmp_path / "Modules"
    scene_dir = modules_dir / "TestModule" / "SceneObj" / "test_scene"
    scene_dir.mkdir(parents=True)
    (scene_dir / "scene.xscene").write_text(_SYNTHETIC_XSCENE, encoding="utf-8")
    return modules_dir, "test_scene"


# ---------------------------------------------------------------------------
# Helpers for synthetic binary files
# ---------------------------------------------------------------------------

def _write_minimal_navmesh(path: Path) -> None:
    """Write a minimal navmesh.bin (RNM1 + NMG9) with 2 triangles, one island."""
    import lz4.block

    # NMG9 payload: 3 vertices, 3 edges, 2 faces (quad would be simpler but let's keep tris)
    # Triangle 1: verts 0,1,2; Triangle 2: verts 0,2,3
    vertices = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
    ]
    # Edges: 0-1, 1-2, 0-2, 2-3, 0-3
    edges = [(0,1),(1,2),(0,2),(2,3),(0,3)]
    # Face 0: verts 0,1,2; edge ids 0,1,2; g3=201
    # Face 1: verts 0,2,3; edge ids 2,3,4; g3=301
    payload = bytearray()
    payload += b"NMG9"
    payload += struct.pack("<I", len(vertices))
    for v in vertices:
        payload += struct.pack("<3f", *v)
    payload += struct.pack("<I", len(edges))
    for va, vb in edges:
        payload += struct.pack("<i2I2iI", -1, va, vb, -1, -1, 0)
    payload += struct.pack("<I", 2)
    # face 0: n=3, vids=0,1,2, eids=0,1,2, g1=2,g2=0,g3=201,g4=0,g5=0,g6=0
    payload += struct.pack("<I", 3)
    payload += struct.pack("<3I", 0, 1, 2)
    payload += struct.pack("<3I", 0, 1, 2)
    payload += struct.pack("<5i", 2, 0, 201, 0, 0)
    payload += struct.pack("<B", 0)
    # face 1: n=3, vids=0,2,3, eids=2,3,4, g3=301
    payload += struct.pack("<I", 3)
    payload += struct.pack("<3I", 0, 2, 3)
    payload += struct.pack("<3I", 2, 3, 4)
    payload += struct.pack("<5i", 2, 0, 301, 0, 0)
    payload += struct.pack("<B", 0)
    # footer
    payload += struct.pack("<I", 32) + b"\x00" * 256

    comp = lz4.block.compress(bytes(payload), mode="high_compression", store_size=False)
    usz = len(payload)
    total = 0x30 + len(comp)
    hdr = struct.pack("<4sIIIQQQII", b"RNM1", total - 8, 3, 0, usz, total - 8, 0, 0, 33)
    assert len(hdr) == 0x30
    path.write_bytes(hdr + comp)


# ---------------------------------------------------------------------------
# Synthetic scene tests (existing, unchanged behaviour)
# ---------------------------------------------------------------------------

def test_terrain_fields(tmp_path):
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = next((s for s in corpus["scenes"] if s["scene"] == scene_name), None)
    assert scene is not None, "Synthetic scene not found in corpus"
    t = scene["terrain"]
    assert t["node_dimension_x"] == 2
    assert t["node_dimension_y"] == 3
    assert t["node_size"] == 100.0
    assert t["min_height"] == 10.0
    assert t["max_height"] == 50.0
    assert t["layer_names"] == ["grass", "rock"]
    assert set(t["heightmap_levels"]) == {5, 7}


def test_entities(tmp_path):
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = next((s for s in corpus["scenes"] if s["scene"] == scene_name), None)
    assert scene is not None
    assert scene["entity_count"] == 3
    assert scene["prefab_refs"] == ["rock_a"]


def test_entity_fields(tmp_path):
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = next((s for s in corpus["scenes"] if s["scene"] == scene_name), None)
    assert scene is not None
    entities = scene["entities"]

    e0 = entities[0]
    assert e0["prefab"] == "rock_a"
    assert e0["tags"] == []
    assert e0["pos"] == pytest.approx([10.0, 20.0, 5.0])
    assert e0["children"] == 0

    e2 = entities[2]
    assert e2["prefab"] is None
    assert e2["name"] == "border_soft"
    assert "walk_area_vertex" in e2["tags"]
    assert e2["children"] == 2


def test_files_key_no_bins(tmp_path):
    """Synthetic dir has no .bin files — they should be absent from files dict."""
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = next((s for s in corpus["scenes"] if s["scene"] == scene_name), None)
    assert scene is not None
    assert "terrain.bin" not in scene["files"]
    assert "navmesh.bin" not in scene["files"]


def test_save_load_roundtrip(tmp_path):
    modules_dir, _ = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    out = tmp_path / "corpus_test.json"
    npz_out = tmp_path / "corpus_terrain_test.npz"
    save_corpus(corpus, str(out), terrain_npz_path=str(npz_out))
    restored = load_corpus(str(out))
    assert len(restored["scenes"]) == len(corpus["scenes"])
    assert restored["skipped"] == corpus["skipped"]
    orig = corpus["scenes"][0]
    rest = restored["scenes"][0]
    assert orig["entities"][0]["pos"] == rest["entities"][0]["pos"]
    assert orig["terrain"]["layer_names"] == rest["terrain"]["layer_names"]


def test_skipped_dir_counted(tmp_path):
    """A scene dir with no scene.xscene should appear in skipped."""
    modules_dir, _ = _make_modules_dir(tmp_path)
    empty = modules_dir / "TestModule" / "SceneObj" / "empty_scene"
    empty.mkdir()
    corpus = build_corpus(str(modules_dir))
    assert any("empty_scene" in s for s in corpus["skipped"])
    assert len(corpus["scenes"]) == 1


def test_module_field(tmp_path):
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = corpus["scenes"][0]
    assert scene["module"] == "TestModule"
    assert scene["scene"] == scene_name


# ---------------------------------------------------------------------------
# New field tests: terrain binary stats
# ---------------------------------------------------------------------------

def test_terrain_new_fields_no_bin(tmp_path):
    """Without terrain.bin, new binary stats fields are None."""
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = next(s for s in corpus["scenes"] if s["scene"] == scene_name)
    t = scene["terrain"]
    # New fields present but None when no terrain.bin
    assert "world_size_x" in t
    assert "world_size_y" in t
    assert "grid_h" in t and t["grid_h"] is None
    assert "grid_w" in t and t["grid_w"] is None
    assert "h_min" in t and t["h_min"] is None
    assert "h_max" in t and t["h_max"] is None
    assert "h_mean" in t and t["h_mean"] is None
    assert "roughness" in t and t["roughness"] is None
    assert "terrain_grid_key" in t and t["terrain_grid_key"] is None
    assert "terrain_grid_shape" in t and t["terrain_grid_shape"] is None
    assert "terrain_error" in t and t["terrain_error"] is None


def test_world_size_computed(tmp_path):
    """world_size_x/y = node_size * node_dimension."""
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = next(s for s in corpus["scenes"] if s["scene"] == scene_name)
    t = scene["terrain"]
    assert t["world_size_x"] == pytest.approx(200.0)  # 100 * 2
    assert t["world_size_y"] == pytest.approx(300.0)  # 100 * 3


# ---------------------------------------------------------------------------
# New field tests: navmesh stats
# ---------------------------------------------------------------------------

def test_navmesh_null_when_absent(tmp_path):
    """No navmesh.bin → navmesh field is None."""
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = next(s for s in corpus["scenes"] if s["scene"] == scene_name)
    assert scene["navmesh"] is None


def test_navmesh_stats_synthetic(tmp_path):
    """Minimal synthetic navmesh.bin → expected stats fields present."""
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    # Write a minimal navmesh.bin into the scene dir
    scene_dir = modules_dir / "TestModule" / "SceneObj" / scene_name
    _write_minimal_navmesh(scene_dir / "navmesh.bin")

    corpus = build_corpus(str(modules_dir))
    scene = next(s for s in corpus["scenes"] if s["scene"] == scene_name)
    nav = scene["navmesh"]
    assert nav is not None
    assert "navmesh_error" not in nav
    assert nav["face_count"] == 2
    assert nav["vertex_count"] == 4
    assert nav["island_count"] == 1
    assert nav["island_sizes_top5"] == [2]
    # g3 histogram
    hist = nav["g3_histogram"]
    assert "201" in hist
    assert "301" in hist
    assert hist["201"] == 1
    assert hist["301"] == 1
    # special band: both 201 and 301 are in 100-999
    assert nav["special_band_face_count"] == 2
    # bbox present
    bbox = nav["bbox"]
    assert bbox is not None
    assert bbox["x_min"] == pytest.approx(0.0)
    assert bbox["x_max"] == pytest.approx(1.0)


def test_navmesh_stats_in_files(tmp_path):
    """navmesh.bin size appears in files dict when present."""
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    scene_dir = modules_dir / "TestModule" / "SceneObj" / scene_name
    _write_minimal_navmesh(scene_dir / "navmesh.bin")
    corpus = build_corpus(str(modules_dir))
    scene = next(s for s in corpus["scenes"] if s["scene"] == scene_name)
    assert "navmesh.bin" in scene["files"]


# ---------------------------------------------------------------------------
# Terrain grids: _terrain_grids key and npz roundtrip
# ---------------------------------------------------------------------------

def test_terrain_grids_key_absent_without_bin(tmp_path):
    """No terrain.bin → _terrain_grids empty."""
    modules_dir, _ = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    assert corpus["_terrain_grids"] == {}


def test_save_load_terrain_grids_roundtrip(tmp_path):
    """Manually inject a grid and verify npz roundtrip via save/load."""
    import numpy as np
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    # Inject a synthetic grid
    fake_grid = np.arange(96 * 96, dtype=np.float32).reshape(96, 96)
    corpus["_terrain_grids"]["TestModule/test_scene"] = fake_grid
    # Also patch terrain_grid_key in the record so save_corpus includes it
    corpus["scenes"][0]["terrain"]["terrain_grid_key"] = "TestModule/test_scene"

    out_json = tmp_path / "corpus.json"
    out_npz = tmp_path / "corpus_terrain.npz"
    save_corpus(corpus, str(out_json), terrain_npz_path=str(out_npz))

    grids = load_terrain_grids(str(out_npz))
    assert "TestModule/test_scene" in grids
    np.testing.assert_array_equal(grids["TestModule/test_scene"], fake_grid)


# ---------------------------------------------------------------------------
# Real scene spot-checks (require game install)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _BATTLE_A.exists(),
    reason="battle_terrain_a not found (game not installed)",
)
def test_battle_terrain_a_terrain():
    """battle_terrain_a: 6x6 nodes, node_size 200, 11 layers, heightmap_level 8."""
    corpus = build_corpus(str(_MODULES))
    scene = next(
        (s for s in corpus["scenes"] if s["scene"] == "battle_terrain_a" and s["module"] == "SandBoxCore"),
        None,
    )
    assert scene is not None, "battle_terrain_a not found in corpus"
    t = scene["terrain"]
    assert t["node_dimension_x"] == 6
    assert t["node_dimension_y"] == 6
    assert t["node_size"] == pytest.approx(200.0)
    assert len(t["layer_names"]) == 11
    assert t["heightmap_levels"] == [8], f"Expected [8], got {t['heightmap_levels']}"


@pytest.mark.skipif(
    not _BATTLE_015.exists(),
    reason="battle_terrain_015 not found (game not installed)",
)
def test_battle_terrain_015_heightmap_level():
    """battle_terrain_015: heightmap_level must be 7."""
    corpus = build_corpus(str(_MODULES))
    scene = next(
        (s for s in corpus["scenes"] if s["scene"] == "battle_terrain_015"),
        None,
    )
    assert scene is not None, "battle_terrain_015 not found in corpus"
    t = scene["terrain"]
    assert 7 in t["heightmap_levels"], f"heightmap_level 7 not found: {t['heightmap_levels']}"


@pytest.mark.skipif(
    not _DARTMOUTH.exists(),
    reason="Dartmouth_castle not found",
)
def test_dartmouth_navmesh_oracle():
    """Dartmouth_castle: navmesh has faces > 0 and known g3 ids 201/211/301/311."""
    corpus = build_corpus(str(_MODULES))
    scene = next(
        (s for s in corpus["scenes"]
         if s["scene"] == "Dartmouth_castle" and s["module"] == "DellarteDellaGuerraScenes"),
        None,
    )
    assert scene is not None, "Dartmouth_castle not found in corpus"
    nav = scene["navmesh"]
    assert nav is not None
    assert "navmesh_error" not in nav, f"navmesh error: {nav.get('navmesh_error')}"
    assert nav["face_count"] > 0
    assert nav["vertex_count"] > 0
    hist = nav["g3_histogram"]
    for expected_id in ("201", "211", "301", "311"):
        assert expected_id in hist, f"Expected g3 id {expected_id} in histogram, got keys: {list(hist.keys())}"


@pytest.mark.skipif(
    not _BATTLE_A.exists(),
    reason="battle_terrain_a not found (game not installed)",
)
def test_battle_terrain_a_binary_stats():
    """battle_terrain_a: binary terrain stats populated (grid_h/w, h_min/max/mean, roughness)."""
    corpus = build_corpus(str(_MODULES))
    scene = next(
        (s for s in corpus["scenes"] if s["scene"] == "battle_terrain_a" and s["module"] == "SandBoxCore"),
        None,
    )
    assert scene is not None
    t = scene["terrain"]
    assert t["grid_h"] is not None and t["grid_h"] > 0
    assert t["grid_w"] is not None and t["grid_w"] > 0
    assert t["h_min"] is not None
    assert t["h_max"] is not None
    assert t["h_mean"] is not None
    assert t["roughness"] is not None and t["roughness"] >= 0
    assert t["terrain_grid_key"] == "SandBoxCore/battle_terrain_a"
    shape = t["terrain_grid_shape"]
    assert shape is not None and len(shape) == 2
    # Downsampled shape should be roughly 96x96 (±a few pixels depending on stride)
    assert 80 <= shape[0] <= 200
    assert 80 <= shape[1] <= 200
    # terrain_grid present in _terrain_grids
    grids = corpus["_terrain_grids"]
    assert "SandBoxCore/battle_terrain_a" in grids
    grid = grids["SandBoxCore/battle_terrain_a"]
    assert grid.dtype == np.float32
    assert grid.shape == tuple(shape)


@pytest.mark.skipif(
    not _DARTMOUTH.exists(),
    reason="Dartmouth_castle not found",
)
def test_dartmouth_terrain_binary_stats():
    """Dartmouth_castle: terrain binary stats populated."""
    corpus = build_corpus(str(_MODULES))
    scene = next(
        (s for s in corpus["scenes"]
         if s["scene"] == "Dartmouth_castle" and s["module"] == "DellarteDellaGuerraScenes"),
        None,
    )
    assert scene is not None
    t = scene["terrain"]
    assert t["grid_h"] is not None
    assert t["h_min"] is not None
    assert t["terrain_grid_key"] == "DellarteDellaGuerraScenes/Dartmouth_castle"
