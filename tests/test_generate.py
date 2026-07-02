"""Generator sanity: build a navmesh from empire_town_s terrain, serialize,
reparse, and check winding matches vanilla convention."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav import generate, nmg9, rnm1
from blnav.terrain import Terrain
from blnav.xscene import read_terrain_params

SCENE = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\empire_town_s"


def signed_area(mesh, face):
    pts = [mesh.vertices[v] for v in face.vertex_ids]
    s = 0.0
    for i in range(len(pts)):
        x1, y1, _ = pts[i]
        x2, y2, _ = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


# vanilla winding
vanilla = nmg9.NavMesh.parse(rnm1.read(SCENE + r"\navmesh.bin"))
areas = [signed_area(vanilla, f) for f in vanilla.faces[:2000]]
pos = sum(1 for a in areas if a > 0)
print(f"vanilla winding: {pos}/{len(areas)} faces CCW (signed area > 0)")

params = read_terrain_params(SCENE + r"\scene.xscene")
terr = Terrain.load(SCENE + r"\terrain.bin")
grid = params.decode_heights(terr.heightmap_grid((params.node_dim_x, params.node_dim_y)))

mesh = generate.from_heightmap(
    grid, params.world_size_x, params.world_size_y,
    cell_size=4.0, max_slope_deg=40.0,
    region=(900.0, 1000.0, 1100.0, 1200.0),
)
print(f"generated: v={len(mesh.vertices):,} e={len(mesh.edges):,} f={len(mesh.faces):,}")
gareas = [signed_area(mesh, f) for f in mesh.faces]
print(f"generated winding: {sum(1 for a in gareas if a > 0)}/{len(gareas)} CCW")

payload = mesh.serialize()
again = nmg9.NavMesh.parse(payload)
assert again.serialize() == payload
out = str(Path(__file__).parent / "_tmp" / "generated_navmesh.bin")
rnm1.write(out, payload)
assert rnm1.read(out) == payload
print(f"generated navmesh serializes + containers OK -> {out}")
print("GENERATOR CHECKS PASSED")
