"""Tests for blscene.corpus — scene corpus indexer."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.corpus import build_corpus, load_corpus, save_corpus

# ---------------------------------------------------------------------------
# Paths to real game scenes used for spot-checks
# ---------------------------------------------------------------------------

_GAME = Path(r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord")
_MODULES = _GAME / "Modules"
_BATTLE_A = _MODULES / "SandBoxCore" / "SceneObj" / "battle_terrain_a"
_BATTLE_015 = _MODULES / "SandBoxCore" / "SceneObj" / "battle_terrain_015"

# Minimal synthetic scene XML
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
# Synthetic scene tests
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

    # First entity: rock_a prefab, no tags, has position, no children
    e0 = entities[0]
    assert e0["prefab"] == "rock_a"
    assert e0["tags"] == []
    assert e0["pos"] == pytest.approx([10.0, 20.0, 5.0])
    assert e0["children"] == 0

    # Third entity: inline with tag and 2 children
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
    save_corpus(corpus, str(out))
    restored = load_corpus(str(out))
    assert len(restored["scenes"]) == len(corpus["scenes"])
    assert restored["skipped"] == corpus["skipped"]
    # Spot-check entity data survives JSON round-trip
    orig = corpus["scenes"][0]
    rest = restored["scenes"][0]
    assert orig["entities"][0]["pos"] == rest["entities"][0]["pos"]
    assert orig["terrain"]["layer_names"] == rest["terrain"]["layer_names"]


def test_skipped_dir_counted(tmp_path):
    """A scene dir with no scene.xscene should appear in skipped."""
    modules_dir, _ = _make_modules_dir(tmp_path)
    # Add an empty scene dir (no scene.xscene)
    empty = modules_dir / "TestModule" / "SceneObj" / "empty_scene"
    empty.mkdir()
    corpus = build_corpus(str(modules_dir))
    assert any("empty_scene" in s for s in corpus["skipped"])
    # The real scene still appears
    assert len(corpus["scenes"]) == 1


def test_module_field(tmp_path):
    modules_dir, scene_name = _make_modules_dir(tmp_path)
    corpus = build_corpus(str(modules_dir))
    scene = corpus["scenes"][0]
    assert scene["module"] == "TestModule"
    assert scene["scene"] == scene_name


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
