"""Tests for blscene.harvest — terrain patch / entity / flora transplant.

Unit tests use synthetic terrain and hand-built clusters (no game data).
Integration tests are skipif-guarded on the presence of native scenes:
  * Durham (node_size 100, 12x12, uniform level-7 terrain, 683 flora records,
    rock_cliff_* props) is the harvest source.
  * battle_terrain_a is the SceneBuilder template.
They harvest small rects, place into a synthetic 769x769 (6x6-node) scene,
build into a tmp dir, then reload the outputs and assert coherence.
"""
from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.compose import SceneBuilder, _sample_height
from blscene.xscene import Scene
from blscene.harvest import (
    TerrainPatch,
    EntityCluster,
    FloraCluster,
    harvest_terrain_patch,
    apply_terrain_patch,
    harvest_entities,
    place_entities,
    harvest_flora,
    place_flora,
    _rotate_flora_matrix,
    _rotate_xy,
)
from blnav.flora import Flora, FloraRecord
from blnav.terrain import Terrain

GAME = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
DURHAM = GAME + r"\DellarteDellaGuerraScenes\SceneObj\Durham"
BATTLE_TEMPLATE = GAME + r"\SandBoxCore\SceneObj\battle_terrain_a"

_NODE_SIZE = 100.0
_H = _W = 6 * 128 + 1  # 769


def _flat(value: float = 42.0) -> np.ndarray:
    return np.full((_H, _W), value, dtype=np.float32)


def _bump_patch(peak: float = 10.0, node_size: float = _NODE_SIZE) -> TerrainPatch:
    """A 129x129 Gaussian bump patch, zero at the border, *peak* at center."""
    spacing = node_size / 128.0
    n = 129
    xs = np.linspace(-1, 1, n)
    xx, yy = np.meshgrid(xs, xs)
    bump = (peak * np.exp(-(xx ** 2 + yy ** 2) * 3.0)).astype(np.float32)
    edge = np.concatenate([bump[0, :], bump[-1, :], bump[1:-1, 0], bump[1:-1, -1]])
    return TerrainPatch(
        heights=bump,
        spacing=spacing,
        world_w=(n - 1) * spacing,
        world_h=(n - 1) * spacing,
        border_mean=float(edge.mean()),
        source="synthetic",
    )


# ---------------------------------------------------------------------------
# Terrain patch math
# ---------------------------------------------------------------------------

class TestTerrainPatchMath:
    def test_stamp_bump_border_continuity(self):
        """Stamping a bump into flat terrain leaves the far field untouched and
        keeps the seam continuous (no cliffs)."""
        flat = _flat(50.0)
        patch = _bump_patch(peak=10.0)
        out = apply_terrain_patch(
            flat, patch, x=200.0, y=200.0, node_size=_NODE_SIZE, blend_margin=20.0
        )
        # Far corner unchanged.
        assert out[0, 0] == pytest.approx(50.0, abs=1e-3)
        # Everything outside the stamped window is exactly 50.
        gx0 = int(round(200.0 / (6 * _NODE_SIZE) * (_W - 1)))
        gy0 = gx0
        cols = int(round(patch.world_w / (_NODE_SIZE / 128.0))) + 1
        rows = cols
        outside = out.copy()
        outside[gy0:gy0 + rows, gx0:gx0 + cols] = 50.0
        assert np.allclose(outside, 50.0, atol=1e-3)
        # No cliff: bounded per-cell gradient inside the window.
        win = out[gy0:gy0 + rows, gx0:gx0 + cols]
        assert np.abs(np.diff(win, axis=0)).max() < 1.0
        assert np.abs(np.diff(win, axis=1)).max() < 1.0

    def test_stamp_interior_value_relative(self):
        """Relative stamp: interior rises by ~peak above the flat base."""
        flat = _flat(50.0)
        patch = _bump_patch(peak=10.0)
        out = apply_terrain_patch(
            flat, patch, x=200.0, y=200.0, node_size=_NODE_SIZE, blend_margin=20.0
        )
        gx0 = int(round(200.0 / (6 * _NODE_SIZE) * (_W - 1)))
        # Center of the 129-cell window.
        center = out[gx0 + 64, gx0 + 64]
        assert center == pytest.approx(60.0, abs=1.0)

    def test_relative_offset_matches_sloped_target(self):
        """A patch with a nonzero border mean is shifted to the target's local
        height (relative stamping), not stamped at its absolute source Z."""
        target = _flat(100.0)
        patch = _bump_patch(peak=6.0)
        # Raise the whole patch by 500 m; relative stamping must cancel that.
        patch.heights = patch.heights + 500.0
        patch.border_mean += 500.0
        out = apply_terrain_patch(
            target, patch, x=100.0, y=100.0, node_size=_NODE_SIZE, absolute=False
        )
        gx0 = int(round(100.0 / (6 * _NODE_SIZE) * (_W - 1)))
        center = out[gx0 + 64, gx0 + 64]
        # Base ~100 + peak 6, NOT ~600.
        assert center == pytest.approx(106.0, abs=1.5)

    def test_absolute_offset_keeps_source_heights(self):
        """absolute=True stamps the patch's world Z verbatim in the interior."""
        target = _flat(0.0)
        patch = _bump_patch(peak=8.0)
        patch.heights = patch.heights + 200.0
        out = apply_terrain_patch(
            target, patch, x=100.0, y=100.0, node_size=_NODE_SIZE,
            blend_margin=10.0, absolute=True,
        )
        gx0 = int(round(100.0 / (6 * _NODE_SIZE) * (_W - 1)))
        center = out[gx0 + 64, gx0 + 64]
        assert center == pytest.approx(208.0, abs=1.5)

    def test_out_of_bounds_raises(self):
        patch = _bump_patch(peak=5.0)
        with pytest.raises(ValueError):
            apply_terrain_patch(
                _flat(), patch, x=590.0, y=590.0, node_size=_NODE_SIZE
            )


# ---------------------------------------------------------------------------
# Anchor / rotation math
# ---------------------------------------------------------------------------

class TestRotationMath:
    def test_rotate_xy_90(self):
        dx, dy = _rotate_xy(1.0, 0.0, math.cos(math.pi / 2), math.sin(math.pi / 2))
        assert dx == pytest.approx(0.0, abs=1e-9)
        assert dy == pytest.approx(1.0, abs=1e-9)

    def test_rotate_flora_matrix_90(self):
        ident = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        r = _rotate_flora_matrix(ident, math.cos(math.pi / 2), math.sin(math.pi / 2))
        # R @ I = R = [[0,-1],[1,0]]
        assert r[0] == pytest.approx(0.0, abs=1e-9)
        assert r[1] == pytest.approx(-1.0, abs=1e-9)
        assert r[4] == pytest.approx(1.0, abs=1e-9)
        assert r[5] == pytest.approx(0.0, abs=1e-9)
        # Z scale + runtime column untouched.
        assert r[10] == 1.0
        assert r[3] == 0.0 and r[7] == 0.0 and r[11] == 0.0

    def test_rotate_flora_matrix_preserves_scale(self):
        """A pure-scale matrix keeps its scale magnitude after rotation."""
        m = [2.0, 0.0, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0, 0.0, 4.0, 0.0]
        r = _rotate_flora_matrix(m, math.cos(math.pi / 2), math.sin(math.pi / 2))
        # rotate 90: rows swap with sign; column norms preserved.
        col0 = math.hypot(r[0], r[4])
        col1 = math.hypot(r[1], r[5])
        assert col0 == pytest.approx(2.0)
        assert col1 == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Entity Z re-snap + placement (synthetic clusters)
# ---------------------------------------------------------------------------

def _make_entity_element(prefab: str, pos: tuple[float, float, float],
                         rot: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> ET.Element:
    ge = ET.Element("game_entity", prefab=prefab)
    ge.text = "\n\t\t\t"
    xf = ET.SubElement(ge, "transform", {
        "position": "%.3f, %.3f, %.3f" % pos,
        "rotation_euler": "%.3f, %.3f, %.3f" % rot,
    })
    xf.tail = "\n\t\t"
    return ge


class TestEntityPlacement:
    def test_z_resnap_preserves_clearance(self):
        """An entity harvested 2 m above source ground sits 2 m above the target
        ground after placement, regardless of the two terrains' absolute heights."""
        cluster = EntityCluster(
            elements=[_make_entity_element("rock_a", (0.0, 0.0, 999.0))],
            offsets=[(0.0, 0.0)],
            clearances=[2.0],
            source="synthetic",
        )
        heights = _flat(30.0)  # flat 30 m target
        builder = SceneBuilder.new_battle(
            "e_resnap", heights, node_size=_NODE_SIZE, template_dir=BATTLE_TEMPLATE
        )
        inserted = place_entities(builder, cluster, x=300.0, y=300.0, snap_z=True)
        pos = inserted[0].find("transform").get("position")
        z = float(pos.split(",")[2])
        assert z == pytest.approx(32.0, abs=0.5)  # 30 (terrain) + 2 (clearance)

    def test_rotation_moves_offset_and_yaw(self):
        """Rotating 90 deg moves a +X offset to +Y and adds to the yaw."""
        cluster = EntityCluster(
            elements=[_make_entity_element("rock_a", (10.0, 0.0, 5.0), (0.0, 0.0, 0.5))],
            offsets=[(10.0, 0.0)],
            clearances=[0.0],
            source="synthetic",
        )
        heights = _flat(20.0)
        builder = SceneBuilder.new_battle(
            "e_rot", heights, node_size=_NODE_SIZE, template_dir=BATTLE_TEMPLATE
        )
        inserted = place_entities(
            builder, cluster, x=300.0, y=300.0, rotation_deg=90.0, snap_z=True
        )
        xf = inserted[0].find("transform")
        px, py, _ = [float(v) for v in xf.get("position").split(",")]
        assert px == pytest.approx(300.0, abs=1e-2)  # +X offset rotated away
        assert py == pytest.approx(310.0, abs=1e-2)  # ...to +Y
        yaw = float(xf.get("rotation_euler").split(",")[2])
        assert yaw == pytest.approx(0.5 + math.pi / 2, abs=1e-3)

    def test_place_into_scene_directly(self):
        """place_entities accepts a bare Scene (no terrain snap)."""
        cluster = EntityCluster(
            elements=[_make_entity_element("rock_a", (0.0, 0.0, 7.0))],
            offsets=[(5.0, 5.0)],
            clearances=[0.0],
            source="synthetic",
        )
        scene = Scene.load(BATTLE_TEMPLATE + r"\scene.xscene")
        before = len(scene.entities)
        place_entities(scene, cluster, x=100.0, y=100.0, snap_z=False)
        assert len(scene.entities) == before + 1


# ---------------------------------------------------------------------------
# Flora record transform round-trip (synthetic)
# ---------------------------------------------------------------------------

class TestFloraTransform:
    def test_translate_and_resnap(self):
        rec = FloraRecord(
            name="tree_a", kind=0,
            matrix=[1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            position=[0.0, 0.0, 100.0], extra=[1.0, 1.0, 1.0, 1.0, 1.0],
        )
        cluster = FloraCluster(
            records=[rec], offsets=[(3.0, 4.0)], clearances=[1.5], source="synthetic"
        )
        heights = _flat(20.0)
        out = place_flora(heights, cluster, x=200.0, y=200.0, node_size=_NODE_SIZE)
        assert len(out) == 1
        nx, ny, nz = out[0].position
        assert nx == pytest.approx(203.0)
        assert ny == pytest.approx(204.0)
        assert nz == pytest.approx(21.5, abs=0.2)  # 20 terrain + 1.5 clearance
        # Untouched source record.
        assert rec.position == [0.0, 0.0, 100.0]

    def test_rotation_rotates_offset_and_matrix(self):
        rec = FloraRecord(
            name="tree_a", kind=0,
            matrix=[1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            position=[0.0, 0.0, 0.0], extra=[1.0, 1.0, 1.0, 1.0, 1.0],
        )
        cluster = FloraCluster(
            records=[rec], offsets=[(10.0, 0.0)], clearances=[0.0], source="synthetic"
        )
        heights = _flat(0.0)
        out = place_flora(
            heights, cluster, x=100.0, y=100.0, rotation_deg=90.0, node_size=_NODE_SIZE
        )
        nx, ny, _ = out[0].position
        assert nx == pytest.approx(100.0, abs=1e-3)
        assert ny == pytest.approx(110.0, abs=1e-3)
        m = out[0].matrix
        assert m[0] == pytest.approx(0.0, abs=1e-6)
        assert m[1] == pytest.approx(-1.0, abs=1e-6)
        assert m[4] == pytest.approx(1.0, abs=1e-6)

    def test_extra_and_kind_preserved(self):
        rec = FloraRecord(
            name="bush", kind=3,
            matrix=[1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            position=[0.0, 0.0, 0.0], extra=[1.0, 0.5, 0.25, 0.75, 1.0],
        )
        cluster = FloraCluster(
            records=[rec], offsets=[(0.0, 0.0)], clearances=[0.0], source="synthetic"
        )
        out = place_flora(_flat(0.0), cluster, x=100.0, y=100.0, node_size=_NODE_SIZE)
        assert out[0].kind == 3
        assert out[0].extra == [1.0, 0.5, 0.25, 0.75, 1.0]


# ---------------------------------------------------------------------------
# Integration: harvest from Durham, place into a synthetic scene, build, reload
# ---------------------------------------------------------------------------

_HAVE_DURHAM = Path(DURHAM + r"\terrain.bin").exists()
_HAVE_TEMPLATE = Path(BATTLE_TEMPLATE + r"\scene.xscene").exists()
_skip = pytest.mark.skipif(
    not (_HAVE_DURHAM and _HAVE_TEMPLATE),
    reason="Durham / battle_terrain_a native scene not installed",
)


@_skip
class TestIntegrationDurham:
    @pytest.fixture(scope="class")
    def built(self, tmp_path_factory):
        # Harvest.
        patch = harvest_terrain_patch(DURHAM, 500.0, 500.0, 600.0, 600.0)
        rocks = harvest_entities(DURHAM, 560.0, 380.0, 640.0, 430.0, prefab_re="rock")
        flora = harvest_flora(DURHAM, 380.0, 820.0, 400.0, 850.0)

        assert len(rocks) > 0, "expected rock_cliff_* props in Durham rect"
        assert len(flora) > 0, "expected flora in Durham rect"

        # Synthetic 6x6 target with a mild slope.
        xs = np.linspace(0, 4, _W)
        xx, yy = np.meshgrid(xs, xs)
        heights = (30.0 + 4.0 * np.sin(xx) * np.cos(yy)).astype(np.float32)
        heights = apply_terrain_patch(
            heights, patch, x=200.0, y=200.0, node_size=_NODE_SIZE
        )

        builder = SceneBuilder.new_battle(
            "harvest_integ", heights, node_size=_NODE_SIZE,
            template_dir=BATTLE_TEMPLATE,
        )
        place_entities(builder, rocks, x=350.0, y=350.0, rotation_deg=45.0)
        place_flora(builder, flora, x=350.0, y=350.0, rotation_deg=30.0)

        out_dir = str(tmp_path_factory.mktemp("harvest_integ"))
        scene_dir = builder.build(out_dir)
        return scene_dir, heights, rocks, flora

    def test_terrain_reloads(self, built):
        scene_dir, heights, _, _ = built
        terrain = Terrain.load(str(Path(scene_dir) / "terrain.bin"))
        grid = terrain.heightmap_grid((6, 6))
        assert grid.shape == (_H, _W)

    def test_flora_present_and_z_coherent(self, built):
        scene_dir, heights, _, flora = built
        f = Flora.load(str(Path(scene_dir) / "flora.bin"))
        assert len(f.records) == len(flora)
        wsx = wsy = 6 * _NODE_SIZE
        for rec in f.records:
            x, y, z = rec.position
            assert 0 <= x <= wsx and 0 <= y <= wsy  # in-bounds
            th = _sample_height(heights, wsx, wsy, x, y)
            if th is not None:
                # Z within a couple metres of terrain (clearance is small for flora).
                assert abs(z - th) < 3.0

    def test_rocks_present_in_xscene(self, built):
        scene_dir, heights, rocks, _ = built
        root = ET.parse(str(Path(scene_dir) / "scene.xscene")).getroot()
        placed = [
            ge for ge in root.find("entities")
            if (ge.get("prefab") or "").startswith("rock")
        ]
        assert len(placed) == len(rocks)
        wsx = wsy = 6 * _NODE_SIZE
        for ge in placed:
            px, py, pz = [float(v) for v in ge.find("transform").get("position").split(",")]
            assert 0 <= px <= wsx and 0 <= py <= wsy

    def test_patch_source_recorded(self, built):
        scene_dir, _, rocks, flora = built
        assert "Durham" in rocks.source
        assert "Durham" in flora.source
