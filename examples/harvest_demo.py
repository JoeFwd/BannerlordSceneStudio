"""Harvest / composite demo.

Builds a demo battle scene into a TEMPORARY directory (never the game folder):

  * synthetic rolling terrain (6x6 nodes, 100 m each = 600 x 600 m)
  * one terrain patch harvested from a native scene, stamped with a smooth blend
  * one entity cluster (rock cliffs) harvested via a prefab regex from Durham
  * flora transplanted from a DIFFERENT scene (empire_village_002), showing that
    terrain / entities / flora can each come from their own source scene

Run::

    python examples/harvest_demo.py

Prints a summary of what was harvested from where, then the output scene path.
The scene is left on disk under the system temp dir for inspection.
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blscene.compose import SceneBuilder
from blscene.harvest import (
    harvest_terrain_patch,
    apply_terrain_patch,
    harvest_entities,
    place_entities,
    harvest_flora,
    place_flora,
)
from blnav.terrain import Terrain
from blnav.flora import Flora

GAME = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
DURHAM = GAME + r"\DellarteDellaGuerraScenes\SceneObj\Durham"
VILLAGE = GAME + r"\SandBoxCore\SceneObj\empire_village_002"
BATTLE_TEMPLATE = GAME + r"\SandBoxCore\SceneObj\battle_terrain_a"

NODE_SIZE = 100.0
H = W = 6 * 128 + 1  # 769 -> 600 x 600 m world


def _rolling_terrain() -> np.ndarray:
    xs = np.linspace(0, 3.0, W, dtype=np.float32)
    xx, yy = np.meshgrid(xs, xs)
    return (35.0 + 8.0 * np.sin(xx) * np.cos(yy)).astype(np.float32)


def main() -> None:
    if not (os.path.isdir(DURHAM) and os.path.isdir(VILLAGE)
            and os.path.isdir(BATTLE_TEMPLATE)):
        print("Native scenes not found; this demo needs Bannerlord v1.4 installed.")
        return

    # --- Harvest (each kind from its own source scene) ---
    # Durham's rock_cliff_* props cluster around (560-640, 380-430).
    rocks = harvest_entities(DURHAM, 560.0, 380.0, 640.0, 430.0, prefab_re="rock")
    # A hilly patch of Durham terrain to transplant.
    patch = harvest_terrain_patch(DURHAM, 500.0, 500.0, 640.0, 640.0)
    # Flora from a village scene (reeds/shrubs/trees) around a dense 100 m rect.
    flora = harvest_flora(VILLAGE, 600.0, 650.0, 700.0, 750.0)

    # --- Compose ---
    heights = _rolling_terrain()
    heights = apply_terrain_patch(
        heights, patch, x=250.0, y=250.0, node_size=NODE_SIZE, blend_margin=25.0
    )

    builder = SceneBuilder.new_battle(
        "harvest_demo", heights, node_size=NODE_SIZE, template_dir=BATTLE_TEMPLATE
    )
    place_entities(builder, rocks, x=300.0, y=300.0, rotation_deg=30.0)
    place_flora(builder, flora, x=400.0, y=400.0, rotation_deg=15.0)

    out_dir = tempfile.mkdtemp(prefix="harvest_demo_")
    scene_dir = builder.build(out_dir)

    # --- Verify by reloading the built outputs ---
    terrain = Terrain.load(os.path.join(scene_dir, "terrain.bin"))
    grid = terrain.heightmap_grid((6, 6))
    built_flora = Flora.load(os.path.join(scene_dir, "flora.bin"))

    print("=== Harvest demo summary ===")
    print(f"terrain patch : {patch.heights.shape} samples from {patch.source}")
    print(f"                (spacing {patch.spacing:.3f} m, "
          f"{patch.world_w:.0f} x {patch.world_h:.0f} m)")
    print(f"entities      : {len(rocks)} rock props from {rocks.source}")
    print(f"flora         : {len(flora)} records from {flora.source}")
    print()
    print(f"built scene   : {scene_dir}")
    print(f"  terrain.bin : reloaded grid {grid.shape}")
    print(f"  flora.bin   : {len(built_flora.records)} records written")
    print()
    print("(temp scene left on disk for inspection; delete it when done)")


if __name__ == "__main__":
    main()
