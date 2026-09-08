"""Generate a navmesh from a terrain heightmap.

Grid-based generator: sample the terrain at a fixed cell size, keep cells
whose slope is walkable, emit one quad face per cell with shared vertices,
then rebuild the edge topology. This mirrors what the official editor's
"generate from terrain" produces structurally (axis-aligned quad grid with
triangles at borders is what vanilla scenes contain).
"""
from __future__ import annotations

import math

import numpy as np

from .nmg9 import Face, NavMesh


def from_heightmap(
    heights: np.ndarray,
    world_size_x: float,
    world_size_y: float,
    cell_size: float = 4.0,
    max_slope_deg: float = 40.0,
    face_id: int = 0,
    scene_level_mask: int = -1,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    region: tuple[float, float, float, float] | None = None,
) -> NavMesh:
    """Build a NavMesh from a float32 world-height grid.

    heights: (H, W) array covering [0, world_size_x] x [0, world_size_y].
    region: optional (min_x, min_y, max_x, max_y) world-space clip.
    scene_level_mask: signed g5 visibility bits, never an island identifier.
    """
    H, W = heights.shape
    sx = (W - 1) / world_size_x
    sy = (H - 1) / world_size_y

    if region:
        rx0, ry0, rx1, ry1 = region
    else:
        rx0, ry0, rx1, ry1 = 0.0, 0.0, world_size_x, world_size_y
    nx = max(1, int((rx1 - rx0) / cell_size))
    ny = max(1, int((ry1 - ry0) / cell_size))

    def sample(wx: float, wy: float) -> float:
        gx = min(max(wx * sx, 0.0), W - 1.001)
        gy = min(max(wy * sy, 0.0), H - 1.001)
        x0, y0 = int(gx), int(gy)
        fx, fy = gx - x0, gy - y0
        return float(
            heights[y0, x0] * (1 - fx) * (1 - fy)
            + heights[y0, x0 + 1] * fx * (1 - fy)
            + heights[y0 + 1, x0] * (1 - fx) * fy
            + heights[y0 + 1, x0 + 1] * fx * fy
        )

    max_dz = math.tan(math.radians(max_slope_deg)) * cell_size

    mesh = NavMesh()
    vert_ids: dict[tuple[int, int], int] = {}

    def corner(ix: int, iy: int) -> int:
        key = (ix, iy)
        if key not in vert_ids:
            wx = rx0 + ix * cell_size
            wy = ry0 + iy * cell_size
            vert_ids[key] = len(mesh.vertices)
            mesh.vertices.append((wx + origin_x, wy + origin_y, sample(wx, wy)))
        return vert_ids[key]

    for iy in range(ny):
        for ix in range(nx):
            wx = rx0 + ix * cell_size
            wy = ry0 + iy * cell_size
            zs = [
                sample(wx, wy),
                sample(wx + cell_size, wy),
                sample(wx + cell_size, wy + cell_size),
                sample(wx, wy + cell_size),
            ]
            if max(zs) - min(zs) > max_dz:
                continue
            # counter-clockwise when viewed from +Z, matching vanilla winding
            vids = [
                corner(ix, iy),
                corner(ix + 1, iy),
                corner(ix + 1, iy + 1),
                corner(ix, iy + 1),
            ]
            mesh.faces.append(Face(vids, [], g1=2, g2=0, g3=face_id, g4=0, g5=scene_level_mask, g6=0))

    mesh.rebuild_edges()
    return mesh
