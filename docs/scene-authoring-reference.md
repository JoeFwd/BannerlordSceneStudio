# Bannerlord Scene Authoring Reference

## Scene File Organization

**SceneObj vs SceneEditData** (moddocs: asset-types/overriding_scenes_prefabs)
- **SceneObj**: Runtime scene files required for gameplay/client mode
- **SceneEditData**: Editor-only files needed for scene editing operations
- Scene registration works by filename; overriding existing scenes replaces default game content
- Caution: Overriding prefabs may break existing scripts if entity hierarchy changes

**Editor-only data — the two-copy rule** (verified 2026-08-17 on `dadg_joust_v3`)

A scene stores its content twice, and *only the runtime copy is what the game reads*:

| Concern | Editor source | Runtime |
|---|---|---|
| Terrain | `SceneEditData/<scene>/terrain_ed.bin` — magic `OK01` | `SceneObj/<scene>/terrain.bin` — magic `ZGR6RTRN` |
| Entities | `<editor_data>` + per-entity `<edit_mode_data>` in `scene.xscene` | every other node in `scene.xscene` |

Tools that write only `SceneObj/` therefore produce a scene that **plays correctly but is
stale or fatal in the editor**. The two terrain formats are unrelated encodings; this repo
writes `ZGR6` only (`blnav/terrain_write.py`), so `terrain_ed.bin` stays whatever donor copy
was seeded. Consequences when such a scene is opened in the Modding Kit:

- The editor renders the **donor** terrain, not the generated one.
- **Saving terrain in the editor regenerates `terrain.bin` from `terrain_ed.bin` and destroys
  the generated terrain.** Back up `terrain.bin` before opening a composed scene.

**Group-object invariant** — every `edit_mode_data/@group_object_guid` must be declared as a
`editor_data/group_objects/group_object/@guid` **in the same scene**. An undeclared GUID makes
the editor dereference a null group on scene load:

```
Faulting application: TaleWorlds.MountAndBlade.Launcher.exe (bin\Win64_Shipping_wEditor)
Faulting module:      TaleWorlds.Native.dll
Exception code:       0xc0000005 (access violation)
```

The runtime never reads `edit_mode_data`, so the scene loads and plays perfectly — the defect
is invisible until someone opens the editor. Copying entity subtrees between scenes drags
`edit_mode_data` along with them, but `<editor_data>` is a *single top-level node* that merge
code overwrites wholesale instead of unioning. Multi-donor composition is the trigger.

Validate before shipping any composed or merged scene:

```python
import xml.etree.ElementTree as ET
r = ET.parse("scene.xscene").getroot()
declared = {g.get("guid") for g in r.iter("group_object")}
used = {e.get("group_object_guid") for e in r.iter("edit_mode_data")} - {None}
assert not (used - declared), f"orphan group guids: {used - declared}"
```

Fix by **declaring the missing group** (preserves the grouping), not by stripping the
attribute. Note `scene.xscene` is CRLF, tab-indented, self-closing tags with no space before
`/>`, and has no BOM — `ElementTree.tostring` / .NET `OuterXml` re-serialize and will not match
the on-disk bytes, so anchor byte-level edits on the raw text.

**Terrain Structure** (moddocs: editor/scene-editor/terrain_creation)
- Node-based system with configurable node count, resolution, and size
- Import/export supports 8-bit and 16-bit heightmaps (PNG/RAW), materialmaps (grayscale), debris, flowmap, vegetation, bedrock layers
- Node resolution individually adjustable for optimization

## Scene Type Requirements

**Arena Scenes** (moddocs: authoring-mission-scenes)
- Minimal terrain; fewer nodes than other scene types
- Smaller overall terrain scale appropriate for confined combat

**Village Scenes** (moddocs: authoring-mission-scenes)
- Requires navigation mesh (triangles and quads) for AI pathfinding and global illumination
- Navmesh faces must be proximate to physics geometry
- Spawn points: sp_player_outside (first entry, away from entrance), sp_player (near gates)

**Siege Scenes** (moddocs: authoring-mission-scenes)
- Requires siegeable walls with solid and broken stages
- Parent entity tags for siege equipment: wall_segment_left, wall_segment_right, etc.
- Navmesh changes dynamically between intact and breached wall states

**Hideout Scenes** (moddocs: authoring-mission-scenes)
- Fighting-mission-only; strict one-way layout design
- Navigation mesh similar to village scenes (triangles and quads for pathfinding)

**Multiplayer Scenes** (moddocs: authoring-mission-scenes, referenced but no specific requirements documented)

## Required Entities & Spawn Points

**Spawn Point Debug Tool** (moddocs: authoring-mission-scenes)
- Validates scene necessities: search "spawnpointdebug" in entity browser
- Three verification tabs: Scene Basic Information, Entity Check (required spawners/NPC points/passages), Navmesh validation
- Each scene type has own baseline requirements to run without crashing

**Spawn Points** (moddocs: authoring-mission-scenes)
- sp_player_outside: Initial entry point; must be positioned away from city entrances
- sp_player: Alternative spawn near gates
- Navmesh polygons must encompass all spawn point pivot points (moddocs: editor/scene-editor/nav_mesh)

## Entities & Components

**Entity Fundamentals** (moddocs: editor/scene-editor/creating_entity)
- Game entities are basic building blocks; containers for meshes, lights, decals, script behaviors
- Hierarchical relationships supported; child entities position relative to parents
- Create empty entity via Add Empty Entity button, then attach components

**Core Components**:
- **Mesh**: Visible geometry; selected from available mesh assets
- **Light**: Illuminates scenes; adjustable radius, intensity, color, dynamic/static shadows; Tiled Deferred Rendering for efficiency
- **Particle System**: Volumetric effects (fire, smoke, splash) via small image/mesh simulation
- **Decal**: Surface details (documentation minimal)
- **Script**: C# behaviors with full entity/scene access; customizable via Entity Inspector parameters
- **Physics**: Collision and physics bodies (referenced but not detailed)

## Prefabs & Entity Reuse

**Prefab System** (moddocs: asset-management/asset-types/prefabs)
- Reusable templates with dynamic connection to source; updates propagate to placed instances
- Nearly all mission objects and scene props are prefabs in Bannerlord
- Connection breaks if: mesh colors, child transforms, or script parameters are modified in scene
- Connection completely severs if: addition operations (add meshes, particles, lights, child entities, script components)

## Terrain, Flora, Heightmaps

**Terrain Import/Export** (moddocs: editor/scene-editor/terrain_creation)
- Supports 8-bit and 16-bit heightmap formats (PNG or RAW)
- Materialmaps: 8-bit grayscale for layer assignment (debris, flowmap, vegetation, bedrock layers)
- Node resolution individually adjustable in Node Properties panel

**Flora** (moddocs: asset-management/implementing-flora reference exists but detailed content not retrieved)
- Referenced as asset type; limited documentation available in public moddocs

## Navigation Mesh (Navmesh)

**Structure & Rules** (moddocs: editor/scene-editor/nav_mesh)
- Compilation of polygons for AI pathfinding; prevents collisions with physics objects
- 1.5-meter diameter vertical clearance required on walkable surfaces (terrain, rooftops, castle walls)
- Applied to traversable surfaces only; never beneath physical objects; areas requiring jumping excluded
- Navmesh polygons must encompass spawn point pivot points or spawns won't function

**Navmesh Types**:
- ID 0: Basic navigation mesh (battles, hideouts, halls)
- ID 1: Raid mode activation
- ID 2: Active walkable areas during normal gameplay
- ID 3: Animal spawn isolation zones
- Village scenes use multiple mesh IDs; siege-town scenes vary between civilian/siege mode

**Generation** (moddocs: editor/scene-editor/nav_mesh)
- Select Mode (hotkeys 1-3): Modify vertices/edges/faces; operations include extrusion, filling, selection growing, vertex connection, welding
- Add Mode (Spacebar): Place four vertices, Ctrl+Space to create polygons

## Scene Levels

**Level System** (moddocs: editor/scene-editor/level_system)
- Organizes entity visibility across mission contexts
- Recognized levels: level_1, level_2, level_3 (difficulty/variation tiers), siege (fortified combat), civilian (non-combat)
- Entity visibility rule: Entity only appears when mission contains **all** levels to which entity is assigned
- Example: Entity assigned to level_1 + siege appears only in missions with both; not in level_1-alone or siege-alone missions
- Editor testing: "Require all levels" (gameplay simulation) vs "Require at least one level" (preview mode)

## Scene Registration

**Module Structure** (moddocs: asset-management/asset-types/overriding_scenes_prefabs)
- Scenes override via folder/filename in module directory
- Can replace default game scenes with identically-named custom scenes
- No detailed XML registration procedure documented in public moddocs

## Known Pitfalls & Limitations

**Common Issues** (moddocs: authoring-mission-scenes, docs.bannerlordmodding.lt)
1. Native Editor test functionality is broken; use Editor Test Mode mod for in-game verification
2. Siege engines: require direct line-of-sight to targets, frequently cause friendly fire if forward-positioned
3. Prefab modifications: Adding components severs connection permanently; only value changes preserve link
4. Terrain: Only ~24 base game scenes include terrain (empire_village_003, khuzait_castle_002, multiplayer maps noted)
5. Spawn points not encompassed by navmesh won't function
6. Scene load verification: `if (!Mission.Current.IsLoadingFinished || Agent.Main == null) return;`
7. Editor planes block sunlight in interiors; seasons adjustable via editor settings
8. Cross-scene entity copies drag the donor's `group_object_guid` with them; if the receiving
   scene's `<editor_data>` came from a *different* donor, the editor AVs on load while the game
   is fine (see "Editor-only data — the two-copy rule" above)
9. Generated terrain lives only in `terrain.bin`; the editor edits `terrain_ed.bin` and will
   overwrite generated terrain on save. No `OK01` writer exists yet

## References

- https://moddocs.bannerlord.com/authoring-mission-scenes/
- https://moddocs.bannerlord.com/editor/scene-editor/
- https://moddocs.bannerlord.com/asset-management/
- https://docs.bannerlordmodding.lt/editor/scenes/
