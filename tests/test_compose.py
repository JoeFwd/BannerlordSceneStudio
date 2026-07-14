"""Tests for blscene.compose — SceneBuilder.

(a) new_battle with a synthetic 6x6-node rolling-hills heightmap.
(b) from_scene clone of battle_terrain_a — files copied, xscene byte-identical.
(c) add() with PrefabCatalog — known prefab ok, unknown raises KeyError.
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.compose import SceneBuilder
from blscene.prefabs import PrefabCatalog
from blscene.xscene import Scene
from blnav.terrain import Terrain
from blnav.xscene import TerrainParams
from blnav import rnm1, nmg9

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GAME_DIR = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
BATTLE_TEMPLATE = (
    GAME_DIR + r"\Modules\SandBoxCore\SceneObj\battle_terrain_a"
)

# 6x6 node grid: shape = (6*128+1, 6*128+1) = (769, 769)
_NX, _NY = 6, 6
_NODE_SIZE = 200.0  # metres per node
_H = _NY * 128 + 1
_W = _NX * 128 + 1


def _make_rolling_heights() -> np.ndarray:
    """Synthetic 6x6-node rolling-hills heightmap.

    Heights range from ~40 m to ~60 m with sine bumps, centred at 50 m.
    """
    xs = np.linspace(0, 2 * math.pi, _W, dtype=np.float32)
    ys = np.linspace(0, 2 * math.pi, _H, dtype=np.float32)
    xx, yy = np.meshgrid(xs, ys)
    heights = 50.0 + 10.0 * (np.sin(xx) * np.cos(yy)).astype(np.float32)
    return heights


# ---------------------------------------------------------------------------
# (a) new_battle round-trip
# ---------------------------------------------------------------------------

class TestNewBattle:
    @pytest.fixture(scope="class")
    def built(self, tmp_path_factory):
        """Build a 6x6-node rolling-hills battle scene and return (out_path, heights)."""
        heights = _make_rolling_heights()
        builder = SceneBuilder.new_battle(
            "test_battle",
            heights,
            node_size=_NODE_SIZE,
            template_dir=BATTLE_TEMPLATE,
        )
        out_dir = str(tmp_path_factory.mktemp("compose_battle"))
        scene_dir = builder.build(out_dir)
        return scene_dir, heights

    def test_all_six_files_exist(self, built):
        scene_dir, _ = built
        expected = {
            "scene.xscene",
            "terrain.bin",
            "flora.bin",
            "atmosphere.xml",
            "references.txt",
            "navmesh.bin",
        }
        found = {f.name for f in Path(scene_dir).iterdir() if f.is_file()}
        assert expected.issubset(found), f"Missing files: {expected - found}"

    def test_xscene_parses_and_byte_roundtrips(self, built, tmp_path):
        scene_dir, _ = built
        xscene_path = Path(scene_dir) / "scene.xscene"
        original_bytes = xscene_path.read_bytes()

        scene = Scene.load(str(xscene_path))
        out_path = str(tmp_path / "rt.xscene")
        scene.save(out_path)

        rt_bytes = Path(out_path).read_bytes()
        assert original_bytes == rt_bytes, "scene.xscene does not byte-round-trip through Scene.save"

    def test_terrain_params_in_xscene_match_inputs(self, built):
        scene_dir, heights = built
        xscene_path = str(Path(scene_dir) / "scene.xscene")
        from blnav.xscene import read_terrain_params
        params = read_terrain_params(xscene_path)

        assert params.node_dim_x == _NX
        assert params.node_dim_y == _NY
        assert abs(params.node_size - _NODE_SIZE) < 0.01

        min_h = float(np.min(heights))
        max_h = float(np.max(heights))
        assert abs(params.min_height - min_h) < 0.01
        assert abs(params.max_height - max_h) < 0.01

    def test_terrain_bin_heights_match_input(self, built):
        """Terrain.load on written terrain.bin decodes heights within quantization."""
        scene_dir, heights_in = built
        xscene_path = str(Path(scene_dir) / "scene.xscene")
        from blnav.xscene import read_terrain_params
        params = read_terrain_params(xscene_path)

        terrain = Terrain.load(str(Path(scene_dir) / "terrain.bin"))
        grid_u16 = terrain.heightmap_grid((params.node_dim_x, params.node_dim_y))
        heights_out = params.decode_heights(grid_u16)

        tol = (params.max_height - params.min_height) / 65535.0
        # Sample a handful of points
        sample_points = [(100, 100), (200, 300), (500, 600), (768, 768)]
        for row, col in sample_points:
            diff = abs(float(heights_out[row, col]) - float(heights_in[row, col]))
            assert diff <= tol + 1e-4, (
                f"Height mismatch at [{row},{col}]: "
                f"in={heights_in[row,col]:.4f} out={heights_out[row,col]:.4f} tol={tol:.6f}"
            )

    def test_navmesh_bin_loads_with_positive_faces(self, built):
        scene_dir, _ = built
        navmesh_path = str(Path(scene_dir) / "navmesh.bin")
        payload = rnm1.read(navmesh_path)
        mesh = nmg9.NavMesh.parse(payload)
        assert len(mesh.faces) > 0, "Generated navmesh has 0 faces"

    def test_sp_battle_set_exists(self, built):
        scene_dir, _ = built
        scene = Scene.load(str(Path(scene_dir) / "scene.xscene"))
        battle_sets = scene.find_entities(name_contains="sp_battle_set")
        assert len(battle_sets) >= 1, "sp_battle_set entity not found"

    def test_all_eight_reinforcement_points_exist(self, built):
        scene_dir, _ = built
        scene = Scene.load(str(Path(scene_dir) / "scene.xscene"))

        # Reinforcement points are children of sp_battle_set
        battle_sets = scene.find_entities(name_contains="sp_battle_set")
        assert len(battle_sets) >= 1

        sp_set = battle_sets[0]
        child_names = {ch.name or "" for ch in sp_set.children}

        expected_reinforcements = {
            "sp_attacker_archer_reinforcement",
            "sp_attacker_cavalry_reinforcement",
            "sp_attacker_horsearcher_reinforcement",
            "sp_attacker_infantry_reinforcement",
            "sp_defender_archer_reinforcement",
            "sp_defender_cavalry_reinforcement",
            "sp_defender_horsearcher_reinforcement",
            "sp_defender_infantry_reinforcement",
        }
        missing = expected_reinforcements - child_names
        assert not missing, f"Missing reinforcement children: {missing}"

    def test_kept_entities_z_snapped_to_terrain(self, built):
        """Each kept top-level entity's z should be within 0.5 m of bilinear height."""
        scene_dir, heights = built
        scene = Scene.load(str(Path(scene_dir) / "scene.xscene"))

        world_size_x = _NX * _NODE_SIZE
        world_size_y = _NY * _NODE_SIZE
        H, W = heights.shape

        from blscene.compose import _sample_height

        max_err = 0.0
        checked = 0
        for ent in scene.entities:
            pos = ent.position
            if pos is None:
                continue
            wx, wy, wz = pos
            expected_z = _sample_height(heights, world_size_x, world_size_y, wx, wy)
            if expected_z is None:
                continue  # out-of-bounds entity
            err = abs(wz - expected_z)
            max_err = max(max_err, err)
            checked += 1

        assert checked > 0, "No kept entities with in-bounds positions found"
        assert max_err <= 0.5, (
            f"Max z-snap error {max_err:.4f} m > 0.5 m tolerance"
        )

    def test_path_point_z_snapped_to_terrain(self, built):
        """Every path point's z should be within 0.5 m of bilinear terrain height."""
        scene_dir, heights = built
        scene = Scene.load(str(Path(scene_dir) / "scene.xscene"))

        world_size_x = _NX * _NODE_SIZE
        world_size_y = _NY * _NODE_SIZE

        from blscene.compose import _sample_height

        max_err = 0.0
        checked = 0
        paths_elem = scene._root.find("Paths")
        assert paths_elem is not None, "<Paths> element missing from composed xscene"

        for path_elem in paths_elem:
            if path_elem.tag != "path":
                continue
            points_elem = path_elem.find("points")
            if points_elem is None:
                continue
            for point_elem in points_elem:
                if point_elem.tag != "point":
                    continue
                pos_str = point_elem.get("position")
                if pos_str is None:
                    continue
                vals = [float(v.strip()) for v in pos_str.split(",")]
                wx, wy, wz = vals[0], vals[1], vals[2]
                expected_z = _sample_height(heights, world_size_x, world_size_y, wx, wy)
                if expected_z is None:
                    continue
                err = abs(wz - expected_z)
                max_err = max(max_err, err)
                checked += 1

        assert checked > 0, "No path points with in-bounds positions found"
        assert max_err <= 0.5, (
            f"Max path-point z-snap error {max_err:.4f} m > 0.5 m tolerance"
        )


# ---------------------------------------------------------------------------
# (b) from_scene clone — byte-identical xscene
# ---------------------------------------------------------------------------

class TestFromSceneClone:
    @pytest.fixture(scope="class")
    def cloned(self, tmp_path_factory):
        out_dir = str(tmp_path_factory.mktemp("compose_clone"))
        builder = SceneBuilder.from_scene(BATTLE_TEMPLATE, "battle_terrain_a_clone")
        scene_dir = builder.build(out_dir)
        return scene_dir

    def test_all_six_files_exist(self, cloned):
        expected = {
            "scene.xscene",
            "terrain.bin",
            "flora.bin",
            "atmosphere.xml",
            "references.txt",
            "navmesh.bin",
        }
        found = {f.name for f in Path(cloned).iterdir() if f.is_file()}
        assert expected.issubset(found), f"Missing files: {expected - found}"

    def test_xscene_byte_identical_to_original(self, cloned):
        orig_bytes = (Path(BATTLE_TEMPLATE) / "scene.xscene").read_bytes()
        clone_bytes = (Path(cloned) / "scene.xscene").read_bytes()
        # First find the diff for a useful error message
        diff_offset = None
        for i, (a, b) in enumerate(zip(orig_bytes, clone_bytes)):
            if a != b:
                diff_offset = i
                break
        if diff_offset is None and len(orig_bytes) != len(clone_bytes):
            diff_offset = min(len(orig_bytes), len(clone_bytes))

        assert orig_bytes == clone_bytes, (
            f"Cloned scene.xscene differs from original "
            + (f"at offset {diff_offset}" if diff_offset is not None else "(length mismatch)")
        )

    def test_terrain_bin_copied(self, cloned):
        orig = (Path(BATTLE_TEMPLATE) / "terrain.bin").read_bytes()
        clone = (Path(cloned) / "terrain.bin").read_bytes()
        assert orig == clone, "terrain.bin was not copied byte-identically"

    def test_navmesh_bin_copied(self, cloned):
        orig = (Path(BATTLE_TEMPLATE) / "navmesh.bin").read_bytes()
        clone = (Path(cloned) / "navmesh.bin").read_bytes()
        assert orig == clone, "navmesh.bin was not copied byte-identically"


# ---------------------------------------------------------------------------
# (c) add() with PrefabCatalog
# ---------------------------------------------------------------------------

class TestAddWithCatalog:
    @pytest.fixture(scope="class")
    def catalog(self):
        cat = PrefabCatalog()
        cat.scan([GAME_DIR + r"\Modules\Native"])
        return cat

    def test_known_prefab_ok(self, catalog, tmp_path):
        heights = _make_rolling_heights()
        builder = SceneBuilder.new_battle(
            "add_test",
            heights,
            node_size=_NODE_SIZE,
            template_dir=BATTLE_TEMPLATE,
        )
        # Pick a known prefab from Native
        known = catalog.names()[0]
        # Should not raise
        builder.add(known, (600.0, 600.0, 50.0), catalog=catalog)

    def test_unknown_prefab_raises(self, catalog, tmp_path):
        heights = _make_rolling_heights()
        builder = SceneBuilder.new_battle(
            "add_test2",
            heights,
            node_size=_NODE_SIZE,
            template_dir=BATTLE_TEMPLATE,
        )
        with pytest.raises(KeyError, match="Prefab not found"):
            builder.add("__nonexistent_prefab_xyz__", (0.0, 0.0, 0.0), catalog=catalog)

    def test_add_without_catalog_no_error(self, tmp_path):
        heights = _make_rolling_heights()
        builder = SceneBuilder.new_battle(
            "add_test3",
            heights,
            node_size=_NODE_SIZE,
            template_dir=BATTLE_TEMPLATE,
        )
        # Without catalog: any name accepted
        builder.add("any_name_no_validation", (100.0, 100.0, 50.0))

    def test_added_entity_appears_in_built_xscene(self, catalog, tmp_path):
        heights = _make_rolling_heights()
        builder = SceneBuilder.new_battle(
            "add_test4",
            heights,
            node_size=_NODE_SIZE,
            template_dir=BATTLE_TEMPLATE,
        )
        known = catalog.names()[0]
        pos = (600.0, 600.0, 50.0)
        builder.add(known, pos, catalog=catalog)
        scene_dir = builder.build(str(tmp_path))

        scene = Scene.load(str(Path(scene_dir) / "scene.xscene"))
        found = scene.find_entities(prefab=known)
        # There should be at least one (the one we just added)
        assert len(found) >= 1
        added = found[-1]
        assert added.position is not None
        assert abs(added.position[0] - pos[0]) < 0.01
        assert abs(added.position[1] - pos[1]) < 0.01
