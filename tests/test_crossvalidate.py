"""Cross-validate navmesh vertices against terrain heights (empire_town_s).

If our decoding of BOTH formats is right, most navmesh vertices should sit
close to the terrain surface (some are on structures/ramps and sit higher).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav import nmg9, rnm1
from blnav.terrain import Terrain
from blnav.xscene import read_terrain_params

SCENE = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\empire_town_s"

params = read_terrain_params(SCENE + r"\scene.xscene")
terr = Terrain.load(SCENE + r"\terrain.bin")
grid = params.decode_heights(terr.heightmap_grid((params.node_dim_x, params.node_dim_y)))
mesh = nmg9.NavMesh.parse(rnm1.read(SCENE + r"\navmesh.bin"))

H, W = grid.shape
sx = (W - 1) / params.world_size_x
sy = (H - 1) / params.world_size_y

verts = np.array(mesh.vertices, dtype=np.float32)
print(f"terrain: {grid.shape} world {params.world_size_x}x{params.world_size_y} "
      f"h[{params.min_height}, {params.max_height}]")
print(f"navmesh vertex bounds: x[{verts[:,0].min():.1f},{verts[:,0].max():.1f}] "
      f"y[{verts[:,1].min():.1f},{verts[:,1].max():.1f}] z[{verts[:,2].min():.1f},{verts[:,2].max():.1f}]")

# Bannerlord: X,Y ground plane, Z up
gx = np.clip(verts[:, 0] * sx, 0, W - 1.001)
gy = np.clip(verts[:, 1] * sy, 0, H - 1.001)
x0, y0 = gx.astype(int), gy.astype(int)
fx, fy = gx - x0, gy - y0
th = (grid[y0, x0] * (1 - fx) * (1 - fy) + grid[y0, x0 + 1] * fx * (1 - fy)
      + grid[y0 + 1, x0] * (1 - fx) * fy + grid[y0 + 1, x0 + 1] * fx * fy)
dz = verts[:, 2] - th
for band, hi in [("<0.5m", 0.5), ("<1m", 1.0), ("<2m", 2.0), ("<5m", 5.0)]:
    print(f"  |dz| {band}: {np.mean(np.abs(dz) < hi) * 100:.1f}%")
print(f"  median dz={np.median(dz):.3f}  p90 |dz|={np.percentile(np.abs(dz), 90):.2f}")
assert np.mean(np.abs(dz) < 2.0) > 0.5, "navmesh does not track terrain — decode wrong?"
print("CROSS-VALIDATION PASSED")
