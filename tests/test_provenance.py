"""Tests for blscene.provenance — audit trail emitted by SceneBuilder.build().

(a) from_scene clone: provenance.json records all roles as verbatim from the
    donor scene; file_origins shows COPIED for binary assets.
(b) new_battle + harvest placement: provenance.json records terrain/navmesh as
    GENERATED, xscene_skeleton as MODIFIED, and an entities record for the
    harvested placement.

Both tests are skipif-guarded on native game data presence so they run
cleanly in offline CI.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.compose import SceneBuilder

GAME = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
CLUN = GAME + r"\DellarteDellaGuerraScenes\SceneObj\Clun_castle"
BATTLE_TEMPLATE = GAME + r"\SandBoxCore\SceneObj\battle_terrain_a"
DARTMOUTH = GAME + r"\DellarteDellaGuerraScenes\SceneObj\Dartmouth_castle"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rolling_heights(nx: int = 6, ny: int = 6) -> np.ndarray:
    H = ny * 128 + 1
    W = nx * 128 + 1
    xs = np.linspace(0, 2 * np.pi, W, dtype=np.float32)
    ys = np.linspace(0, 2 * np.pi, H, dtype=np.float32)
    xx, yy = np.meshgrid(xs, ys)
    return (50.0 + 10.0 * (np.sin(xx) * np.cos(yy))).astype(np.float32)


def _load_provenance(scene_dir: str) -> dict:
    pj = Path(scene_dir) / "provenance.json"
    assert pj.exists(), f"provenance.json not found in {scene_dir}"
    return json.loads(pj.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# (a) from_scene clone
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not Path(CLUN).exists(), reason="Clun_castle not available")
class TestFromSceneProvenance:
    @pytest.fixture(scope="class")
    def built(self, tmp_path_factory):
        builder = SceneBuilder.from_scene(CLUN, "test_clone_prov")
        out_dir = str(tmp_path_factory.mktemp("prov_clone"))
        scene_dir = builder.build(out_dir)
        return scene_dir

    def test_provenance_json_exists(self, built):
        assert (Path(built) / "provenance.json").exists()

    def test_provenance_md_exists(self, built):
        assert (Path(built) / "provenance.md").exists()

    def test_scene_name(self, built):
        data = _load_provenance(built)
        assert data["scene_name"] == "test_clone_prov"

    def test_tool_field(self, built):
        data = _load_provenance(built)
        assert data["tool"] == "blscene"

    def test_sources_all_verbatim(self, built):
        data = _load_provenance(built)
        roles = {r["role"]: r for r in data["sources"]}
        for role in ("xscene_skeleton", "terrain", "navmesh", "flora", "atmosphere", "references"):
            assert role in roles, f"missing role: {role}"
            assert roles[role]["verbatim"] is True, f"{role} should be verbatim"

    def test_source_label_contains_clun(self, built):
        data = _load_provenance(built)
        for rec in data["sources"]:
            assert "Clun_castle" in rec["source"], \
                f"source label {rec['source']!r} missing Clun_castle"

    def test_terrain_file_origin_copied(self, built):
        data = _load_provenance(built)
        fo = data["file_origins"]
        assert "terrain.bin" in fo
        assert fo["terrain.bin"]["origin"] == "COPIED"
        assert fo["terrain.bin"]["sha256_match"] is True

    def test_navmesh_file_origin_copied(self, built):
        data = _load_provenance(built)
        fo = data["file_origins"]
        assert "navmesh.bin" in fo
        assert fo["navmesh.bin"]["origin"] == "COPIED"
        assert fo["navmesh.bin"]["sha256_match"] is True

    def test_xscene_file_origin_modified(self, built):
        data = _load_provenance(built)
        fo = data["file_origins"]
        assert fo["scene.xscene"]["origin"] == "MODIFIED"

    def test_reuse_summary_mentions_copied(self, built):
        data = _load_provenance(built)
        summary = data["reuse_summary"]
        assert "COPIED" in summary

    def test_generated_utc_present(self, built):
        data = _load_provenance(built)
        assert data["generated_utc"]


# ---------------------------------------------------------------------------
# (b) new_battle + harvest placement
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not Path(BATTLE_TEMPLATE).exists() or not Path(DARTMOUTH).exists(),
    reason="battle_terrain_a or Dartmouth_castle not available",
)
class TestNewBattleProvenanceWithHarvest:
    @pytest.fixture(scope="class")
    def built(self, tmp_path_factory):
        from blscene.harvest import harvest_entities, place_entities

        heights = _rolling_heights()
        builder = SceneBuilder.new_battle(
            "test_battle_prov",
            heights,
            node_size=200.0,
            template_dir=BATTLE_TEMPLATE,
        )
        builder.provenance_note("script", "tests/test_provenance.py")
        builder.provenance_note("seed", 0)

        # Harvest a small cluster from Dartmouth and place it.
        cluster = harvest_entities(DARTMOUTH, 250.0, 390.0, 290.0, 430.0,
                                   prefab_re="rock")
        if cluster.elements:
            place_entities(builder, cluster, x=400.0, y=400.0)

        out_dir = str(tmp_path_factory.mktemp("prov_battle"))
        scene_dir = builder.build(out_dir)
        return scene_dir, cluster

    def test_provenance_json_exists(self, built):
        scene_dir, _ = built
        assert (Path(scene_dir) / "provenance.json").exists()

    def test_terrain_generated(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        roles = {r["role"]: r for r in data["sources"]}
        assert "terrain" in roles
        assert roles["terrain"]["source"] == "GENERATED"
        assert roles["terrain"]["verbatim"] is None

    def test_navmesh_generated(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        roles = {r["role"]: r for r in data["sources"]}
        assert "navmesh" in roles
        assert roles["navmesh"]["source"] == "GENERATED"

    def test_xscene_skeleton_modified(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        roles = {r["role"]: r for r in data["sources"]}
        assert "xscene_skeleton" in roles
        assert roles["xscene_skeleton"]["verbatim"] is False

    def test_entities_record_when_harvested(self, built):
        scene_dir, cluster = built
        if not cluster.elements:
            pytest.skip("no rock entities found in Dartmouth rect")
        data = _load_provenance(scene_dir)
        roles = [r["role"] for r in data["sources"]]
        assert "entities" in roles
        ent_rec = next(r for r in data["sources"] if r["role"] == "entities")
        assert ent_rec["count"] == len(cluster.elements)
        assert "Dartmouth_castle" in ent_rec["source"]

    def test_generator_meta(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        assert data["generator"]["script"] == "tests/test_provenance.py"
        assert data["generator"]["seed"] == 0

    def test_terrain_file_origin_generated(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        fo = data["file_origins"]
        assert fo["terrain.bin"]["origin"] == "GENERATED"

    def test_navmesh_file_origin_generated(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        fo = data["file_origins"]
        assert fo["navmesh.bin"]["origin"] == "GENERATED"

    def test_atmosphere_file_origin_copied(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        fo = data["file_origins"]
        assert "atmosphere.xml" in fo
        # atmosphere is copied from template so should be COPIED with matching hash
        assert fo["atmosphere.xml"]["origin"] == "COPIED"
        assert fo["atmosphere.xml"]["sha256_match"] is True

    def test_reuse_summary_mentions_generated(self, built):
        scene_dir, _ = built
        data = _load_provenance(scene_dir)
        assert "GENERATED" in data["reuse_summary"]
