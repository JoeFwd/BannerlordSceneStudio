"""Shared scene session state for the MCP server and web GUI.

A "scene" is a directory containing scene.xscene, terrain.bin and (optionally)
navmesh.bin. Terrain is cached by (path, mtime); the navmesh is held in memory
as the working copy until saved.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

import numpy as np

from blnav import nmg9, rnm1
from blnav.terrain import Terrain
from blnav.xscene import TerrainParams, read_terrain_params


@dataclass
class SceneSession:
    scene_dir: str
    params: TerrainParams | None = None
    heights: np.ndarray | None = None      # float32 world heights
    mesh: nmg9.NavMesh = field(default_factory=nmg9.NavMesh)
    dirty: bool = False

    @property
    def navmesh_path(self) -> str:
        return os.path.join(self.scene_dir, "navmesh.bin")

    def sample_height(self, x: float, y: float) -> float:
        h = self.heights
        H, W = h.shape
        gx = min(max(x * (W - 1) / self.params.world_size_x, 0.0), W - 1.001)
        gy = min(max(y * (H - 1) / self.params.world_size_y, 0.0), H - 1.001)
        x0, y0 = int(gx), int(gy)
        fx, fy = gx - x0, gy - y0
        return float(
            h[y0, x0] * (1 - fx) * (1 - fy)
            + h[y0, x0 + 1] * fx * (1 - fy)
            + h[y0 + 1, x0] * (1 - fx) * fy
            + h[y0 + 1, x0 + 1] * fx * fy
        )

    def save(self, out_path: str | None = None, backup: bool = True) -> str:
        path = out_path or self.navmesh_path
        if backup and os.path.exists(path) and not os.path.exists(path + ".bak"):
            shutil.copy2(path, path + ".bak")
        rnm1.write(path, self.mesh.serialize())
        self.dirty = False
        return path


_current: SceneSession | None = None


def load_scene(scene_dir: str) -> SceneSession:
    global _current
    scene_dir = os.path.abspath(scene_dir)
    sess = SceneSession(scene_dir)
    xscene = os.path.join(scene_dir, "scene.xscene")
    terrain_bin = os.path.join(scene_dir, "terrain.bin")
    if os.path.exists(xscene) and os.path.exists(terrain_bin):
        sess.params = read_terrain_params(xscene)
        terr = Terrain.load(terrain_bin)
        grid = terr.heightmap_grid((sess.params.node_dim_x, sess.params.node_dim_y))
        sess.heights = sess.params.decode_heights(grid)
    if os.path.exists(sess.navmesh_path):
        sess.mesh = nmg9.NavMesh.parse(rnm1.read(sess.navmesh_path))
    _current = sess
    return sess


def current() -> SceneSession:
    if _current is None:
        raise RuntimeError("no scene loaded — call load_scene first")
    return _current
