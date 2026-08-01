"""Generate dadg_gen_siege_castle: the first programmatically-composed
siege-capable Bannerlord castle scene built with the blscene composer.

Approach (see docs/siege-scene-design.md, "reuse donor xscene wholesale"):
  We clone the DADG donor castle **Clun_castle** verbatim with
  ``SceneBuilder.from_scene``.  This is the fewest-moving-parts route and the
  one with the lowest crash risk:

    * The donor's REAL terrain (terrain.bin, 8x8 nodes @100 m, uniform level-7
      heightmap, an authentic hill/approach) is copied byte-for-byte — NOT flat
      synthetic ground.
    * The donor navmesh.bin is copied byte-for-byte, so every scripted navmesh
      id (ladder OnWallNavMeshIds 211/311/212/312, inside g3=1, approach g3=2)
      stays perfectly aligned with the entities that reference it.  Nothing is
      re-anchored, so no navmesh transplant / re-projection is needed and risks
      #1-#5 of the design doc (disconnected navmesh, id mismatch, missing wall
      segment / spawn path / camera) cannot be introduced by us — the clone is
      identical to a shipping, working siege scene.
    * Every HARD-REQUIRED siege entity (WallSegments x39, 2x CastleGate, 4x
      SiegeLadderSpawner, 2x SiegeTowerSpawner, BatteringRamSpawner,
      siege_deployment_placeholder_part_a/_b, strategycamera{attacker,defender}
      tags, defender_boundry/attacker_boundry, spawn paths) rides along verbatim
      inside the cloned xscene.

Donor choice: Clun_castle over Dartmouth_castle because Clun carries BOTH
``siege_deployment_placeholder_part_a`` and ``_part_b`` (Dartmouth ships only
``_part_b``) and the full WallSegment set, giving the most complete deployment
graph.  Both donors have uniform level-7 terrain and matching ladder navmesh ids.

Output files (matching the donor's authored set, editor/prt data omitted):
  scene.xscene, terrain.bin, navmesh.bin, flora.bin, atmosphere.xml, references.txt
Output: DellarteDellaGuerraScenes/SceneObj/dadg_gen_siege_castle/

Seeded/reproducible: this is a deterministic verbatim clone (no RNG); rerunning
produces byte-identical output for terrain/navmesh/flora and an xscene whose only
difference from the donor is the ``name`` attribute (dadg_gen_siege_castle).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.compose import SceneBuilder

GAME = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
DONOR = GAME + r"\DellarteDellaGuerraScenes\SceneObj\Clun_castle"
OUT_DIR = GAME + r"\DellarteDellaGuerraScenes\SceneObj"
SCENE_NAME = "dadg_gen_siege_castle"


def main() -> None:
    builder = SceneBuilder.from_scene(DONOR, SCENE_NAME)
    # Rename the scene so the loaded scene identity matches its folder name.
    builder._scene._root.set("name", SCENE_NAME)

    scene_dir = builder.build(OUT_DIR)
    print(f"Scene written to: {scene_dir}")
    for p in sorted(Path(scene_dir).iterdir()):
        if p.is_file():
            print(f"  {p.name}  ({p.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
