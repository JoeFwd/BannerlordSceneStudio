# Siege-Capable Castle Scene — Design Document (blscene)

**Goal:** let a follow-up agent programmatically BUILD a besiegeable Bannerlord
castle scene (no in-game editor) using the blscene composer, and register it so a
campaign siege loads and runs without crashing.

**Target game version: v1.4** — every reference file/symbol below comes from
`D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord` (v1.4 install) and
the `mcp__bannerlord-search-1_4_6` decompiled source. The v1.2 install is untouched.

Evidence sources: `corpus.json` (568 scenes), the blnav navmesh reader
(`blnav/nmg9.py`, `blnav/rnm1.py`), the DADG `settlements.xml`, and decompiled
managed source. Concrete scene files inspected:
`SandBoxCore/SceneObj/khuzait_castle_siege_001`,
`SandBox/SceneObj/sturgia_castle_siege_001`,
`SandBoxCore/SceneObj/{empire_castle_b, vlandia_castle_a}`,
`DellarteDellaGuerraScenes/SceneObj/{Dartmouth_castle, Clun_castle}`.

---

## A. Settlement scene inventory

### Module distribution (corpus)
SandBoxCore 202, SandBox 195, DellarteDellaGuerraScenes 86, Native 80,
StoryMode 4, DellarteDellaGuerraMap 1.

### Classification by name convention
- **Towns** (56): `<culture>_town_<x>` in SandBoxCore (the campaign town-visit / siege
  scenes) plus interior sub-scenes in SandBox. Siege-capable town variants are marked
  by name suffix `_siege` (e.g. `empire_town_j_siege`).
- **Castles** (62): `<culture>_castle_<x>` (SandBoxCore, the campaign siege scenes);
  `*_castle_keep_a_lN_interior` and `castle_hall_*` are **interiors only**, not
  siege-capable; `meeting_castle_*` are conversation stages, not siege-capable.
- **Villages** (121): `<culture>_village_<x>`; raid variants suffixed `_raid` /
  `_navalraid`. Not siege targets.
- **MP siege** (16): `mp_siege_map_*` (Native) — multiplayer, different spawn rules.

### The Settlement → scene binding (the load contract)

Campaign siege entry (`TaleWorlds.CampaignSystem.Siege`, `...Encounters`):
```
CampaignMission.OpenSiegeMissionWithDeployment(
    besiegedSettlement.LocationComplex.GetLocationWithId("center").GetSceneName(wallLevel), ...)
```
where `wallLevel = Town.GetWallLevel()` (0-3, set by `building_castle_fortifications`
level). `Location.GetSceneName(upgradeLevel)` returns `_sceneNames[upgradeLevel]`,
falling back to `_sceneNames[0]` if empty.

In `DellarteDellaGuerraMap/ModuleData/settlements.xml` each castle binds the `center`
location scene per wall level:
```xml
<Location id="center" scene_name="Framlingham_castle"
          scene_name_1="Framlingham_castle" scene_name_2="Framlingham_castle"
          scene_name_3="Framlingham_castle" />
```
`scene_name` = level 0, `scene_name_1..3` = wall levels 1-3. **This one line is the
test hook**: rebinding `scene_name_N` of ONE castle's `center` location to our
generated scene makes that castle besiegeable with our scene, no C# changes.

**Wall level = which scene loads.** `building_castle_fortifications` level in the same
settlement entry drives `GetWallLevel()`. Lowest-fortification DADG castles (level 1,
so siege loads `scene_name_1`): **`dadg_Clare_castle_comp`, `dadg_Gloucester_castle_comp`**
— preferred rebind targets (a level-1 wall castle needs the fewest breach variants).

### DADG castle scenes — all are siege-capable

Every DADG `*_castle` scene in `DellarteDellaGuerraScenes` carries the **full siege
entity set** (verified across Dartmouth, Clun, Piel, Brough, Corfe, Framlingham,
Caister, Carisbrooke, Stokesay, Eilan_donan, Brough am, Brough). None is scenery-only;
`castle_hall_*` are interiors, not exterior siege scenes. Entity counts 697-2061
(Dartmouth 913, Clun 817) — an order of magnitude smaller than native (1671-4280).

Common skeleton present in (nearly) every siege-capable scene (top-level prefab
families, from corpus + xscene):
- `strategic_archer_point`, `strategic_attacker_archer_position`,
  `defender_archer_position`, `attacker_archer_position` (AI cover points, hundreds)
- `defender_boundry`, `attacker_boundry` (side boundary volumes)
- `strategyCameraAttacker` / `strategyCameraDefender` tags (deployment camera)
- `siege_ladder_<N>m_spawner`, `siege_tower_<N>m_spawner`, `batteringram_a_spawner`
  (the functional siege-weapon spawners — **native prefabs**)
- ballista/mangonel/trebuchet `_spawner` (defender engines)
- `WallSegment` script components on wall meshes; `CastleGate` gate prefabs
- `<path>` elements named `tower_a/tower_b` (siege-tower routes), `batterin` (ram route)
- `sp_*` NPC prefabs (town-visit population; sally-out `sp_sally_out_ambush_battle_set`)

---

## B. Siege mission hard requirements (managed source, v1.4.6)

Ranked HARD-REQUIRED (null-ref / non-functional siege if missing) vs degraded.

### HARD-REQUIRED
1. **Terrain + navmesh that spans attacker camp → walls → interior.** Agents path on
   the navmesh; no connected navmesh = no movement, immediate AI failure. (See C.)
2. **At least one `WallSegment` script per defended side.**
   `Mission.ActiveMissionObjects.FindAllWithType<WallSegment>().FirstOrDefault(ws =>
   ws.DefenseSide == side)` drives deployment-point association and the breach system.
   `WallSegment : SynchedMissionObject, IPointDefendable, ICastleKeyPosition`. The
   campaign passes `SettlementWallSectionHitPointsRatioList` to
   `OpenSiegeMissionWithDeployment`; the mission maps ratios onto wall segments to set
   breached state. Missing wall segments → deployment points cannot resolve a side.
3. **`CastleGate`** (`CastleGate : UsableMachine, IPointDefendable, ICastleKeyPosition`).
   Provides `GetGateNavMeshId()` (default field `GateNavMeshId = 7`) and toggles the
   gate faces via `Scene.SetAbilityOfFacesWithId(GetGateNavMeshId(), enabled)`. The
   defender AI treats it as a key position (`OverTheWallNavMeshID => GetGateNavMeshId()`).
4. **Primary attacker siege weapon reachable to a wall.** Deployment points require a
   primary weapon (`SiegeLadder` / `SiegeTower` / `BatteringRam`, all implement
   `IPrimarySiegeWeapon`). They come from the **spawner** script components
   (`SiegeLadderSpawner`, `SiegeTowerSpawner`, `BatteringRamSpawner` in
   `TaleWorlds.MountAndBlade.Objects.Siege`), which `AssignParametersFromSpawner(...)`
   onto the spawned weapon. Each ladder/tower carries an `OnWallNavMeshId` that MUST
   match a real navmesh face id (see C) or agents will not climb.
5. **Deployment points.** `Mission.ActiveMissionObjects.FindAllWithType<DeploymentPoint>()`;
   `DeploymentPoint : SynchedMissionObject`. Each resolves a type (Ranged / Breach /
   BatteringRam / TowerLadder) from the weapons under it. In the DADG/native scenes
   these are the `siege_deployment_placeholder_part_a/_b` prefabs plus the spawners.
6. **Spawn side tagging.** `SiegeSpawnFrameBehavior.Initialize` collects
   `SpawnPoints.Where(x => x.HasTag("attacker"))` and `...HasTag("defender")`; multiplayer
   uses `sp_zone_<i>` grouping, but **campaign sieges do NOT use `sp_zone_`** (neither
   khuzait nor Dartmouth has any) — campaign spawn is path/deployment-based via the
   `Side="Attacker"/"Defender"` script variables on spawn entities and the initial
   spawn `<path>`. At minimum, defender and attacker spawn frames must resolve:
   `Mission.GetInitialSpawnPathDataOfSide(side)` must return a valid path.
7. **Deployment/strategy camera.** `Mission.Scene.FindEntityWithTag("strategyCameraAttacker")`
   / `"strategyCameraDefender"` — used by the deployment screen; both present in every
   siege scene. A `?? null` fallback exists but the OoB deployment UI degrades badly.

### DEGRADED-BUT-LOADS
- `strategic_archer_point` / `*_archer_position` / cover points: AI plays worse but no
  crash if sparse.
- Sally-port door (`sally_door_a`, tag `inner_gate`) — only needed for sally-out
  missions; a plain assault loads without it.
- Ballista/mangonel/trebuchet defender `_spawner`s — optional defender engines.
- Ambush indicator / `sp_sally_out_ambush_battle_set` — only the sally-out ambush path.
- `merlon` indestructible tags — cosmetic/AI-cover refinement.

### Town-visit (walkable town) — cheaper fallback milestone
`CampaignMission.OpenTownVisitMission` / the "center" location at wall level with no
siege. Hard requirements shrink to:
- A navmesh the player + wandering NPCs can walk.
- `spawnpoint_player` (tag) for the player start; `Passage` entities for doors between
  locations; usable points tagged `npc_common` for townsfolk
  (`MissionAgentHandler.FindUnusedPointWithTagForAgent(agent, "npc_common")`).
- No wall/gate/siege-weapon logic runs. **This is the recommended first
  green-light** before attempting siege.

### Where requirements live (script components on entities)
- `SiegeLadderSpawner` editable variables (xscene `<variable>` on the spawner
  `<game_entity>`): `SideTag`, `TargetWallSegmentTag`, **`OnWallNavMeshId`**,
  `DownStateRotationRadian`, `UpperStateRotationRadian`, `BarrierTagToRemove`,
  `IndestructibleMerlonsTag`, `RemoveOnDeployTag`. These are passed into the ladder via
  `AssignParametersFromSpawner`.
- `CastleGate`: `GateNavMeshId` (default 7). Toggles those faces open/closed.
- `WallSegment`: `DefenseSide`, its `GetNavmeshFaceIds`, breach faces.
- Validation the editor itself enforces (from source, so our writer must obey):
  `OnWallNavMeshId` **must not be -1, 0, or have ones-digit == 1** in a singleplayer
  scene, and **must be unique per ladder**
  (`"OnWallNavMeshId must not be shared with any other siege ladder."`).

---

## C. Navmesh design conventions (blnav on real scenes)

The blnav NMG9 face record exposes `g3` (the dynamic navmesh face **id**,
`SetAbilityOfFacesWithId` target) and `g5` (island/group). Measured face data:

| scene | faces | distinct g3≠0 | g3 range (≠0) | g5 islands | g6=1 faces |
|---|---|---|---|---|---|
| khuzait_castle_siege_001 | 82,490 | 29 | 1–669 | 12 | 0 |
| sturgia_castle_siege_001 | 90,128 | 29 | 1–531 | 9 | 0 |
| empire_castle_b | 188,606 | 27 | 1–531 | 12 | 0 |
| vlandia_castle_a | 29,792 | 26 | 1–531 | 6 | 0 |
| **Dartmouth_castle (DADG)** | **6,138** | **28** | **1–511** | **2** | **2,535** |
| **Clun_castle (DADG)** | **6,328** | **22** | **1–511** | **4** | **2,866** |

### The dynamic navmesh-id (g3) convention — CONFIRMED end-to-end
- **`g3 = 1`**: "inside the castle" — the dominant face group (thousands of faces).
  The AI counts units inside via `Formation.CountUnitsOnNavMeshIDMod10(1, ...)`, i.e.
  `faceId % 10 == 1`. This is why **ladder/gate ids may never end in 1** (they'd be
  miscounted as "inside").
- **`g3 = 2`**: a second common walkable group (hundreds of faces) — typically the
  ground/approach or the wall-walkway ability group.
- **`g3 = 7`**: default `CastleGate.GateNavMeshId` (gate faces toggled open/closed).
- **`g3` in the ~100–670 band, small counts (1–40 faces each)**: the per-siege-weapon
  drop faces and gate/breach groups the xscene scripts reference. These are almost
  always `...01` or `...11` (ones-digit ≠ 1 rule is about the *mod-10==1* case; note
  `x01`, `x11` end in 1 only when the whole value %10==1 — the observed ladder ids like
  `201, 211, 301, 311` have %10 ∈ {1} for `x01/x11`… see below).

**Direct wiring proof (Dartmouth):** the xscene siege-ladder spawners carry
`OnWallNavMeshId = 211, 311, 201, 301` and the navmesh has faces with exactly
`g3 = 201, 211, 301, 311` (1–2 faces each). Each ladder marks its drop faces via
`Scene.MarkFacesWithIdAsLadder(OnWallNavMeshId, true)` and enables them on deploy via
`Scene.SetAbilityOfFacesWithId(OnWallNavMeshId, enabled)`. So **the number in the
xscene script must equal a `g3` face-id we author into the navmesh.** (Note: the
editor-warning rule literally checks `OnWallNavMeshId % 10 == 1` is forbidden; the
observed shipping values `201/211/301/311` have `%10 == 1`, which contradicts the
warning text — the warning is a soft editor check, the runtime does not crash on it.
Safe policy: pick ids whose ones-digit is NOT 1 AND not 0, e.g. `202, 302, 402`,
to avoid the warning entirely and stay clear of the `%10==1` "inside" bucket.)

### Global id constants (source)
- `MaxNavMeshId = 1000000`.
- Runtime-allocated dynamic ids start at `_nextDynamicNavMeshIdStart = 1000010`,
  incrementing by 10 (`GetNextDynamicNavMeshIdStart`). So hand-authored scene ids live
  well below 1,000,000 (the observed 1–669 band); the ≥1,000,010 range is reserved for
  runtime allocation — **do not author faces there.**
- `g5` (island/group): small integers, negative for stair/wall/walkway islands,
  large positive for ground zones. **Disconnected islands ARE allowed** (stairs,
  ramparts, wall-tops are separate g5 groups joined only where geometry meets).

### Wall-walkway / rampart connectivity
Ramparts connect to the ground through **stair faces** (their own g5 island, joined at
the stair foot/top). Ladders and the gate provide the *dynamic* connections (faces that
start disabled and are enabled on deploy). So the static navmesh is: ground ring +
walkway ring + stairs, plus a small set of pre-cut ladder-drop faces (g3 = the ladder
ids) that sit at each wall top and are toggled on when a ladder deploys.

### What the generator needs beyond `from_heightmap`
`from_heightmap` gives the ground sheet only. For a siege we must **hand-author**:
1. A **walkway ring** on top of the walls (a strip mesh following the wall tops).
2. **Stair faces** joining walkway to ground (one per stair prefab), as their own g5.
3. **Ladder-drop faces** at each wall top: 1–3 small faces per ladder, `g3 =` that
   ladder's `OnWallNavMeshId`, initially the ability bit that the ladder toggles.
4. **Gate faces** spanning the gate opening: `g3 = 7` (or the gate's `GateNavMeshId`).
5. Set the interior ground faces to `g3 = 1` so the "inside castle" count works.

blnav already supports authoring faces (`add_face`, `set_face_attributes`,
`rebuild_edges`), and `nmg9.Face.g3/g5/g6` are directly settable. Typical DADG target:
**~6,000 faces total** (Dartmouth/Clun scale), ~25 distinct g3 ids, 2–4 g5 islands.
Note DADG scenes set **`g6 = 1` on ~45% of faces** (native uses 0); g6 appears to be a
walkable-surface/roof flag. Match the DADG convention when harvesting DADG geometry.

---

## D. DADG-assets-only feasibility

**Finding: "DADG assets" = mostly native base-game prefabs.** DADG castle scenes are
assembled from:

- **Functional siege prefabs — 100% native, always shipped with the base game:**
  `siege_ladder_7m_spawner`, `siege_ladder_8m_spawner`, `siege_ladder_11m_spawner`,
  `siege_tower_9m_spawner`, `batteringram_a_spawner`,
  `empire_castle_gate_inner_l2`, `aserai_castle_gate_outer_l1`,
  `siege_deployment_placeholder_part_a/_b`, `strategic_archer_point`,
  `strategic_attacker_archer_position`, `defender_boundry`, `attacker_boundry`,
  ballista/mangonel/trebuchet `_spawner`, `sally_door_a`, `sp_*` NPCs.
- **DADG-specific STRUCTURAL meshes** (the visual wall/tower/keep, in
  `DellarteDellaGuerra*` .tpac):
  `dadg_english_fort_big_castle_wall_a` (+`_b`, `_broken`),
  `dadg_english_fort_big_castle_wall_gate_smaller`,
  `dadg_norman_english_fort_castle_wall_tower_b`,
  `dadg_fort_english_round_tower_e`, `dadg_english_modern_church_tower`,
  `dadg_fort_english_stairs_tower_b`, `dadg_english_stairs`, `dadg_fort_stairs_a`,
  `dadg_pavise_siege_wall_with_cutout`, plus native `european_castle_wall_fence_a/_b`.

So "use only DADG assets" is satisfied automatically: the **functional** siege objects
are native (guaranteed present), and the **visual** castle is DADG's own fort meshes,
already used by every DADG castle.

### Minimal v1 parts list (a level-1 wall castle)
| role | prefab (source) | count |
|---|---|---|
| Wall segment (normal) | `dadg_english_fort_big_castle_wall_a` | 4-6 |
| Wall segment (breach variant) | `dadg_english_fort_big_castle_wall_a_broken` | 1-2 |
| Gatehouse w/ working gate | `dadg_english_fort_big_castle_wall_gate_smaller` + `aserai_castle_gate_outer_l1` (CastleGate) | 1 |
| Corner towers | `dadg_norman_english_fort_castle_wall_tower_b` / `dadg_fort_english_round_tower_e` | 2 |
| Keep | `dadg_english_modern_church_tower` (or any DADG keep mesh) | 1 |
| Wall stairs | `dadg_fort_english_stairs_tower_b` / `dadg_english_stairs` | 2 |
| Attacker ladders | `siege_ladder_7m_spawner`, `siege_ladder_11m_spawner` | 2-3 |
| Attacker siege tower dock | `siege_tower_9m_spawner` | 1-2 |
| Ram lane | `batteringram_a_spawner` | 1 |
| Deployment placeholders | `siege_deployment_placeholder_part_a/_b` | per weapon |
| Cover / AI points | `strategic_archer_point`, `*_archer_position` | ~dozens |
| Boundaries | `defender_boundry`, `attacker_boundry` | ~8 each |
| Deployment cameras | entities tagged `strategyCameraAttacker/Defender` | 1 each |

---

## Build plan (v1)

### Recommended approach: HARVEST the whole DADG castle ring as one cluster

`blscene/harvest.py` transplants a world-space rectangle's **entire top-level
`<game_entity>` subtree verbatim** — children, transforms, `<script_component>` data,
and `<path>` elements are preserved. This means we can lift a complete, already-working
DADG castle (walls + gate + towers + all spawners + all `OnWallNavMeshId` values +
strategic points + cameras) as ONE cluster onto generated terrain. This sidesteps
re-deriving the entire siege entity graph by hand.

Reference/oracle scene (structural simplest full-siege castle): **`Clun_castle`**
(817 top-level entities, 6,328 navmesh faces, keep-heavy compact layout) or
**`Dartmouth_castle`** (913 entities, 6,138 faces) — both DADG, both an order of
magnitude smaller than any native siege scene while carrying the complete siege set.
Among **native** scenes the simplest full-siege reference is **`khuzait_castle_siege_001`**
(1,004 entities — the smallest native scene that still has ladders+towers+ram+gate+
wall segments+deployment placeholders), useful as the canonical "what a native siege
looks like" oracle.

Pipeline:
1. `SceneBuilder` (blscene/compose.py) → generate flat-ish terrain sized to the castle
   footprint (Clun/Dartmouth are compact) via `from_heightmap`.
2. `harvest.py` → harvest the Clun (or Dartmouth) castle cluster + its terrain patch +
   flora, anchored on the new terrain. Keep the cluster un-rotated first (rotation
   complicates the navmesh transplant).
3. **Navmesh**: for v1, harvest/copy the source castle's `navmesh.bin` too and stitch
   it into the generated ground navmesh — the source g3 ids already match the harvested
   script `OnWallNavMeshId`s. Weld the castle navmesh island(s) to the generated ground
   sheet at the gate/approach so attacker faces (g3=2 approach) connect to the ladder
   drop faces (g3=201/211/...) and interior (g3=1). Use blnav `add_face` to bridge and
   `rebuild_edges` to fix adjacency. Preserve g5 islands and g6 flags from source.
4. Write terrain.bin (ZGR6), navmesh.bin (RNM1/NMG9), flora.bin, scene.xscene.
5. Copy `atmosphere.xml` + `prt_data.bin` from the source castle scene.

### Entity / script / tag checklist to satisfy siege load
- [ ] ≥1 `WallSegment` script per side with a `DefenseSide`.
- [ ] `CastleGate` prefab with `GateNavMeshId` matching a navmesh g3 group.
- [ ] ≥1 attacker `siege_ladder_*_spawner` with unique `OnWallNavMeshId` matching a
      navmesh g3 face group; `SideTag` + `TargetWallSegmentTag` pointing at a real
      `WallSegment` tag.
- [ ] ≥1 `siege_tower_*_spawner` with `SideTag` and a `<path>` (tower_a/tower_b route).
- [ ] `batteringram_a_spawner` with a `<path>` (batterin route) to the gate.
- [ ] `siege_deployment_placeholder_part_a/_b` per weapon (deployment points).
- [ ] Entities tagged `strategyCameraAttacker` and `strategyCameraDefender`.
- [ ] `defender_boundry` / `attacker_boundry` volumes.
- [ ] A resolvable initial spawn path per side (`Side="Attacker"/"Defender"` entities
      / spawn `<path>`).
- [ ] `strategic_archer_point` / `*_archer_position` cover points (degraded if sparse).
- [ ] Navmesh: interior faces g3=1, gate faces g3=GateNavMeshId, ladder-drop faces
      g3=each ladder's OnWallNavMeshId, connected ground↔walkway↔stairs.

### Registration / test route (least invasive)
1. Deploy the generated scene folder to
   `DellarteDellaGuerraScenes/SceneObj/<new_scene>/` (all 6 files + atmosphere/prt).
2. In `DellarteDellaGuerraMap/ModuleData/settlements.xml`, temporarily rebind ONE
   low-fortification castle's `center` location:
   change `dadg_Clare_castle_comp` (or `dadg_Gloucester_castle_comp`, both wall level 1)
   `<Location id="center" scene_name_1="<new_scene>" ...>`. Because these are level-1
   forts, the siege loads `scene_name_1`, so only that one attribute matters.
3. In a campaign, besiege that castle. First validate the **town-visit** path (walk the
   scene) before triggering the assault, to isolate navmesh/geometry crashes from
   siege-logic crashes.
4. Revert the settlements.xml edit after testing. (Do NOT commit.)

---

## Risk list (ordered by crash likelihood)

1. **Disconnected / missing navmesh between attacker camp and walls** → agents can't
   path, AI asserts / soft-locks; the single highest-probability failure. Mitigate by
   welding the harvested castle navmesh to the generated ground sheet and verifying one
   connected component from spawn → ladder-drop → interior (g3=1).
2. **`OnWallNavMeshId` / `GateNavMeshId` not present as a navmesh g3 face id** →
   ladders/gate deploy but agents never cross; possible null path assert. Keep the
   harvested navmesh and the harvested script values together (they already match).
3. **No `WallSegment` for a besieged side** → deployment-point side resolution returns
   null, `SettlementWallSectionHitPointsRatio` mapping throws. Ensure each ring side
   has a wall segment with a `DefenseSide`.
4. **Missing initial spawn path / spawn side entities** → `GetInitialSpawnPathDataOfSide`
   / spawn frame null-ref at troop spawn. Preserve the harvested spawn paths and
   `Side`-tagged entities.
5. **Missing `strategyCameraAttacker/Defender` or deployment placeholders** → deployment
   screen / OoB UI crash or empty deployment. Preserve both cameras and the
   `siege_deployment_placeholder_part_*` set.

(Lower-severity: mismatched wall-level scene binding loads a fallback scene; missing
`prt_data.bin`/`atmosphere.xml` degrades visuals but usually loads; missing merlon /
ballista spawners only weaken defender AI.)

---

## Quick reference: simplest siege scenes
- **Simplest full-siege reference overall (build oracle): `Clun_castle` / `Dartmouth_castle`**
  (DADG, ~6,100–6,300 navmesh faces, ~817–913 entities, complete siege set, DADG
  fort meshes + native functional prefabs).
- **Simplest NATIVE siege reference: `khuzait_castle_siege_001`** (1,004 entities —
  smallest native scene with the full ladder/tower/ram/gate/wall-segment set).
