# Rochester Castle — Bannerlord Scene Build Specification

**Target period:** Wars of the Roses, c. 1460  
**Scene name (proposed):** `dadg_Rochester_castle` (matches existing `settlements.xml` binding)  
**Spec version:** 1.0 (2026-07-17)  

---

## Part 1 — Historical & Architectural Facts

### 1.1 The Keep

Rochester Castle's keep is the defining feature and one of the finest Norman great towers in England.

| Attribute | Value | Source |
|---|---|---|
| External footprint | **21 × 21 m** (70 × 70 ft) | Gatehouse Gazetteer; Wikipedia; World History Encyclopedia |
| Total height (parapet) | **34.5 m** (113 ft) | Gatehouse Gazetteer (most precise); Wikipedia gives 34 m |
| Turret height (above parapet) | **+3.7 m** (12 ft); overall turret tip 38 m | English Heritage; Wikipedia |
| Wall thickness at base | **3.5–3.7 m** (11–12 ft) | World History Encyclopedia; Wikipedia |
| Wall thickness at top | **~3 m** (10 ft) | Wikipedia |
| Construction date | c. 1127–1136, Archbishop William of Corbeil | Gatehouse Gazetteer |
| Corner turrets | **4 total**: 3 square (NE, NW, SW), 1 **round** (SE); the round SE turret was rebuilt after the 1215 siege mine collapsed the original square corner | Gatehouse Gazetteer; World History Encyclopedia; Wikipedia |
| Internal spine wall | East–west cross wall, full height, divides keep in two | English Heritage; World History Encyclopedia |
| Well shaft | 18 m into bedrock, centred in spine wall | World History Encyclopedia |
| Floors | Basement (storage) + 3 upper floors; 4 storeys total | Gatehouse Gazetteer |
| Forebuilding | Rectangular, attached to **north** face; entrance at first-floor level; drawbridge gap 2.7 m (9 ft); portcullis behind inner door | Wikipedia; Ancient History Sites |
| Forebuilding size | No precise external dimensions in sources; inferred ~8–10 m wide × ~5–6 m projecting north from keep face (consistent with typical forebuilding proportions) | Inference from plan sketches at great-castles.com |
| Spiral stairs | NE turret (accesses all floors) and SW turret (excludes basement) | Gatehouse Gazetteer |
| Roof state, 15th c. | Keep was still largely standing and roofed; no demolition recorded until post-1603. English Heritage reports no documented construction or demolition in the 15th c. | English Heritage history page |
| Materials | Kentish ragstone with Caen limestone dressings at corners and window surrounds | English Heritage; World History Encyclopedia |

**Source discrepancy — height:** The Gatehouse Gazetteer gives 34.5 m to parapet; Wikipedia gives 34 m; World History Encyclopedia gives 34.4 m; all consistent rounding of the same survey figure. English Heritage quotes 38 m which is the turret tips. **Spec uses 34.5 m parapet / 38 m turret tips.**

### 1.2 Bailey and Curtain Wall Circuit

| Attribute | Value | Source |
|---|---|---|
| Bailey shape | Roughly **rectangular to irregular quadrilateral**, elongated N–S | Wikipedia; Gatehouse Gazetteer |
| Bailey N–S dimension | **~120 m** | Gatehouse Gazetteer |
| Bailey E–W dimension | Not explicitly recorded; plan sketches at great-castles.com suggest ~60–70 m | Inferred from plan; no authoritative figure found |
| Keep position | **South-east corner** of bailey | English Heritage; Wikipedia |
| Main gatehouse | **North-east** side; demolished in the 19th century; originally featured an archway with projecting towers | Wikipedia; Castlopedia |
| Postern / NW tower | **North-west corner** tower, built c. 1378–1383 (Richard II), guarded the river/bridge approach; contained a postern gate | Gatehouse Gazetteer; World History Encyclopedia |
| West wall | Incorporates **11th-century Gandulfian masonry** (1087–89) with herringbone courses; partly built atop Roman city wall footings; height surviving varies; original height ~6.7 m | English Heritage; World History Encyclopedia |
| East curtain | Rebuilt under Edward III and Richard II, **1367–1383**; Kentish ragstone; two rectangular 2-storey mural towers | English Heritage; Gatehouse Gazetteer; World History Encyclopedia |
| East mural towers | **2 rectangular towers**, NE of keep along east curtain; built 1367–1370 | English Heritage; Ancient History Sites |
| South-east drum tower | **Round**, ~9 m diameter (30 ft), built early 13th c. by Henry III to fill 1215 mine breach; Henry III's drum tower (sometimes called the "south tower") | Wikipedia; World History Encyclopedia; Ancient History Sites |
| Henry III chamber block | 2-storey structure on west curtain, 1220s | English Heritage |
| Curtain wall height | ~6.7 m (22 ft) | World History Encyclopedia; Wikipedia |
| Curtain wall thickness | ~1.37 m (4.5 ft) at base | World History Encyclopedia |
| Roman wall reuse | West curtain built partly **on Roman city wall** foundations (no Roman wall survives above ground in this stretch) | English Heritage; Wikipedia |
| Ditch | Castle ditch originally on all sides **except west** (west = River Medway cliff); partially infilled by medieval period; east and north sides still traceable in 15th c. | Wikipedia; Gatehouse Gazetteer |
| North curtain | Fragmentary; incorporated into High Street property garden walls by later centuries | Gatehouse Gazetteer |

**Count and positions of surviving towers (c. 1460):**
1. SE corner — Henry III round tower (13th c.)
2. NW corner — Richard II tower/postern (c. 1378–83)
3–4. Two rectangular towers on east curtain (1367–70)
Keep itself has 4 corner turrets (structurally separate from curtain towers)
**Total: 4 curtain towers + the keep's own 4 turrets**

### 1.3 Terrain and Site

| Attribute | Value | Source |
|---|---|---|
| Location | South-west corner of Rochester city; on east bank of River Medway | Wikipedia |
| River frontage | Castle's **west** wall faces the Medway directly; no ditch on west side | Wikipedia; World History Encyclopedia |
| Esplanade | Flat strip between west curtain and river bank | English Heritage description |
| Boley Hill | Natural rock outcrop ~100 m long NW–SE, immediately **south** of castle; rises ~7 m above surrounding ground; NW end overlooks river with a 12 m (40 ft) cliff to east bank | Gatehouse Gazetteer (Boley Hill entry) |
| Cathedral position | Rochester Cathedral ~100 m **south-east** of keep (outside castle enclosure) | General reference; confirmed by map |
| Medieval bridge | Rochester Bridge crossed ~20–30 m **north-west** of NW corner tower; "a little left of the present bridge" closer to the castle | Search results; Gatehouse Gazetteer |
| Medieval town walls | Enclosed castle on **north and east** sides; walled town abutted the castle | English Heritage |
| Site elevation above river | Castle bailey approximately **8–12 m** above Medway flood level (Kentish ragstone outcrop); Boley Hill summit ~15 m | Inferred from typical Rochester street levels and Boley Hill height data |
| Roman road (Watling Street) | Runs **north** through town, crossing bridge; is the London–Canterbury–Dover route; effectively a "market street" N of castle | Wikipedia |
| Orientation | Castle faces roughly true north; keep at SE corner; gatehouse NE; river W; Boley Hill S | Confirmed across multiple sources |

**ASCII Site Plan (schematic, not to scale)**

```
         N
         |
 [River  |  WALLED TOWN
  Medway]|  (N and E sides)
         |
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  W      | Rochester Castle              E
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  |  NW  |                     | NE    |
  |tower/|     BAILEY          |gate   |
  |post- |     (gardens)       |(demol)|
  |ern   |                     |       |
  |      |                ~120m|       |
  |  W CURTAIN          E CURTAIN~70m  |
  |  (Gandulf/11th c.)  (Edw III)     |
  |                     [Rect.Tower 1] |
  |      |                     |       |
  |      |                     |       |
  |      |                [Rect.Tower 2]|
  |      |     +-----------+   |       |
  |Hen3  |     |  KEEP     |   |       |
  |chamb |     | (21x21m)  |[SE drum   |
  |block |     +-----------+  tower]   |
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
         |
    [BOLEY HILL ~100m]
         |
    CATHEDRAL (~100m SE of keep)
```

Approximate real distances:
- Bailey N–S: 120 m
- Bailey E–W: ~65 m (estimated)
- Keep to west curtain (inner): ~35 m
- Keep to north curtain (inner): ~80 m
- NW tower to NE gatehouse along north curtain: ~65 m
- Medieval bridge to NW tower: ~30 m

**Sources for Part 1:**
- English Heritage description: https://www.english-heritage.org.uk/visit/places/rochester-castle/history/description/
- English Heritage history: https://www.english-heritage.org.uk/visit/places/rochester-castle/history/
- Gatehouse Gazetteer (Rochester Castle): https://www.gatehouse-gazetteer.info/English%20sites/1912.html
- Gatehouse Gazetteer (Boley Hill): https://gatehouse-gazetteer.info/English%20sites/1915.html
- Wikipedia — Rochester Castle: https://en.wikipedia.org/wiki/Rochester_Castle
- World History Encyclopedia: https://www.worldhistory.org/Rochester_Castle/
- Ancient History Sites: https://www.ancient-history-sites.com/sites/rochester-castle/
- Great Castles floor plan: https://great-castles.com/rochesterplan.html
- Castlopedia: https://www.castlopedia.com/castle/rochester-castle/2657

### 1.4 Wars of the Roses Context (1455–1487)

Rochester Castle played **no military role in the Wars of the Roses**. The famous sieges were in **1215** (King John vs. rebellious barons) and **1264** (Simon de Montfort's forces). After Edward III and Richard II spent approximately £2,262 on repairs in 1367–1383, there is **no record of any construction work in the 15th century**. From around 1400, the bailey was leased to private tenants. The keep remained standing and structurally intact but was almost certainly unroofed or partially ruinous by mid-century. By the second half of the 16th century Elizabeth I licensed removal of stone from the curtain wall to build Upnor Fort.

**Verdict for scene:** Depict a **garrisoned-but-aging royal castle**. The keep dominates and is the primary defensible structure. The curtain wall circuit is mostly standing (east wall freshly repaired 1370s) but the bailey interior has been let to tenants — timber lean-tos, a well, domestic buildings. The main gatehouse (NE) is still functional. The NW postern tower is relatively new (built 1378–83 — only ~75 years old in 1460). The Henry III chamber block on the west wall is ruinous. The north curtain is fragmented.

---

## Part 2 — Scene Scale and Coordinate Plan

### 2.1 Recommended Scale

Bannerlord castle siege scenes in the DADG corpus typically span **200–500 m** for the core structure, within an overall scene terrain of ~800×800 m (Carisbrooke: structural bbox ~218×180 m core; Corfe: ~186×214 m). Rochester's real bailey is only 120×65 m — compact enough to use **near true-to-life scale** for the castle proper.

**Recommended: use ~1:1 scale for the castle structure, 800×800 m total scene.**

- The small bailey means walls are close together — good for siege gameplay (short approach to inner gate).
- Compress the attacker camp terrain on the south/east to bring siege spawners into range.
- The River Medway runs along the west edge; no attacker approach from that side.

### 2.2 Scene Coordinate System

Scene origin (0,0,0): **centre of bailey**, approximately at scene world coordinates (400, 400).

```
Scene Y+ = North
Scene X+ = East
Scene Z = up
```

| Feature | Scene X | Scene Y | Scene Z | Notes |
|---|---|---|---|---|
| Scene origin (bailey centre) | 400 | 400 | see terrain | — |
| Keep centre | 437 | 350 | terrain+0 | SE quadrant of bailey |
| Keep SW corner | 426 | 339 | terrain+0 | footprint 21×21 m |
| Keep NE corner | 448 | 361 | terrain+0 | — |
| Forebuilding centre | 437 | 368 | terrain+0 | ~8 m N of keep face |
| NE gatehouse | 437 | 460 | terrain+0 | approx ~5 m inside N curtain |
| NW postern tower centre | 367 | 455 | terrain+0 | NW corner |
| SE drum tower centre | 448 | 340 | terrain+0 | SE corner, outside keep |
| East mural tower 1 (N) | 462 | 432 | terrain+0 | On east curtain |
| East mural tower 2 (S) | 462 | 400 | terrain+0 | On east curtain |
| West curtain mid | 365 | 400 | terrain+0 | Medway side |
| North curtain mid | 400 | 462 | terrain+0 | Fragmentary |
| South curtain mid | 400 | 337 | terrain+0 | Near keep |
| Castle bailey centre | 400 | 400 | terrain+4 | Keep corner at Z+8–10 |
| Attacker camp | 500 | 300 | terrain+0 | SE approach, open ground |
| River Medway (W edge) | 300 | 400 | terrain-2 | River runs N–S |
| Boley Hill top | 400 | 290 | terrain+8 | 100 m south of keep |
| Cathedral area | 470 | 340 | outside scene | May not be rendered |

**Curtain wall coordinates (approximate; corners):**
- NW: (365, 462)
- NE: (465, 462)  
- SE: (465, 337)
- SW: (365, 337)

Curtain wall spans:
- N wall: ~100 m (365→465 in X at Y=462)
- E wall: ~125 m (337→462 in Y at X=465)
- S wall: ~100 m (365→465 in X at Y=337)
- W wall: ~125 m (337→462 in Y at X=365)

> Note: These dimensions are ~20% larger than the real 120×65 m to give more gameplay space and accommodate wall-segment prefab sizes. The real ratio (almost 2:1 N–S vs E–W) is preserved.

### 2.3 Terrain Plan

| Zone | Elevation (above scene base) | Notes |
|---|---|---|
| River Medway (W) | −2 to 0 m | River bed; steep west bank |
| Esplanade (W of castle) | +1 to +2 m | Flat strip between curtain and river |
| Castle bailey | +4 to +6 m | Kentish ragstone rise |
| Boley Hill (S) | +6 to +10 m | Gradual rise south of castle |
| Attacker camp (SE/E) | +2 to +4 m | Gentle slope; siege approach from E |
| Town (N/NE, outside curtain) | +3 to +5 m | Town street level; walled town |
| Cathedral environs (SE) | +3 m | Background only |

**Siege approach:** Attackers enter from the **east or south-east** (the only open ground). The ditch ran on the east and north sides — include a gentle depression ~5–8 m wide × 2 m deep on the east face. The river cliff on the west eliminates any western approach.

---

## Part 3 — DADG Asset Mapping

### 3.1 Prefab Family Reference (from corpus analysis)

All prefabs below are confirmed to exist in the DADG 6217-prefab catalog (DellarteDellaGuerraScenes module, `DellarteDellaGuerra_Houses.xml` unless noted).

**Wall segment spacing inferred from Framlingham/Corfe/Dartmouth placement:**
- `dadg_norman_english_fort_castle_wall_tower_a`: spaced ~22–27 m (nearest-neighbour) in Framlingham — implies wall panels between towers are ~22 m
- `dadg_english_fort_big_castle_wall_a`: spaced 19–43 m in Corfe/Dartmouth; most common run ~42 m
- `dadg_english_smaller_fort_wall`: ~7–30 m runs in Framlingham

### 3.2 Asset Mapping Table

| Rochester Feature | Prefab(s) to Use | Segment Length / Notes | Compromise |
|---|---|---|---|
| **Keep (21×21 m, 34.5 m tall)** | `dadg_fort_norman_keep_b` + `dadg_fort_norman_keep_c` | Place as a pair, ~5 m apart (as in Bristol); each sub-prefab ~8–9 m square | **MAJOR GAP**: prefab pair = ~15×20 m footprint, not 21×21. Height visually short (~20 m?). See §3.3 below for alternatives. |
| **Keep SE round turret** | `dadg_fort_english_round_tower_d` | 1× at SE corner of keep | Round tower from Carisbrooke; scale to match keep |
| **Keep forebuilding (N face)** | `dadg_english_fort_block` or `dadg_english_fort_block_part` | Rectangular block, ~8 m wide; position N of keep entrance at first-floor Z | Minor: no exact forebuilding prefab; use block + stairs |
| **Forebuilding stair/access** | `dadg_fort_english_stairs_tower_a` or `dadg_fort_english_stairs_tower_b` | 1× | Donor: Dartmouth/Clun |
| **Main curtain wall straight runs** | `dadg_english_fort_big_castle_wall_a` | ~19–42 m per segment; use 4–5 segments per 100 m run | Primary English curtain wall. Donor: Corfe, Dartmouth |
| **Curtain wall short fills** | `dadg_english_small_fort_wall` or `dadg_english_smaller_fort_wall` | ~8–20 m fills | Where main wall doesn't fit |
| **East curtain mural towers (×2 rectangular)** | `dadg_norman_english_fort_castle_wall_tower_a` | 1× each, ~22 m apart on E curtain | Framlingham donor. Square towers, 2-storey |
| **SE drum/round tower (Henry III)** | `dadg_fort_english_round_tower_d` | 1× at SE corner of bailey | ~9 m diameter; only round tower in DADG family |
| **NW postern tower (Richard II, rect.)** | `dadg_norman_english_fort_castle_wall_tower_b` | 1× at NW corner | Rectangular, taller; donor: Bristol, Carisbrooke |
| **NE main gatehouse** | `dadg_castle_gate_outer_l1` (has CastleGate + DestructableComponent scripts) | 1× at NE | Primary functional gate for siege |
| **Gatehouse passage/portcullis** | `dadg_english_gatehouse_fort_retex` | 1× backing `dadg_castle_gate_outer_l1` | Donor: Corfe |
| **West wall (Gandulf, lower/thinner)** | `dadg_english_smaller_fort_wall` or `dadg_english_small_fort_wall` | Lower profile; 4–6 segments | West wall was ~6.7 m tall, thinner (1.37 m) than the east |
| **Henry III chamber block (W wall)** | `dadg_english_fort_house_a` | 1× against inner W curtain | Ruinous by 1460; use as half-standing |
| **Bailey interior buildings** | `dadg_fort_castle_shed_a/b/c/d`, `dadg_fort_castle_well` | Mix of 3–4 sheds + 1 well | Bailey let to tenants c. 1400 |
| **Ruinous sections (N curtain)** | `ruinous_castle_wall_b`, `ruinous_castle_stone_heap_a/b` | 3–4 segments along N curtain | N curtain was fragmentary by 1460 |
| **Siege spawners** | `siege_tower_12m_spawner` (keep E face) + `siege_tower_9m_spawner` (NE gate) | Standard | Keep is 34 m — 12 m siege tower works for first-floor access |
| **Ballista / mangonel** | `ballista_a_spawner`, `mangonel_a_spawner`, `mangonel_b_spawner` | Place on keep roof level and E curtain | Standard DADG siege equipment |
| **Attacker camp barriers** | `dadg_pavise_siege_wall_with_cutout`, `dadg_pavise_wall_with_cutout` | SE camp approach | Standard |
| **sp_ gameplay markers** | `sp_player_castle`, `sp_guard_lords_hall_gate` | Mandatory | Always required |
| **Ditch/slope** | Terrain sculpting only | 5–8 m wide, 2 m deep, E and N sides | No prefab; pure terrain |
| **Boley Hill** | Terrain sculpting only | ~100 m S of keep; +6 to +10 m | No prefab; rough terrain feature |

### 3.3 Keep — Worst Gap and Compromise Options

**Target:** 21 m × 21 m footprint, parapet at 34.5 m (turrets at 38 m). Three square corner turrets + one round turret (SE).

**Available prefabs in descending match quality:**

1. **`dadg_fort_norman_keep_b` + `dadg_fort_norman_keep_c` (recommended)**
   - Used together in Bristol at positions 20.6 m apart
   - Each sub-prefab composed of `dadg_small_fort_corner_tower` + wall panels
   - Combined footprint: approximately 15–20 m in each dimension (not measured from mesh; inferred from child positions in XML: corner tower at x≈7.2, y≈7.5 → half-width ~8 m)
   - **Compromise:** footprint is ~75–85% of Rochester's 21 m; height is approximately 60–70% of 34.5 m (visually shorter)
   - **Mitigation:** Scale up uniformly by 1.3–1.4x using entity scale parameter to reach 21 m; this will also increase height proportionally
   - The two-part composition (b+c together) creates an interesting silhouette with two corner-tower clusters

2. **`dadg_fort_norman_keep_a`** (also exists; used in Norwich worldmap context at scale 0.886)
   - Similar construction to b/c; single-piece variant
   - Check `dadg_adjusted_houses.xml` line 10979 — same prefab referenced at scale 0.789

3. **`dadg_english_fort_block` + `dadg_english_fort_block_part` (fallback)**
   - Solid stone rectangular block
   - Used in Corfe and Clun to construct inner ward structures
   - Lower silhouette; no turrets
   - Could be stacked/scaled to approximate a blank keep but lacks Norman character

4. **`dadg_english_durham_fort` composite** (from Durham scene)
   - Full modular Durham Castle keep assembly using `dadg_english_durham_fort_wall_a/b/c` + `dadg_english_durham_fort_small_tower` + `dadg_english_durham_fort_wide_wall`
   - Durham's great tower is a 12th-c. Norman keep (though much altered); this prefab family was designed for it
   - Durham scene spans 130 m × 418 m of these wall pieces — it's a large complex, not just the keep
   - The Durham Fort prefab itself (`dadg_english_durham_fort`) is a single mesh; other `_wall_` pieces are wall segments
   - **Best authentic Norman feel** but unclear overall dimensions without in-game measurement

**Recommendation:** Use `dadg_fort_norman_keep_b` as the main keep body, scaled to 1.35x (estimated to reach ~21 m footprint), placed at keep SE quadrant of bailey. Add `dadg_fort_english_round_tower_d` at SE corner of the keep's own footprint to represent the reconstructed round turret. Place `dadg_english_fort_block_part` on the N face as the forebuilding base. The builder should measure `dadg_fort_norman_keep_b` in-engine first to confirm actual mesh extents before committing to the scale factor.

---

## Part 4 — Settlement Registration

Rochester Castle **already exists** in `settlements.xml`:

```xml
<!-- Rochester -->
<Settlement id="dadg_Rochester_castle" 
            name="Rochester Castle" 
            owner="Faction.clan_grey_of_ruthin" 
            posX="885.341" posY="187.302" 
            culture="Culture.empire">
  <Locations complex_template="LocationComplexTemplate.castle_complex">
    <Location id="center" 
              scene_name="Brougham_castle" 
              scene_name_1="Brougham_castle" 
              scene_name_2="Brougham_castle" 
              scene_name_3="Brougham_castle" />
    <Location id="lordshall" 
              scene_name_1="castle_hall_a" 
              scene_name_2="castle_hall_a" 
              scene_name_3="castle_hall_a" />
    <Location id="prison" scene_name="vlandia_dungeon_stealth" />
  </Locations>
```

**Current scene binding:** `Brougham_castle` is used as a placeholder for all 3 prosperity levels.

**Action required after scene build:** Change `scene_name`, `scene_name_1`, `scene_name_2`, `scene_name_3` in the `<Location id="center">` tag from `Brougham_castle` to the new scene name (e.g. `Rochester_castle` or `dadg_Rochester_castle_siege`).

**Associated village:** `village_Maidstone` (bound to `dadg_Rochester_castle`), using `dadg_village_d_combe` scene — no change needed.

**Culture note:** Currently set to `Culture.empire` — this is the vanilla faction proxy used for English/Vlandian culture in DADG. No change needed unless a dedicated English culture id exists.

---

## Part 5 — Open Questions and Risks

### 5.1 Critical unknowns

1. **Keep prefab actual dimensions**: The mesh extent of `dadg_fort_norman_keep_b` is not measured from XML coordinates alone (the corner tower at z=3.857 with scale=0.625 inside means the tower top is at approximately 3.857 + 0.625×keep-tower-height). The builder must place and measure in-engine before scaling.

2. **Bailey E–W dimension**: No archaeological source gives the precise east–west extent of the bailey. The 65 m estimate is based on plan sketches only. If the actual dimension is closer to 50 m or 80 m, adjust the east curtain X coordinate accordingly.

3. **North curtain survival**: Sources say it is "fragmentary" and "incorporated into garden walls". Unclear how much was still standing in 1460 vs. when sources were written (19th–20th c.). Spec assumes partial survival (use `ruinous_castle_wall_b` sections interspersed with gaps).

4. **Henry III chamber block dimensions**: No measurements found. Only known it was "two-storey" and on the "west curtain" built in the 1220s. Treat as a secondary building approximately 15×8 m.

5. **Ditch depth and width on east/north**: No measurements found. Use nominal 5 m wide × 2 m deep (gentle slope, partially silted by 1460).

6. **Gate form**: The NE gatehouse was demolished in the 19th century. No surviving description of its exact 15th-century form. Assume a twin-towered gatehouse based on contemporary English practice.

### 5.2 Gameplay risks

7. **Keep too small for navmesh**: If the keep is scaled to 21 m, the interior is inaccessible to NPCs. The keep in c. 1460 was used primarily as a landmark, not actively garrisoned with troops on upper floors. Place the `sp_player_castle` flag at the base of the keep forebuilding. Keep the navmesh traversal path around the keep, not through it.

8. **River impassable**: The west edge (river) must be walled off by terrain + west curtain. Do not place any attacker spawners west of the curtain — the river cliff makes western assault impossible.

9. **Siege tower height**: The keep parapet (real: 34.5 m) is likely taller than any siege tower spawner variant. `siege_tower_12m_spawner` reaches the first-floor entry level of the keep forebuilding (at ~5–6 m). This is the intended route. The keep interior at full height is not a siege objective — only the forebuilding and bailey court.

10. **DADG Rochester keep prefab is worldmap-only**: `dadg_worldmap_rochester_keep` in `cabbage.xml` is a **worldmap icon** (scale 0.546, single meta_mesh). Do NOT use this in the battle scene — it is too small and has no physics/navmesh. Use `dadg_fort_norman_keep_b/c` or `dadg_fort_norman_keep_a` instead.

11. **dadg_fort_norman_keep_a**: A fourth variant exists in `DellarteDellaGuerra_Houses.xml` (line 114112) and the `norwich_keep_wall` compound prefab; it has `dadg_small_fort_corner_tower` as children. This variant is used at scale 0.886 in the Norwich worldmap context. May be the same mesh as b/c — builder should compare all four variants (a/b/c/d) visually before choosing.

### 5.3 Source gaps

- No plan or aerial photograph source was found that gives east–west bailey dimension in metres. If the Historic England plan image at `https://historicengland.org.uk/images-books/photos/item/MP/ROC0007` is accessible with an authenticated account, it may resolve this.
- Boley Hill elevation measurements are from the Gatehouse Gazetteer entry (40-ft cliff to river). Modern ground level is reduced by Tudor/18th-c. terracing; original height was greater.
- No Kent Archaeological Society report was accessible during this research session. Checking KAS Archaeologia Cantiana volumes for Rochester (available via JSTOR) would yield more precise survey data.

---

## Summary for Builder

| Item | Value |
|---|---|
| Scene name | `dadg_Rochester_castle` (matches settlements.xml) |
| settlements.xml change | `scene_name` in `<Location id="center">` from `Brougham_castle` → new scene name |
| Scene size | 800×800 m |
| Castle structure scale | ~1:1 real-world (bailey 100×65 m in scene, slightly enlarged from real 120×65 m for playability) |
| Keep footprint | 21×21 m target; use `dadg_fort_norman_keep_b` scaled ~1.35x |
| Keep height | ~20–22 m visual (with scale); real target 34.5 m cannot be matched without custom mesh |
| Primary wall prefab | `dadg_english_fort_big_castle_wall_a` (~19–42 m per segment) |
| Tower prefabs | `dadg_norman_english_fort_castle_wall_tower_a` (E curtain ×2), `dadg_norman_english_fort_castle_wall_tower_b` (NW postern), `dadg_fort_english_round_tower_d` (SE drum) |
| Gate | `dadg_castle_gate_outer_l1` (functional siege gate) at NE |
| Siege approach | From East and SE |
| Period mood | Aging royal castle; keep intact; bailey let to tenants; north curtain fragmentary |
| Worst asset gap | Keep height (available ~20 m vs. real 34.5 m); no exact forebuilding prefab |
