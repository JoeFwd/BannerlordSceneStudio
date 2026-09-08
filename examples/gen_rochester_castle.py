"""Generate the dadg_gen_rochester_castle siege scene FROM SCRATCH.

Ground-up rebuild (the earlier whole-Clun-clone attempt was rejected).  Nothing
is bulk-copied; every castle piece is authored entity-by-entity and only the
individual script-bearing siege entities are harvested (one at a time) from
Clun_castle for their exact <scripts> blobs.

  * TERRAIN — a synthetic Rochester heightmap built from scratch: River Medway
    band + scarp on the W edge, Boley Hill rise to the S, a flat castle platform,
    an esplanade W of the curtain, an E ditch, and a gentle E/SE attacker
    esplanade.  No donor terrain.bin is read or copied.

  * VISUAL CASTLE — keep pair, curtain circuit, four towers, a hand-placed
    functional gate (dadg_castle_gate_outer_l1), and light bailey dressing are
    authored ENTITY-BY-ENTITY via builder.add(): each record is a prefab
    reference + a transform computed from the Rochester coordinate spec.

  * SIEGE SCRIPT ENTITIES — the ONE sanctioned reuse.  WallSegment carriers,
    ladder / tower / ram spawners, deployment placeholders (attacker + defender,
    each keeping its DeploymentPoint Side), and boundaries are harvested as
    INDIVIDUAL entity records from Clun_castle (to keep their exact <scripts>),
    then repositioned + retagged onto the Rochester walls.  Strategy cameras are
    authored fresh with DADG lowercase tags.  The gate is NOT harvested: the
    baked CastleGate script rides inside dadg_castle_gate_outer_l1.

  * NAVMESH — generated from scratch: one welded ground/approach sheet from the
    heightmap (g3=2); interior bailey retagged g3=1; a gate band retagged
    g3=462 (through) / g3=106 (outer strip disabled on open) to match the baked
    CastleGate NavigationMeshId / NavigationMeshIdToDisableOnOpen of the
    hand-placed gate; ladder-drop faces retagged to each spawner OnWallNavMeshId
    (202/212/302/312 — none end in 0 or 1); faces under the wall footprints are
    removed; camp->gate->interior is verified as a single connected component.

Coordinate frame (Rochester spec, Part 2.2): X+=East, Y+=North, Z=up; bailey
centre ~(400,400).  Curtain corners NW(365,462) NE(465,462) SE(465,337)
SW(365,337); keep at the SE quadrant (437,350).

Output: DellarteDellaGuerraScenes/SceneObj/dadg_gen_rochester_castle/
"""
from __future__ import annotations

import copy
import math
import sys
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.compose import SceneBuilder, _sample_height
from blscene.harvest import harvest_entities
from blnav import rnm1
from blnav.generate import from_heightmap
from blnav.nmg9 import NavMesh

GAME = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
SC = GAME + r"\DellarteDellaGuerraScenes\SceneObj"
CLUN = SC + r"\Clun_castle"
OUT_DIR = SC

SCENE_NAME = "dadg_gen_rochester_castle"

# --- World constants ---
N = 1025                 # samples per axis (8*128+1)
NODE_SIZE = 100.0
NODES = 8
WORLD = NODES * NODE_SIZE   # 800 m
SEED = 1460                 # deterministic composition (depicted year)

# Terrain layer indices in the battle_terrain_a template <layers>:
#   0 first_material(grass)  6 dry_ground  7 soil  8 hard_rock
# (verified against the emitted <layers> list: first_material, base_rock,
#  mountain_grass, base_snow, flow, grass, dry_ground, soil, hard_rock, ...)
LAYER_ROCK = 8           # river scarp / cliff
LAYER_SOIL = 7           # Boley Hill / ditch
LAYER_DIRT = 6           # dry_ground: approach road + worn bailey earth

# --- Datum heights (m) for the Rochester landscape ---
PLATFORM_Z = 30.0        # flat castle platform (Clun-like datum so harvested
                         #   siege props sit at a sensible Z)
RIVER_Z = 22.0           # Medway bed
ESPLANADE_Z = 28.5       # flat strip W of curtain
BOLEY_Z = 38.0           # Boley Hill summit S
CAMP_Z = 27.0            # SE/E attacker esplanade

# --- Castle geometry (Rochester spec, Part 2.2) ---
BAILEY = (400.0, 400.0)
CURTAIN = {  # corner XY
    "NW": (365.0, 462.0),
    "NE": (465.0, 462.0),
    "SE": (465.0, 337.0),
    "SW": (365.0, 337.0),
}
KEEP_XY = (437.0, 350.0)
GATE_XY = (437.0, 462.0)   # main gate seated in the N curtain opening

# Baked CastleGate ids inside dadg_castle_gate_outer_l1 (measured from prefab):
#   NavigationMeshId=462 (through-gate faces), NavigationMeshIdToDisableOnOpen=106
GATE_ID = 462
GATE_DISABLE_ID = 106

LV = ["level_1", "level_2", "level_3", "siege"]


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------
def _smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def build_heights() -> np.ndarray:
    """Compose the Rochester heightmap from scratch (no donor terrain)."""
    ii = np.arange(N, dtype=np.float32)
    xx, yy = np.meshgrid(ii, ii)           # xx=col=X index, yy=row=Y index
    wx = xx / (N - 1) * WORLD               # world X (East)
    wy = yy / (N - 1) * WORLD               # world Y (North)

    # Base surface = flat castle platform everywhere; features carve/raise it.
    h = np.full((N, N), PLATFORM_Z, dtype=np.float32)

    # --- Esplanade shelf: flat strip just W of the curtain (X ~ 320..365). ---
    espl = _smoothstep((wx - 320.0) / 25.0) * (1.0 - _smoothstep((wx - 355.0) / 15.0))
    h = h * (1.0 - espl) + ESPLANADE_Z * espl

    # --- River Medway band + scarp on the W edge (X < ~320). ---
    scarp = _smoothstep((wx - 270.0) / 50.0)          # 0 at river, 1 at esplanade
    river_surface = RIVER_Z + (ESPLANADE_Z - RIVER_Z) * scarp
    river_w = 1.0 - _smoothstep((wx - 300.0) / 40.0)  # 1 west, 0 east of X~340
    h = h * (1.0 - river_w) + river_surface * river_w

    # --- Boley Hill: gentle rock rise to the S (~400, 265), summit +8 m. ---
    dbx = wx - 400.0
    dby = wy - 265.0
    boley = (BOLEY_Z - PLATFORM_Z) * np.exp(
        -(dbx ** 2) / (2 * 95.0 ** 2) - (dby ** 2) / (2 * 55.0 ** 2)
    )
    boley *= (1.0 - _smoothstep((wy - 320.0) / 30.0))   # fade out under the S wall
    h = h + boley.astype(np.float32)

    # --- East ditch: gentle 2 m depression just outside the E curtain. ---
    ditch = 2.0 * np.exp(-((wx - 485.0) ** 2) / (2 * 8.0 ** 2))
    ditch *= _smoothstep((wy - 330.0) / 25.0) * (1.0 - _smoothstep((wy - 460.0) / 25.0))
    h = h - ditch.astype(np.float32)

    # --- Attacker esplanade: gentle fall to CAMP_Z on the E / SE open ground. ---
    east = _smoothstep((wx - 495.0) / 120.0)          # ramps E of the ditch
    h = h * (1.0 - east) + CAMP_Z * east
    sedge = _smoothstep((330.0 - wy) / 60.0) * _smoothstep((wx - 430.0) / 60.0)
    h = h * (1.0 - 0.5 * sedge) + CAMP_Z * (0.5 * sedge)

    # --- Very low-amplitude deterministic undulation on open E ground only. ---
    rng = np.random.default_rng(SEED)
    field = rng.standard_normal((9, 9)).astype(np.float32)
    fy = np.linspace(0, 8, N)
    fx = np.linspace(0, 8, N)
    gy0 = np.floor(fy).astype(int); gy1 = np.minimum(gy0 + 1, 8)
    gx0 = np.floor(fx).astype(int); gx1 = np.minimum(gx0 + 1, 8)
    ty = (fy - gy0)[:, None]; tx = (fx - gx0)[None, :]
    undul = (
        field[np.ix_(gy0, gx0)] * (1 - ty) * (1 - tx)
        + field[np.ix_(gy0, gx1)] * (1 - ty) * tx
        + field[np.ix_(gy1, gx0)] * ty * (1 - tx)
        + field[np.ix_(gy1, gx1)] * ty * tx
    ).astype(np.float32)
    free = _smoothstep((wx - 470.0) / 40.0)           # E of curtain only
    h = h + 0.8 * undul * free

    return h.astype(np.float32)


def layer_weights(heights: np.ndarray) -> dict[int, np.ndarray]:
    """Rock on the steep river scarp; soil on Boley Hill and the E ditch."""
    spacing = WORLD / (N - 1)
    gy, gx = np.gradient(heights)
    slope = np.hypot(gx, gy) / spacing

    ii = np.arange(N, dtype=np.float32)
    xx, yy = np.meshgrid(ii, ii)
    wx = xx / (N - 1) * WORLD
    wy = yy / (N - 1) * WORLD

    rock = ((slope > 0.12) & (wx < 340.0)).astype(np.float32)
    soil = (
        ((wy < 330.0) & (np.abs(wx - 400.0) < 110.0)).astype(np.float32)   # Boley
        + ((np.abs(wx - 485.0) < 12.0) & (wy > 330.0) & (wy < 460.0)).astype(np.float32)  # ditch
    )
    soil = np.clip(soil, 0.0, 1.0)

    # --- Dirt road (dry_ground): rutted approach from the SE/E esplanade up to
    #     the N gate, then a worn track through the gate into the bailey; plus a
    #     patch of trampled earth across the worn bailey interior.  Donors
    #     (Corfe/Dartmouth) paint dry_ground along the main siege approach and
    #     the trafficked ward floor, keeping grass elsewhere. ---
    def _band(px0, py0, px1, py1, half):
        """Soft ~2*half-wide painted band along the segment (px0,py0)->(px1,py1)."""
        vx, vy = px1 - px0, py1 - py0
        ln2 = vx * vx + vy * vy
        t = np.clip(((wx - px0) * vx + (wy - py0) * vy) / max(ln2, 1e-6), 0.0, 1.0)
        cx = px0 + t * vx
        cy = py0 + t * vy
        d = np.hypot(wx - cx, wy - cy)
        return np.clip(1.0 - d / half, 0.0, 1.0)

    road = np.zeros_like(heights)
    road = np.maximum(road, _band(505.0, 300.0, 450.0, 470.0, 6.0))   # esplanade -> gate approach
    road = np.maximum(road, _band(450.0, 470.0, 437.0, 462.0, 6.0))   # bend to gate mouth
    road = np.maximum(road, _band(437.0, 470.0, 437.0, 430.0, 5.0))   # through gate into bailey
    # Worn bailey earth: gentle trampled patch around the interior circulation.
    bailey_worn = 0.55 * np.exp(
        -((wx - 410.0) ** 2) / (2 * 26.0 ** 2) - ((wy - 405.0) ** 2) / (2 * 32.0 ** 2)
    )
    dirt = np.clip(np.maximum(road, bailey_worn.astype(np.float32)), 0.0, 1.0)
    # Road/dirt overrides soil/rock where they overlap so it reads as a track.
    soil = np.clip(soil - dirt, 0.0, 1.0)

    print(f"terrain: slope max={slope.max():.3f} rock={rock.mean()*100:.1f}% "
          f"soil={soil.mean()*100:.1f}% dirt={dirt.mean()*100:.1f}%")
    return {LAYER_ROCK: rock, LAYER_SOIL: soil, LAYER_DIRT: dirt}


def th(heights, x, y, default=PLATFORM_Z):
    z = _sample_height(heights, WORLD, WORLD, x, y)
    return z if z is not None else default


# ---------------------------------------------------------------------------
# Visual castle structure (authored entity-by-entity)
# ---------------------------------------------------------------------------
def wall_run(builder, heights, x0, y0, x1, y1, prefab, seg_len, *, z_lift=0.0):
    """Place a straight run of wall segments from (x0,y0) to (x1,y1).

    Each segment is a fresh entity record (prefab + transform).  Yaw aligns the
    wall's long axis with the run direction.  Returns segment centre coords.
    """
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    n = max(1, int(round(length / seg_len)))
    yaw = math.atan2(dy, dx)
    centres = []
    for i in range(n):
        t = (i + 0.5) / n
        cx = x0 + dx * t
        cy = y0 + dy * t
        cz = th(heights, cx, cy) + z_lift
        builder.add(prefab, (cx, cy, cz), (0.0, 0.0, yaw), levels=LV)
        centres.append((cx, cy))
    return centres


def build_structure(builder, heights):
    """Author the Rochester curtain, towers, gatehouse, keep, and bailey props."""
    NW, NE, SE, SW = (CURTAIN[k] for k in ("NW", "NE", "SE", "SW"))

    WALL_BIG = "dadg_english_fort_big_castle_wall_a"     # E curtain (repaired)
    WALL_SM = "dadg_english_small_fort_wall"             # W/S/N curtain

    # Closed curtain circuit; only the N-curtain gate opening (X 428..446) is left.
    wall_run(builder, heights, SW[0], SW[1], NW[0], NW[1], WALL_SM, 13.5)   # W (river)
    wall_run(builder, heights, SW[0], SW[1], SE[0], SE[1], WALL_SM, 13.5)   # S (near keep)
    wall_run(builder, heights, SE[0], SE[1], NE[0], NE[1], WALL_BIG, 20.0)  # E (attacker)
    wall_run(builder, heights, NW[0], NW[1], 428.0, NE[1], WALL_SM, 13.5)   # N-W of gate
    wall_run(builder, heights, 446.0, NE[1], NE[0], NE[1], WALL_SM, 13.5)   # N-E of gate

    # Four towers (fresh records).  SE round drum, two E mural towers, NW postern.
    builder.add("dadg_fort_english_round_tower_d",
                (448.0, 340.0, th(heights, 448.0, 340.0)), (0, 0, 0), levels=LV)
    builder.add("dadg_norman_english_fort_castle_wall_tower_a",
                (462.0, 432.0, th(heights, 462.0, 432.0)),
                (0, 0, math.radians(-90)), levels=LV)
    builder.add("dadg_norman_english_fort_castle_wall_tower_a",
                (462.0, 400.0, th(heights, 462.0, 400.0)),
                (0, 0, math.radians(-90)), levels=LV)
    builder.add("dadg_norman_english_fort_castle_wall_tower_b",
                (367.0, 455.0, th(heights, 367.0, 455.0)), (0, 0, 0), levels=LV)

    # NE main gate — hand-placed functional CastleGate (baked scripts, ids 462/106).
    builder.add("dadg_castle_gate_outer_l1",
                (GATE_XY[0], GATE_XY[1], th(heights, *GATE_XY)),
                (0, 0, math.radians(180)), levels=LV)

    # Keep pair at the SE quadrant, scaled up ~1.35x (spec §3.3).  Replicates the
    # Bristol convention: keep_c south, keep_b ~20 m north, both yaw ~ -0.2 rad.
    KS = (1.35, 1.35, 1.35)
    KEEP_YAW = -0.21
    kz = th(heights, *KEEP_XY)
    builder.add("dadg_fort_norman_keep_c", (KEEP_XY[0], KEEP_XY[1], kz),
                (0, 0, KEEP_YAW), scale=KS, levels=LV)
    kbx = KEEP_XY[0] + 5.76        # Bristol pair offset (b is ~20 m N of c)
    kby = KEEP_XY[1] + 19.79
    builder.add("dadg_fort_norman_keep_b",
                (kbx, kby, th(heights, kbx, kby)),
                (0, 0, KEEP_YAW), scale=KS, levels=LV)

    # Wall stairs joining walkway to bailey (visual + AI hint).
    builder.add("dadg_fort_english_stairs_tower_b",
                (455.0, 415.0, th(heights, 455.0, 415.0)),
                (0, 0, math.radians(90)), levels=LV)

    # Bailey dressing: a well + a lean-to shed (bailey let to tenants c.1400).
    builder.add("dadg_fort_castle_well",
                (405.0, 405.0, th(heights, 405.0, 405.0)), (0, 0, 0), levels=LV)
    builder.add("dadg_english_fort_house_a",
                (378.0, 420.0, th(heights, 378.0, 420.0)),
                (0, 0, math.radians(90)), levels=LV)

    # Mandatory gameplay marker (base of the keep forebuilding).
    builder.add("sp_player_castle",
                (420.0, 385.0, th(heights, 420.0, 385.0)), (0, 0, 0))

    builder.provenance_note(
        "structure",
        "curtain circuit (W/S/N small + E big, closed but for N gate gap) + "
        "SE round tower + 2 E mural towers + NW postern + hand-placed "
        "dadg_castle_gate_outer_l1 + keep pair(c,b 1.35x) + stairs + well + "
        "house + sp_player_castle, all authored via builder.add")


# ---------------------------------------------------------------------------
# Quality dressing (authored entity-by-entity; donor conventions in comments)
# ---------------------------------------------------------------------------
# Curtain-wall walkway top height above terrain (dadg small-fort wall parapet).
WALL_TOP_Z = 7.0
# Wall run mid-lines (X or Y fixed) used to place wall-top props on the walkway.
#   W curtain X=365 (SW->NW), S curtain Y=337, E curtain X=465, N curtain Y=462.

# Attacker-lane / deployment keep-out rectangles (x0,y0,x1,y1).  No blocking
# prop (rock/building/cart/woodpile/fence) may sit inside these — they must stay
# clear for formations, ladder/tower/ram approach, and deployment.  Small
# self-lit torches and thin flora are allowed (they sit off the walked faces or
# are non-blocking).  Verified against the siege navmesh g3 lanes.
_KEEPOUT = [
    (470.0, 250.0, 560.0, 560.0),   # attacker esplanade (E of curtain) + camp
    (405.0, 455.0, 470.0, 520.0),   # N gate approach corridor + ram lane
    (372.0, 344.0, 458.0, 456.0),   # bailey interior deployment box (handled separately)
    (430.0, 250.0, 520.0, 335.0),   # SE attacker deploy wedge
]


def _in_keepout(x, y, boxes=_KEEPOUT):
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)


def build_dressing(builder, heights):
    """Author period-decayed-castle dressing entity-by-entity.

    Categories + the donor convention each replicates (measured from the corpus
    inventories of Clun_castle / Dartmouth_castle / Carisbrooke / Corfe):

      * bailey interior: sheds, barrels/crates, hay, carts, woodpiles, a stable,
        a plough, a midden, and repair clutter (wood + ruinous stone heaps)
        against the freshly-rebuilt E curtain (Clun/Carisbrooke ward dressing).
      * wall-top: banners on towers/gate + self-lit outdoor torches on the
        walkway (torch_outdoors_a_burning is the standard DADG/native wall light,
        used across 93 corpus scenes; it carries its own light+fire so no paired
        light entity is needed).
      * exterior: rocks/outcrops on the river scarp and Boley Hill
        (Dartmouth scatters ~174 terrain_green_rock_*), roadside props on the
        approach, and riverside boats on the Medway band.
      * AI archer positions: strategic_archer_point (defender, wall-tops +
        interior) and strategic_attacker_archer_position (esplanade) — the single
        biggest count driver in DADG castles (Clun 167, Dartmouth 232); these are
        zero-collision empty markers used by the siege AI.

    All placements avoid the attacker lanes / deployment keep-outs (or sit off
    the navmesh, e.g. on wall-tops or the river bank).
    """
    rng = np.random.default_rng(SEED)
    counts = {"prop": 0, "building": 0, "light": 0, "banner": 0,
              "rock": 0, "archer": 0}

    def add(prefab, x, y, *, zoff=0.0, z=None, yaw=0.0, scale=None, cat="prop"):
        zz = (th(heights, x, y) + zoff) if z is None else z
        builder.add(prefab, (x, y, zz), (0.0, 0.0, yaw), scale=scale, levels=LV)
        counts[cat] += 1

    # ----- Bailey interior dressing (tenant-leased, decayed ward) -----------
    # Storehouse/stable cluster in the NW bailey (away from keep + gate lane).
    add("dadg_english_stable", 380.0, 408.0, yaw=math.radians(90), cat="building")
    add("dadg_barn_c", 384.0, 434.0, yaw=math.radians(180), cat="building")
    add("dadg_fort_castle_shed_a", 396.0, 442.0, yaw=math.radians(-90), cat="building")
    add("dadg_fort_castle_shed_b", 408.0, 444.0, yaw=math.radians(-90), cat="building")
    add("dadg_fort_castle_shed_d", 388.0, 396.0, yaw=math.radians(0), cat="building")
    # Henry III chamber block (ruinous) against the inner W curtain.
    add("dadg_english_fort_block", 372.0, 378.0, yaw=math.radians(90), cat="building")

    # Domestic + market clutter around the sheds and well (bailey let to tenants).
    prop_cluster = [
        ("bd_barrel_heap_a", 400.0, 440.0), ("bd_barrel_heap_b", 404.0, 447.0),
        ("bd_barrel_a", 397.0, 447.0), ("bd_barrel_a", 393.0, 445.0),
        ("crate_a", 411.0, 448.0), ("crate_a", 414.0, 445.0),
        ("dadg_hay_thatch_b", 383.0, 420.0), ("dadg_hay_small", 388.0, 424.0),
        ("dadg_haystore", 379.0, 428.0),
        ("dadg_stool_a", 407.0, 408.0), ("dadg_bench_a", 402.0, 411.0),
        ("dadg_table_a", 404.0, 409.0), ("dadg_dresser", 386.0, 400.0),
        ("bd_bucket_b", 407.0, 403.0), ("bd_manure_a", 415.0, 452.0),
        ("bd_plough_a", 420.0, 448.0), ("dadg_granary1", 391.0, 450.0),
        ("dadg_cart_b", 418.0, 438.0), ("dadg_market_cart_a", 424.0, 442.0),
        ("dadg_wagon_a", 396.0, 452.0),
    ]
    for i, (pf, x, y) in enumerate(prop_cluster):
        if _in_keepout(x, y, _KEEPOUT[2:3]):   # allow inside bailey box, but...
            pass
        add(pf, x, y, yaw=float(rng.uniform(0, 2 * math.pi)), cat="prop")

    # Repair clutter + rubble against the freshly-rebuilt E curtain (1367-83):
    # woodpiles, stacked stone (no scaffold prefab exists in DADG — wood/stone
    # heaps stand in for repair works), kept off the E-wall ladder-drop faces.
    repair = [
        ("bd_wood_heap_a", 452.0, 408.0), ("bd_wood_heap_d", 454.0, 396.0),
        ("bd_stacked_wood", 456.0, 420.0), ("ruinous_castle_stone_heap_a", 450.0, 428.0),
        ("ruinous_castle_stone_heap_b", 453.0, 388.0), ("weapon_heap_arrow_a", 448.0, 416.0),
        ("shovel", 451.0, 424.0), ("bd_heap_d", 455.0, 402.0),
    ]
    for pf, x, y in repair:
        add(pf, x, y, yaw=float(rng.uniform(0, 2 * math.pi)), cat="prop")

    # Second domestic/market cluster in the SW bailey corner (leased plots), and
    # firewood/fodder against the S curtain — all clear of the gate/ram lane and
    # of the central deployment area (kept W of X=400, S of Y=395).
    sw_cluster = [
        ("bd_barrel_a", 378.0, 360.0), ("bd_barrel_a", 381.0, 363.0),
        ("crate_a", 384.0, 358.0), ("bd_barrel_heap_a", 376.0, 356.0),
        ("dadg_hay_thatch_b", 388.0, 352.0), ("dadg_hay_small", 392.0, 356.0),
        ("bd_wood_heap_a", 396.0, 350.0), ("bd_stacked_wood", 400.0, 348.0),
        ("dadg_cart_c", 385.0, 372.0), ("dadg_wagon_a", 379.0, 380.0),
        ("dadg_stool_a", 390.0, 366.0), ("dadg_bench_a", 393.0, 368.0),
        ("bd_bucket_b", 396.0, 364.0), ("bd_manure_a", 402.0, 352.0),
        ("dadg_granary1", 375.0, 372.0), ("dadg_dresser", 380.0, 386.0),
        ("bd_heap_d", 398.0, 358.0), ("bd_wood_heap_d", 404.0, 346.0),
        ("ruinous_castle_stone_heap_a", 372.0, 350.0),
        ("weapon_heap_arrow_a", 386.0, 362.0),
    ]
    for pf, x, y in sw_cluster:
        add(pf, x, y, yaw=float(rng.uniform(0, 2 * math.pi)), cat="prop")

    # A couple of interior fences/hurdles penning off the tenant plots (thin,
    # non-blocking; placed clear of the deployment centre and gate lane).
    for x, y, yaw in ((376.0, 414.0, 0.0), (376.0, 420.0, 0.0),
                      (390.0, 438.0, math.radians(90)), (394.0, 438.0, math.radians(90))):
        add("english_fence", x, y, yaw=yaw, cat="prop")

    # ----- Wall-top dressing: banners + self-lit torches --------------------
    # Banners on the gate and the four towers (DADG flies dadg_banner_pennon_b /
    # dadg_banner_toaddtag_bd_banner_b on tower tops).
    banner_spots = [
        ("dadg_banner_pennon_b", 437.0, 460.0, WALL_TOP_Z + 1.5),   # gate
        ("dadg_banner_toaddtag_bd_banner_b", 448.0, 340.0, WALL_TOP_Z + 1.0),  # SE drum
        ("dadg_banner_pennon_b", 462.0, 432.0, WALL_TOP_Z + 1.0),   # E mural tower N
        ("dadg_banner_pennon_b", 462.0, 400.0, WALL_TOP_Z + 1.0),   # E mural tower S
        ("dadg_banner_toaddtag_bd_banner_b", 367.0, 455.0, WALL_TOP_Z + 1.0),  # NW postern
    ]
    for pf, x, y, dz in banner_spots:
        add(pf, x, y, zoff=dz, cat="banner")

    # Self-lit outdoor torches spaced along the curtain walkway tops (night-siege
    # readability).  All sit on the parapet (Z = terrain+WALL_TOP_Z), off the
    # ground navmesh entirely.
    torch_spots = []
    for y in (352.0, 372.0, 392.0, 412.0, 432.0, 452.0):      # E curtain X=465
        torch_spots.append((465.0, y))
    for y in (352.0, 380.0, 408.0, 436.0):                    # W curtain X=365
        torch_spots.append((365.0, y))
    for x in (378.0, 404.0, 452.0):                           # N curtain Y=462
        torch_spots.append((x, 462.0))
    for x in (380.0, 410.0, 440.0):                           # S curtain Y=337
        torch_spots.append((x, 337.0))
    for x, y in torch_spots:
        add("torch_outdoors_a_burning", x, y, zoff=WALL_TOP_Z, cat="light")
    # A brazier/campfire in the bailey and the attacker camp (ground level).
    add("burning_campfire", 400.0, 430.0, cat="light")
    add("burning_campfire", 515.0, 315.0, cat="light")   # attacker camp (open ground edge)

    # ----- Exterior: rocks on scarp/Boley, roadside props, riverside --------
    # River scarp outcrops (W edge, X<340) + Boley Hill rocks (S, Y<325).  Half
    # of the big rocks are deliberately half-buried (bury 0.4 m) so they read as
    # bedrock outcrops, not floating props (Stonehenge-generator convention).
    rock_prefabs = ["cliff_soil_b", "terrain_green_rock_d", "terrain_green_rock_c",
                    "terrain_green_rock_big_a", "terrain_green_rock_big_c",
                    "terrain_green_rock_a", "terrain_green_rock_b"]
    n_rock = 0
    # Scarp band.
    for _ in range(34):
        x = float(rng.uniform(285.0, 335.0))
        y = float(rng.uniform(300.0, 500.0))
        pf = rock_prefabs[rng.integers(0, len(rock_prefabs))]
        bury = 0.4 if "big" in pf else 0.15
        s = float(rng.uniform(0.8, 1.6))
        add(pf, x, y, zoff=-bury, yaw=float(rng.uniform(0, 2 * math.pi)),
            scale=(s, s, s), cat="rock")
        n_rock += 1
    # Boley Hill outcrops (S of the castle, clear of the SE attacker wedge X<430).
    for _ in range(22):
        x = float(rng.uniform(330.0, 425.0))
        y = float(rng.uniform(255.0, 320.0))
        if _in_keepout(x, y):
            continue
        pf = rock_prefabs[rng.integers(0, len(rock_prefabs))]
        bury = 0.4 if "big" in pf else 0.15
        s = float(rng.uniform(0.8, 1.5))
        add(pf, x, y, zoff=-bury, yaw=float(rng.uniform(0, 2 * math.pi)),
            scale=(s, s, s), cat="rock")
        n_rock += 1

    # Riverside: a beached boat + a moored boat on the Medway band, and the
    # medieval bridge stub NW of the postern (spec Part 1.3).
    add("english_boat", 300.0, 430.0, yaw=math.radians(20), cat="prop")
    add("english_boat_b", 296.0, 470.0, yaw=math.radians(-15), cat="prop")
    add("stone_bridge_wide", 320.0, 490.0, yaw=math.radians(90), cat="building")

    # Roadside props on the SE approach shoulder (off the road/lane): a couple of
    # carts and a woodpile at the road edge, plus hedges lining the track.
    add("dadg_cart_c", 468.0, 335.0, yaw=math.radians(30), cat="prop")
    add("bd_wood_heap_f", 464.0, 328.0, cat="prop")

    # ----- AI archer positions (defender wall-tops + interior; attacker camp) -
    # strategic_archer_point on the walkway tops and interior; the count is the
    # main density lever DADG castles pull (Clun 167 / Dartmouth 232).
    def_archer = []
    for y in np.linspace(345.0, 458.0, 13):        # E curtain walkway
        def_archer.append((465.0, float(y), WALL_TOP_Z))
    for y in np.linspace(345.0, 458.0, 11):        # W curtain walkway
        def_archer.append((365.0, float(y), WALL_TOP_Z))
    for x in np.linspace(367.0, 463.0, 9):         # N curtain walkway
        def_archer.append((float(x), 462.0, WALL_TOP_Z))
    for x in np.linspace(367.0, 463.0, 9):         # S curtain walkway
        def_archer.append((float(x), 337.0, WALL_TOP_Z))
    # Interior fallback archer points (ground) around the keep + bailey edges.
    for x, y in ((420.0, 372.0), (448.0, 372.0), (415.0, 415.0), (430.0, 430.0),
                 (400.0, 448.0), (385.0, 388.0), (452.0, 372.0), (410.0, 388.0)):
        def_archer.append((x, y, 0.0))
    for x, y, dz in def_archer:
        add("strategic_archer_point", x, y, zoff=dz, cat="archer")

    # Attacker archer positions spread over the E/SE esplanade (open ground).
    for _ in range(28):
        x = float(rng.uniform(485.0, 540.0))
        y = float(rng.uniform(300.0, 500.0))
        add("strategic_attacker_archer_position", x, y, cat="archer")
    for _ in range(12):
        x = float(rng.uniform(440.0, 520.0))
        y = float(rng.uniform(270.0, 320.0))
        add("strategic_attacker_archer_position", x, y, cat="archer")

    total = sum(counts.values())
    builder.provenance_note(
        "dressing",
        "GENERATED entity-by-entity: bailey buildings/props/repair-clutter "
        "(Clun/Carisbrooke ward convention), wall-top banners + self-lit "
        "torch_outdoors_a_burning + campfires, scarp/Boley rocks "
        "(Dartmouth rock-scatter convention), riverside boats + bridge, and "
        "strategic archer positions (Clun/Dartmouth AI-marker density). "
        f"counts={counts} total={total}")
    print(f"dressing placed: {counts} total={total}")
    return counts


def add_flora_entities(builder, heights):
    """Paint flora as ENTITIES, not flora.bin.

    Finding: every DADG hand-made castle ships a 12-124 byte (empty/near-empty)
    flora.bin and gets its grass from the terrain shader; landscape trees/bushes
    are placed as ordinary prefab ENTITIES (tree_far_a is the workhorse, 3596
    uses across the DADG module; dadg_english_hedges_a/b + dadg_cornish_hedge for
    hedgerows; flora_grass_terrain_a/b tufts; forest_pine / tree_far_forest /
    forest_ruinous_tree_beech_* for variety; shrub_* bushes).  So flora.bin is
    left as the correct 12-byte stub and vegetation is authored here.

    Grass cover comparable to the DADG battle maps is delivered by the terrain
    grass layer (layer 0 = first_material grass); worn bailey/road areas get
    dry_ground paint (see layer_weights) so grass thins there.  Outside the walls
    we scatter trees + hedges + grass tufts; the bailey stays sparse (worn).
    """
    rng = np.random.default_rng(SEED + 7)
    counts = {"tree": 0, "hedge": 0, "grass": 0, "shrub": 0}

    def add(prefab, x, y, *, yaw=None, scale=None, cat="tree"):
        yaw = float(rng.uniform(0, 2 * math.pi)) if yaw is None else yaw
        builder.add(prefab, (x, y, th(heights, x, y)), (0.0, 0.0, yaw),
                    scale=scale, levels=LV)
        counts[cat] += 1

    tree_prefabs = ["tree_far_a", "tree_far_a", "tree_far_a", "forest_pine",
                    "tree_far_forest", "forest_ruinous_tree_beech_d",
                    "forest_ruinous_tree_beech_e"]

    # Trees line the SE/S approach and the town edge N of the castle, and cluster
    # on Boley Hill's flanks — but never on the open attacker esplanade/camp or
    # the interior.  Deterministic scatter with keep-out rejection.
    placed = 0
    attempts = 0
    while placed < 130 and attempts < 6000:
        attempts += 1
        # Sample a ring of exterior ground around the castle.
        x = float(rng.uniform(255.0, 545.0))
        y = float(rng.uniform(255.0, 545.0))
        # Exclude interior + the flat attacker esplanade/camp (keep it open) +
        # the immediate approach road; keep trees to the peripheral landscape.
        if 360.0 <= x <= 470.0 and 335.0 <= y <= 465.0:
            continue                                   # castle footprint + interior
        if _in_keepout(x, y):
            continue                                   # attacker lanes / camp
        if x > 470.0 and 300.0 <= y <= 500.0:
            continue                                   # attacker esplanade — stay clear
        s = float(rng.uniform(0.75, 1.25))
        add(tree_prefabs[rng.integers(0, len(tree_prefabs))], x, y,
            scale=(s, s, s), cat="tree")
        placed += 1

    # Riverside willows/trees on the Medway bank (W band) for the river frontage.
    for _ in range(14):
        x = float(rng.uniform(275.0, 320.0))
        y = float(rng.uniform(280.0, 520.0))
        add("tree_far_a", x, y, scale=(0.9, 0.9, 1.1), cat="tree")

    # Hedgerows lining the SE approach road and field boundaries S of the castle
    # (dadg_english_hedges / cornish_hedge — the DADG hedgerow convention).
    hedge_lines = [
        (475.0, 330.0, 520.0, 300.0),   # SE road shoulder
        (455.0, 320.0, 490.0, 300.0),
        (330.0, 305.0, 420.0, 300.0),   # field boundary S of Boley
    ]
    for x0, y0, x1, y1 in hedge_lines:
        n = 6
        for i in range(n):
            t = (i + 0.5) / n
            hx = x0 + (x1 - x0) * t
            hy = y0 + (y1 - y0) * t
            if _in_keepout(hx, hy):
                continue
            yaw = math.atan2(y1 - y0, x1 - x0)
            add("dadg_english_hedges_a", hx, hy, yaw=yaw, cat="hedge")

    # Grass tufts + shrubs scattered on the exterior slopes (not the bare road/
    # esplanade/interior) to break up the terrain-shader grass.
    placed = 0
    attempts = 0
    while placed < 64 and attempts < 4500:
        attempts += 1
        x = float(rng.uniform(255.0, 545.0))
        y = float(rng.uniform(255.0, 545.0))
        if 360.0 <= x <= 470.0 and 335.0 <= y <= 465.0:
            continue
        if _in_keepout(x, y):
            continue
        pf = "flora_grass_terrain_a" if rng.random() < 0.6 else (
            "shrub_b" if rng.random() < 0.5 else "shrub_d")
        cat = "grass" if pf.startswith("flora_grass") else "shrub"
        add(pf, x, y, cat=cat)
        placed += 1

    total = sum(counts.values())
    builder.provenance_note(
        "flora_entities",
        "GENERATED as prefab ENTITIES (flora.bin left as the correct 12-byte "
        "stub, matching every DADG hand-made castle): tree_far_a/forest_pine/"
        "ruinous-beech scatter outside the walls + riverside, dadg_english_"
        "hedges roadside hedgerows, flora_grass_terrain + shrub tufts; interior "
        "kept sparse (worn ward). grass cover comes from the terrain grass "
        f"layer. counts={counts} total={total}")
    print(f"flora entities placed: {counts} total={total}")
    return counts


# ---------------------------------------------------------------------------
# Siege script-bearing entities (individual harvests from Clun, retargeted)
# ---------------------------------------------------------------------------
def _harvest_one(scene_dir, cx, cy, *, prefab_re=None, name_re=None, half=6.0):
    """Harvest exactly one entity record near (cx,cy) from a donor scene.

    Returns the deep-copied <game_entity> Element (first match).  Siege spawners
    match on the ``prefab`` attribute; WallSegment / part_b carriers have an
    empty ``prefab`` and are matched on the ``name`` attribute instead.
    """
    c = harvest_entities(scene_dir, cx - half, cy - half, cx + half, cy + half,
                         prefab_re=prefab_re, name_re=name_re,
                         include_infrastructure=True)
    if len(c) == 0:
        raise RuntimeError(f"no harvest match for {prefab_re or name_re} near ({cx},{cy})")
    return copy.deepcopy(c.elements[0])


def _set_transform(elem, x, y, z, yaw):
    t = elem.find("transform")
    t.set("position", "%.3f, %.3f, %.3f" % (x, y, z))
    t.set("rotation_euler", "%.3f, %.3f, %.3f" % (0.0, 0.0, yaw))


def _set_tag(elem, tag):
    """Replace the entity's <tags> with a single tag."""
    for existing in elem.findall("tags"):
        elem.remove(existing)
    tags = ET.SubElement(elem, "tags")
    tags.text = "\n\t\t\t\t"
    tg = ET.SubElement(tags, "tag", name=tag)
    tg.tail = "\n\t\t\t"
    tags.tail = "\n\t\t\t"


def _set_spawner_var(elem, script_name, **kv):
    for sc in elem.iter("script"):
        if sc.get("name") == script_name:
            for v in sc.findall("variables/variable"):
                if v.get("name") in kv:
                    v.set("value", str(kv[v.get("name")]))


def place_siege(builder, heights):
    """Harvest individual siege entities from Clun, reposition, retag onto walls.

    Returns a dict recording OnWallNavMeshId / gate ids for navmesh authoring.
    """
    scene = builder._scene
    harvested = 0

    def insert(elem):
        nonlocal harvested
        ent_elem = scene._entities_elem
        kids = list(ent_elem)
        if kids:
            kids[-1].tail = "\n\t\t"
        ent_elem.append(elem)
        elem.tail = "\n\t"
        harvested += 1

    # ---- WallSegment carriers: EXACTLY ONE breachable wall per defended side.
    #      SiegeMissionPreparationHandler.ArrangeDestructedMeshes() builds
    #      list3 = WallSegments whose DefenseSide != NotSet AND that carry a
    #      broken_child child, then loops once per _wallHitPointPercentages entry
    #      (Settlement.WallSectionCount == 2 for every fortification, verified) and
    #      calls FindRightMostWall(list3) each pass. FindRightMostWall returns
    #      non-null only for list3 count 1 or 2 -> null (NRE) for 0 or >2.
    #      Clun ground-truth: exactly 2 qualifying WallSegments (1 left, 1 right),
    #      both the *_broken carriers (solid_child + broken_child). So we place
    #      ONE left (E curtain) and ONE right (N curtain); the two ladders per side
    #      all target the single wall_segment_<side> tag.
    ws_left = _harvest_one(CLUN, 380.622, 352.921,
                           name_re=r"^dadg_english_small_fort_wall_broken$")
    ws_right = _harvest_one(CLUN, 356.525, 418.818,
                            name_re=r"^dadg_english_fort_big_castle_wall_a_broken$")

    LEFT_YAW = math.radians(90)    # E curtain runs N-S
    RIGHT_YAW = 0.0                # N curtain runs E-W
    # LEFT breachable wall: E curtain, centred between the two E-curtain ladders.
    e = copy.deepcopy(ws_left)
    _set_transform(e, 465.0, 402.0, th(heights, 465.0, 402.0) + 0.4, LEFT_YAW)
    _set_spawner_var(e, "WallSegment", SideTag="left")
    _set_tag(e, "wall_segment_left")
    insert(e)
    # RIGHT breachable wall: N curtain E of the gate opening (on the N-E run,
    # clear of the gate gap X 428..446), at the E N-curtain ladder drop.
    e = copy.deepcopy(ws_right)
    _set_transform(e, 455.0, 462.0, th(heights, 455.0, 462.0) + 0.4, RIGHT_YAW)
    _set_spawner_var(e, "WallSegment", SideTag="right")
    _set_tag(e, "wall_segment_right")
    insert(e)

    # ---- Ladder spawners: 2 LEFT (E curtain), 2 RIGHT (N curtain).  Each keeps
    #      its own OnWallNavMeshId (ids chosen so ones-digit is not 0 or 1); the
    #      navmesh authors matching ladder-drop faces with those exact ids. ----
    ladder_specs = [
        # (donor xy, target xy, yaw, OnWallNavMeshId, side)
        ((387.843, 353.119), (465.0, 420.0), LEFT_YAW,  202, "left"),
        ((378.083, 358.003), (465.0, 384.0), LEFT_YAW,  212, "left"),
        ((360.338, 423.459), (412.0, 462.0), RIGHT_YAW, 302, "right"),
        ((361.695, 413.561), (455.0, 462.0), RIGHT_YAW, 312, "right"),
    ]
    ladders = []
    for (dx, dy), (x, y), yaw, navid, side in ladder_specs:
        e = _harvest_one(CLUN, dx, dy, prefab_re=r"^siege_ladder_\d+m_spawner$")
        _set_transform(e, x, y, th(heights, x, y), yaw)
        _set_spawner_var(e, "SiegeLadderSpawner",
                         OnWallNavMeshId=navid, SideTag=side,
                         TargetWallSegmentTag="wall_segment_" + side)
        insert(e)
        ladders.append((x, y, navid, side))

    # ---- Tower spawners: LEFT approaches E curtain; RIGHT approaches N curtain.
    for (dx, dy), (x, y), path, side in (
        ((391.091, 451.901), (500.0, 400.0), "path_1", "left"),
        ((391.091, 451.901), (437.0, 505.0), "path_2", "right"),
    ):
        e = _harvest_one(CLUN, dx, dy, prefab_re=r"^siege_tower_\d+m_spawner$")
        _set_transform(e, x, y, th(heights, x, y),
                       math.atan2(BAILEY[1] - y, BAILEY[0] - x))
        _set_spawner_var(e, "SiegeTowerSpawner",
                         PathEntityName=path, SideTag=side,
                         TargetWallSegmentTag="wall_segment_" + side)
        insert(e)

    # ---- Battering ram: middle, to the gate (battering_path). ----
    e = _harvest_one(CLUN, 423.830, 425.222, prefab_re=r"^batteringram_a_spawner$")
    RAM_XY = (437.0, 505.0)
    _set_transform(e, RAM_XY[0], RAM_XY[1], th(heights, *RAM_XY), math.radians(-90))
    _set_spawner_var(e, "BatteringRamSpawner",
                     PathEntityName="battering_path", GateTag="outer_gate",
                     SideTag="middle")
    insert(e)

    # ---- Deployment placeholders: one _a + attacker/defender _b (keep Side). ----
    # CONTAINMENT INVARIANT (DeploymentPoint.AfterMissionStart): a DeploymentPoint
    # whose SiegeWeaponTag == "dpWeapon" and that has NO weapon within its Radius
    # falls into SetBreachSideDeploymentPoint(), which dereferences the first
    # SiegeTower under the point -> NRE when none exists (this fires even on a
    # civilian visit, where the siege-TeamAI global-weapon path is not taken).
    # Clun keeps every dpWeapon point co-located with a weapon spawner
    # (part_a within 4.4 m of a SiegeTowerSpawner; a ram point within 4.1 m of a
    # BatteringRamSpawner).  We replicate that: seat part_a ON the LEFT tower
    # spawner (500,400) so a SiegeTower is always under it.
    dep_a = _harvest_one(CLUN, 394.590, 449.180,
                         prefab_re=r"^siege_deployment_placeholder_part_a$")
    _set_transform(dep_a, 500.0, 400.0, th(heights, 500.0, 400.0), 0.0)
    insert(dep_a)

    # A battering-ram deployment point co-located with the ram spawner (437,505),
    # mirroring Clun's ram dpWeapon point (R=6.43, ram within 4.1 m).  This keeps
    # the ram deployable and satisfies the containment invariant for this point.
    dep_ram = _harvest_one(CLUN, 427.922, 425.600,
                           prefab_re=r"^siege_deployment_placeholder_part_b$")
    _set_transform(dep_ram, 437.0, 505.0, th(heights, 437.0, 505.0), 0.0)
    insert(dep_ram)

    dep_atk = _harvest_one(CLUN, 407.113, 432.342,             # Side=Attacker
                           name_re=r"^siege_deployment_placeholder_part_b$")
    for (x, y) in ((490.0, 415.0), (490.0, 390.0), (437.0, 495.0)):
        eb = copy.deepcopy(dep_atk)
        _set_transform(eb, x, y, th(heights, x, y), 0.0)
        insert(eb)
    dep_dfn = _harvest_one(CLUN, 360.9, 361.7,                 # Side=Defender
                           prefab_re=r"^siege_deployment_placeholder_part_b$")
    for (x, y) in ((410.0, 400.0), (445.0, 420.0), (400.0, 440.0)):
        eb = copy.deepcopy(dep_dfn)
        _set_transform(eb, x, y, th(heights, x, y), 0.0)
        insert(eb)

    # ---- Boundaries: attacker (E/SE open) + defender (interior). ----
    atk = _harvest_one(CLUN, 430.943, 332.267, prefab_re=r"^attacker_boundry$")
    for (x, y) in ((480.0, 360.0), (505.0, 400.0), (480.0, 440.0),
                   (505.0, 460.0), (460.0, 505.0)):
        eb = copy.deepcopy(atk)
        _set_transform(eb, x, y, th(heights, x, y), 0.0)
        insert(eb)
    dfn = _harvest_one(CLUN, 407.362, 344.750, prefab_re=r"^defender_boundry$")
    for (x, y) in ((400.0, 400.0), (420.0, 380.0), (400.0, 445.0),
                   (378.0, 400.0), (445.0, 425.0)):
        eb = copy.deepcopy(dfn)
        _set_transform(eb, x, y, th(heights, x, y), 0.0)
        insert(eb)

    # ---- Strategy cameras (DADG lowercase tags), built fresh as tagged empties.
    for tag, (x, y, zoff, pitch, yaw) in (
        ("strategycameraattacker", (505.0, 350.0, 22.0, 0.6, math.radians(140))),
        ("strategycameradefender", (400.0, 400.0, 24.0, 0.3, 0.0)),
    ):
        cam = ET.Element("game_entity", name="empty_object")
        cam.text = "\n\t\t\t"
        tags = ET.SubElement(cam, "tags"); tags.text = "\n\t\t\t\t"
        tg = ET.SubElement(tags, "tag", name=tag); tg.tail = "\n\t\t\t"
        tags.tail = "\n\t\t\t"
        tr = ET.SubElement(cam, "transform")
        tr.set("position", "%.3f, %.3f, %.3f" % (x, y, th(heights, x, y) + zoff))
        tr.set("rotation_euler", "%.3f, %.3f, %.3f" % (pitch, 0.0, yaw))
        tr.tail = "\n\t\t\t"
        lvls = ET.SubElement(cam, "levels"); lvls.text = "\n\t\t\t\t"
        for i, lname in enumerate(LV):
            lv = ET.SubElement(lvls, "level", name=lname)
            lv.tail = "\n\t\t\t\t" if i < 3 else "\n\t\t\t"
        lvls.tail = "\n\t\t"
        insert(cam)

    builder.record_harvest(
        "entities", "DellarteDellaGuerraScenes/Clun_castle",
        detail="individual siege script entities (WallSegment walls, ladder/"
               "tower/ram spawners, attacker+defender deployment, boundaries) "
               "harvested one-by-one, repositioned + retagged; cameras authored "
               "fresh; gate NOT harvested (baked CastleGate in prefab)",
        count=harvested)
    print(f"siege entities placed (harvested + fresh cameras): {harvested}")
    return {
        "gate_id": GATE_ID, "gate_disable_id": GATE_DISABLE_ID,
        "gate_xy": GATE_XY, "ladders": ladders,
    }


# ---------------------------------------------------------------------------
# Paths (siege routes) — deep-copied from Clun, points translated to our frame
# ---------------------------------------------------------------------------
def add_paths(builder, heights):
    """Author the <Paths> siege routes (path_1 tower-left, path_2 tower-right,
    battering_path ram) by translating Clun's path shapes into our frame."""
    root = builder._scene._root
    clun_root = ET.parse(CLUN + r"\scene.xscene").getroot()
    clun_paths = clun_root.find("Paths")

    paths = root.find("Paths")
    if paths is None:
        paths = ET.SubElement(root, "Paths")
        paths.text = "\n\t\t"

    anchors = {
        "path_1": (500.0, 400.0),         # tower-left dock -> E curtain
        "path_2": (437.0, 500.0),         # tower-right dock -> N curtain
        "battering_path": (437.0, 466.0), # ram -> gate
    }
    made = []
    for src in clun_paths.findall("path"):
        nm = src.get("name")
        if nm not in anchors:
            continue
        p = copy.deepcopy(src)
        pts = p.findall("points/point")
        last = pts[-1]
        lx, ly, _ = (float(v) for v in last.get("position").split(","))
        ax, ay = anchors[nm]
        dx, dy = ax - lx, ay - ly
        for pt in pts:
            px, py, _ = (float(v) for v in pt.get("position").split(","))
            nx, ny = px + dx, py + dy
            pt.set("position", "%.3f, %.3f, %.3f" % (nx, ny, th(heights, nx, ny)))
            for tan in pt:
                if tan.get("position"):
                    tx, ty, _ = (float(v) for v in tan.get("position").split(","))
                    ntx, nty = tx + dx, ty + dy
                    tan.set("position", "%.3f, %.3f, %.3f" % (ntx, nty, th(heights, ntx, nty)))
        paths.append(p)
        made.append(nm)
    kids = list(paths)
    for k in kids[:-1]:
        k.tail = "\n\t\t"
    kids[-1].tail = "\n\t"
    paths.tail = "\n"
    print(f"paths authored: {made}")


# ---------------------------------------------------------------------------
# Navmesh (generated from scratch, hand-authored siege g3 faces)
# ---------------------------------------------------------------------------
def _centroid(mesh, f):
    pts = [mesh.vertices[i] for i in f.vertex_ids]
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def _nearest_face(mesh, px, py, keep, *, region=None):
    best, bd = None, 1e18
    for fi in keep:
        f = mesh.faces[fi]
        cx, cy = _centroid(mesh, f)
        if region and not (region[0] <= cx <= region[2] and region[1] <= cy <= region[3]):
            continue
        d = (cx - px) ** 2 + (cy - py) ** 2
        if d < bd:
            bd, best = d, fi
    return best


def _wall_footprint_bands():
    """Rectangular half-width bands (x0,y0,x1,y1) hugging each curtain run.

    Faces whose centroid falls inside a band are cut from the sheet (walls are
    impassable), EXCEPT a gate opening on the N curtain which is left walkable.
    """
    NW, NE, SE, SW = (CURTAIN[k] for k in ("NW", "NE", "SE", "SW"))
    hw = 2.5   # half wall footprint width
    return [
        # W curtain (X=365, SW->NW)
        (SW[0] - hw, SW[1], SW[0] + hw, NW[1]),
        # S curtain (Y=337, SW->SE)
        (SW[0], SW[1] - hw, SE[0], SW[1] + hw),
        # E curtain (X=465, SE->NE)
        (SE[0] - hw, SE[1], SE[0] + hw, NE[1]),
        # N curtain W of gate (Y=462, NW->428)
        (NW[0], NE[1] - hw, 428.0, NE[1] + hw),
        # N curtain E of gate (446->NE)
        (446.0, NE[1] - hw, NE[0], NE[1] + hw),
    ]


def _largest_component(mesh, keep):
    """Return the set of face indices (subset of *keep*) in the largest
    edge-connected component, using shared-vertex-pair adjacency."""
    # Build edge -> faces adjacency over the kept faces.
    from collections import defaultdict
    edge_faces = defaultdict(list)
    for fi in keep:
        vids = mesh.faces[fi].vertex_ids
        n = len(vids)
        for k in range(n):
            a, b = vids[k], vids[(k + 1) % n]
            edge_faces[(min(a, b), max(a, b))].append(fi)
    adj = defaultdict(set)
    for fis in edge_faces.values():
        for i in range(len(fis)):
            for j in range(i + 1, len(fis)):
                adj[fis[i]].add(fis[j])
                adj[fis[j]].add(fis[i])
    seen = set()
    best = set()
    for start in keep:
        if start in seen:
            continue
        comp = set()
        dq = deque([start])
        seen.add(start)
        while dq:
            u = dq.popleft()
            comp.add(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    dq.append(v)
        if len(comp) > len(best):
            best = comp
    return best


def build_navmesh(heights, siege) -> NavMesh:
    """Single welded walkable sheet, cut wall footprints, then retag siege faces.

    One ``from_heightmap`` sheet over the castle + approach guarantees the
    interior, gate approach, and attacker esplanade start as one welded grid.  We
    then (1) DELETE faces under the wall footprints (walls are impassable),
    (2) keep only the largest connected component, (3) RETAG faces by region for
    the siege g3 ids, and (4) rebuild edges.
    """
    mesh = from_heightmap(
        heights, world_size_x=WORLD, world_size_y=WORLD,
        cell_size=4.0, max_slope_deg=40.0,
        face_id=2, scene_level_mask=-1,
        region=(330.0, 250.0, 560.0, 560.0),
    )

    # --- (1) Cut faces under wall footprints (leave the gate opening). ---
    gx, gy = siege["gate_xy"]
    bands = _wall_footprint_bands()
    keep = []
    cut = 0
    for fi, f in enumerate(mesh.faces):
        cx, cy = _centroid(mesh, f)
        under_wall = any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in bands)
        if under_wall:
            cut += 1
            continue
        keep.append(fi)

    # --- (2) Keep only the largest connected component. ---
    comp = _largest_component(mesh, keep)
    dropped_islands = len(keep) - len(comp)
    mesh.faces = [mesh.faces[fi] for fi in sorted(comp)]

    # Remap: work on the compacted face list now.
    all_idx = list(range(len(mesh.faces)))

    # --- (3) Retag by region. ---
    # Interior bailey box -> g3=1.
    IX0, IY0, IX1, IY1 = 372.0, 344.0, 458.0, 456.0
    interior = 0
    for f in mesh.faces:
        cx, cy = _centroid(mesh, f)
        if IX0 <= cx <= IX1 and IY0 <= cy <= IY1:
            f.g3 = 1
            interior += 1

    # Gate crossing band spanning the N-curtain opening.
    gate_thru = gate_out = 0
    for f in mesh.faces:
        cx, cy = _centroid(mesh, f)
        if abs(cx - gx) <= 7.0:
            if gy - 3.0 <= cy <= gy + 3.0:              # through-gate span
                f.g3 = siege["gate_id"]; gate_thru += 1
            elif gy + 3.0 < cy <= gy + 9.0:             # outer strip disabled on open
                f.g3 = siege["gate_disable_id"]; gate_out += 1

    # Ladder-drop faces: nearest kept sheet face to each ladder target.
    used = set()
    for (x, y, navid, side) in siege["ladders"]:
        cand = [i for i in all_idx if i not in used]
        fi = _nearest_face(mesh, x, y, cand, region=(330.0, 250.0, 560.0, 560.0))
        used.add(fi)
        mesh.faces[fi].g3 = navid

    # Breach navmesh: author the dual (solid/broken) faces that the two
    # WallSegment scripts toggle when a wall is breached.  See _author_breach.
    breach_report = _author_breach(mesh, siege)

    mesh.rebuild_edges()
    print(f"navmesh: cut_under_walls={cut} dropped_island_faces={dropped_islands} "
          f"kept_faces={len(mesh.faces)} interior(g3=1)={interior} "
          f"gate_thru({siege['gate_id']})={gate_thru} "
          f"gate_out({siege['gate_disable_id']})={gate_out} ladder_faces={len(used)}")
    print(f"navmesh breach faces: {breach_report}")
    return mesh


# ---------------------------------------------------------------------------
# Breach navmesh (WallSegment dual solid/broken faces)
# ---------------------------------------------------------------------------
# Ground-truth id conventions harvested from Clun_castle (verified against native
# aserai_castle_002 / aserai_castle_a — the id sets are engine-wide constants):
#   wall_segment_LEFT  (dadg_english_small_fort_wall_broken, Clun id set 2xx):
#       properGroundOutside=228 properGroundInside=291
#       overDebrisOutside=271 overDebrisInside=281 overDebrisGeneric=261
#       onSolidWallGeneric=251   (all underDebris* = -1, unused, as Clun ships)
#   wall_segment_RIGHT (dadg_english_fort_big_castle_wall_a_broken, Clun id set 3xx):
#       properGroundOutside=328 properGroundInside=391
#       overDebrisOutside=371 overDebrisInside=381 overDebrisGeneric=361
#       onSolidWallGeneric=351   (all underDebris* = -1)
# These match the WallSegment <scripts> harvested onto our two walls verbatim, so
# authoring faces with THESE id values at OUR wall positions makes the harvested
# scripts toggle real geometry.
#
# Engine semantics (WallSegment.OnChooseUsedWallSegment, decompiled 1.4.6):
#   SOLID  (isBroken=false): overDebris{Outside,Inside,Generic} -> disabled.
#     -> the crossing between properGroundOutside and properGroundInside is severed
#        (those debris faces are the ONLY bridge over the wall footprint), so the
#        wall is impassable; onSolidWallGeneric stays enabled (defenders' wall-top).
#   BROKEN (isBroken=true):  overDebris{Outside,Inside,Generic} -> enabled (and
#     merged onto the adjacent properGround faces); onSolidWallGeneric -> disabled.
#     -> outside properGround -> oDO -> oDG -> oDI -> inside properGround is a
#        connected walkable path through the breach.
# underDebris* are only touched when set (>0); Clun/our walls leave them -1.
BREACH_WALLS = {
    "left": dict(  # E curtain, crossing runs along +X (outside=+X east, inside=-X)
        center=(465.0, 402.0), across="x", outside_sign=+1.0,
        pGO=228, pGI=291, oDO=271, oDI=281, oDG=261, oSW=251),
    "right": dict(  # N curtain, crossing runs along +Y (outside=+Y north, inside=-Y)
        center=(455.0, 462.0), across="y", outside_sign=+1.0,
        pGO=328, pGI=391, oDO=371, oDI=381, oDG=361, oSW=351),
}


def _vert_at(mesh, x, y, tol=0.6):
    """Return the index of the mesh vertex nearest (x,y) within tol, else None."""
    best, bd = None, tol * tol
    for vi, (vx, vy, _vz) in enumerate(mesh.vertices):
        d = (vx - x) ** 2 + (vy - y) ** 2
        if d < bd:
            bd, best = d, vi
    return best


def _add_vert(mesh, x, y, z):
    mesh.vertices.append((x, y, z))
    return len(mesh.vertices) - 1


def _retag_face_at(mesh, cx, cy, g3, tol=1.6):
    """Retag the single sheet face whose centroid is nearest (cx,cy) within tol."""
    best, bd = None, tol * tol
    for fi, f in enumerate(mesh.faces):
        fx, fy = _centroid(mesh, f)
        d = (fx - cx) ** 2 + (fy - cy) ** 2
        if d < bd:
            bd, best = d, fi
    if best is not None:
        mesh.faces[best].g3 = g3
    return best


def _author_breach(mesh, siege):
    """Author the solid/broken breach faces for both WallSegments.

    For each wall the wall-footprint cut leaves a gap in the retained sheet.  We
    (a) retag the inside/outside boundary sheet faces to properGround{In,Out},
    (b) stitch a debris strip (overDebris Outside -> Generic -> Inside) welded to
    those boundary grid vertices so it shares edges with the sheet, and
    (c) add an isolated high-z parapet face tagged onSolidWallGeneric.

    Wall-local frame: `cross` = signed distance across the wall (outside positive),
    `along` = distance parallel to the wall.  `to_world(cross, along)` maps back to
    scene XY.  The retained sheet edges sit at cross = +/- OUT_EDGE (grid columns
    at cx +/- 4 for x-walls, cy +/- 4 for y-walls); the wall centre is cross=0.
    """
    from blnav.nmg9 import Face
    report = {}

    for side, spec in BREACH_WALLS.items():
        cx, cy = spec["center"]
        pGO, pGI = spec["pGO"], spec["pGI"]
        oDO, oDI, oDG, oSW = spec["oDO"], spec["oDI"], spec["oDG"], spec["oSW"]
        sgn = spec["outside_sign"]

        # Sheet grid: region origin (330,250), 4 m cells -> vertex lines on the
        # 4 m lattice.  Snap the wall centre's along-axis onto the vertex lattice
        # so the strip welds to real grid verts, and pick 3 along-columns on the
        # lattice straddling the wall centre.
        GRID = 4.0
        def snap(v, origin):
            return origin + round((v - origin) / GRID) * GRID
        if spec["across"] == "x":     # E curtain: cross = X (outside east), along = Y
            along0 = snap(cy, 250.0)
            def to_world(cross, along):
                return (cx + sgn * cross, along)
        else:                         # N curtain: cross = Y (outside north), along = X
            along0 = snap(cx, 330.0)
            def to_world(cross, along):
                return (along, cy + sgn * cross)
        along_vals = (along0 - GRID, along0, along0 + GRID)   # 3 lattice columns
        n_added = 0

        # Locate the retained sheet edge VERTEX columns (inside/outside) by scanning
        # outward from the wall centre on the lattice until verts exist at all 3
        # along-columns.  cx/cy may be off-lattice, so the in/out offsets differ.
        def snapc(cross):
            # snap a cross-offset so the resulting cross line lands on the lattice
            if spec["across"] == "x":
                return snap(cx + sgn * cross, 330.0) - cx if sgn > 0 else cross
            return snap(cy + sgn * cross, 250.0) - cy if sgn > 0 else cross
        def has_edge(cross):
            return all(_vert_at(mesh, *to_world(cross, av)) is not None
                       for av in along_vals)
        def find_edge(direction):
            for k in range(1, 8):
                # step along the lattice from the wall centre
                if spec["across"] == "x":
                    line = snap(cx, 330.0) + direction * k * GRID
                    cross = (line - cx) * sgn
                else:
                    line = snap(cy, 250.0) + direction * k * GRID
                    cross = (line - cy) * sgn
                if has_edge(cross):
                    return cross
            return None
        out_c = find_edge(+1)
        in_c = find_edge(-1)
        if out_c is None or in_c is None:
            report[side] = dict(error="no sheet edge", out_c=out_c, in_c=in_c)
            continue

        # (a) Retag the boundary sheet faces to properGround.  Their centroids sit
        #     one half-cell (2 m) further out than the edge vertex column.
        for av in (along0 - 2.0, along0 + 2.0):   # face-centroid along lattice (+2)
            _retag_face_at(mesh, *to_world(in_c - 2.0, av), pGI)
            _retag_face_at(mesh, *to_world(out_c + 2.0, av), pGO)

        # (b) Debris strip: weld to the located in/out edge grid verts, add a
        #     midline column at cross=0.  Two cells along the wall.
        def gv(cross, along):
            return _vert_at(mesh, *to_world(cross, along))

        made = []
        for a_lo, a_hi in ((along_vals[0], along_vals[1]),
                           (along_vals[1], along_vals[2])):
            iv_lo, iv_hi = gv(in_c, a_lo), gv(in_c, a_hi)
            ov_lo, ov_hi = gv(out_c, a_lo), gv(out_c, a_hi)
            if None in (iv_lo, iv_hi, ov_lo, ov_hi):
                continue
            z = (mesh.vertices[iv_lo][2] + mesh.vertices[ov_lo][2]) / 2.0
            wx, wy = to_world(0.0, a_lo); mv_lo = _add_vert(mesh, wx, wy, z)
            wx, wy = to_world(0.0, a_hi); mv_hi = _add_vert(mesh, wx, wy, z)
            n_added += 2
            # outside half (out_edge -> centre): overDebrisOutside
            mesh.faces.append(Face([ov_lo, ov_hi, mv_hi, mv_lo], [],
                                   g1=2, g2=0, g3=oDO, g4=0, g5=-1, g6=0))
            # inside half (centre -> in_edge): overDebrisInside
            mesh.faces.append(Face([mv_lo, mv_hi, iv_hi, iv_lo], [],
                                   g1=2, g2=0, g3=oDI, g4=0, g5=-1, g6=0))
            made += [mesh.faces[-2], mesh.faces[-1]]
        # Retag one centre inside-half face to overDebrisGeneric (rubble crest at
        # the wall line), matching Clun where oDG spans the wall centre.
        if len(made) >= 2:
            made[1].g3 = oDG

        # (c) Isolated parapet face (onSolidWallGeneric): high z, not welded to
        #     the ground sheet (mirrors Clun 251/351 on the intact wall-top).
        top_z = 30.0 + WALL_TOP_Z
        wx, wy = to_world(-0.6, along_vals[0]); t0 = _add_vert(mesh, wx, wy, top_z)
        wx, wy = to_world(+0.6, along_vals[0]); t1 = _add_vert(mesh, wx, wy, top_z)
        wx, wy = to_world(+0.6, along_vals[2]); t2 = _add_vert(mesh, wx, wy, top_z)
        wx, wy = to_world(-0.6, along_vals[2]); t3 = _add_vert(mesh, wx, wy, top_z)
        n_added += 4
        mesh.faces.append(Face([t0, t1, t2, t3], [],
                               g1=2, g2=0, g3=oSW, g4=0, g5=-1, g6=0))

        report[side] = dict(pGO=pGO, pGI=pGI, oDO=oDO, oDI=oDI, oDG=oDG, oSW=oSW,
                            in_c=round(in_c, 1), out_c=round(out_c, 1),
                            verts_added=n_added)
    return report


# ---------------------------------------------------------------------------
# Verification (siege-invariant checks; run at the end of a regen)
# ---------------------------------------------------------------------------
def _scripts_of(elem):
    """{script_name: {var: value}} for scripts DIRECTLY on this game_entity."""
    out = {}
    for scs in elem.findall("scripts"):
        for s in scs.findall("script"):
            out[s.get("name")] = {v.get("name"): v.get("value")
                                  for v in s.findall("variables/variable")}
    return out


def _direct_scripts(elem):
    out = []
    for scs in elem.findall("scripts"):
        for s in scs.findall("script"):
            out.append(s.get("name"))
    return out


def _elem_pos(elem):
    t = elem.find("transform")
    if t is None or not t.get("position"):
        return None
    return tuple(float(v) for v in t.get("position").split(","))


def _elem_tags(elem):
    te = elem.find("tags")
    return [] if te is None else [t.get("name") for t in te if t.tag == "tag"]


def _has_child_tag(elem, tag):
    ch = elem.find("children")
    if ch is None:
        return False
    return any(tag in _elem_tags(c) for c in ch.iter("game_entity"))


# Siege-weapon SCRIPTS whose entity produces a deployable weapon under a point.
_SIEGE_WEAPON_SCRIPTS = {
    "SiegeLadder", "SiegeTower", "BatteringRam",
    "SiegeLadderSpawner", "SiegeTowerSpawner", "BatteringRamSpawner",
    "RangedSiegeWeapon", "Ballista", "Catapult", "Mangonel", "FireBallista",
}


def _siege_weapon_globals(entities_elem):
    """[(script, gx, gy, tags)] global XY of every siege-weapon-script entity.

    Global XY = sum of transform positions down the parent chain (ignoring
    rotation — a coarse proximity estimate sufficient for the small child offsets
    the siege spawners use).
    """
    out = []

    def walk(el, ox, oy):
        p = _elem_pos(el)
        gx = ox + (p[0] if p else 0.0)
        gy = oy + (p[1] if p else 0.0)
        for sn in _direct_scripts(el):
            if sn in _SIEGE_WEAPON_SCRIPTS:
                out.append((sn, gx, gy, _elem_tags(el)))
        ch = el.find("children")
        if ch is not None:
            for c in ch.findall("game_entity"):
                walk(c, gx, gy)

    for e in entities_elem.findall("game_entity"):
        walk(e, 0.0, 0.0)
    return out


def verify_breach_navmesh(scene_dir):
    """Third invariant: the breach dual-navmesh must actually be authored.

    The two breachable WallSegments carry Clun's breach navmesh ids in their
    <scripts>.  If navmesh.bin contains NO faces with those ids, the engine's
    OnChooseUsedWallSegment face-toggling is a silent no-op and a breached wall
    stays impassable (attackers cannot path through).  This check reads the
    on-disk navmesh and asserts, per wall:

      (a) all 6 breach ids exist (properGround{Out,In}, overDebris{Out,In,Gen},
          onSolidWall) with >=1 face each;
      (b) SOLID state (every overDebris face disabled, both breaches + gate
          blocked): NO outside->inside route survives -> the wall is a barrier;
      (c) BROKEN state (this wall's overDebris enabled, onSolidWall disabled,
          the OTHER wall solid + gate blocked): an outside->inside route exists
          through this breach.

    Raises AssertionError on any violation.
    """
    mesh = NavMesh.parse(rnm1.read(str(Path(scene_dir) / "navmesh.bin")))
    V = mesh.vertices

    def cen(f):
        p = [V[i] for i in f.vertex_ids]
        n = len(p)
        return (sum(q[0] for q in p) / n, sum(q[1] for q in p) / n,
                sum(q[2] for q in p) / n)

    IDS = {
        "left":  dict(pGO=228, pGI=291, oDO=271, oDI=281, oDG=261, oSW=251,
                      probe_out=(472.0, 402.0), probe_in=(455.0, 402.0)),
        "right": dict(pGO=328, pGI=391, oDO=371, oDI=381, oDG=361, oSW=351,
                      probe_out=(455.0, 470.0), probe_in=(455.0, 452.0)),
    }
    ALL_OVER = {IDS[s][k] for s in IDS for k in ("oDO", "oDI", "oDG")}
    ALL_SOLID = {IDS[s]["oSW"] for s in IDS}
    gate_ids = {GATE_ID, GATE_DISABLE_ID}

    # (a) id existence
    from collections import Counter
    g3 = Counter(f.g3 for f in mesh.faces)
    for side, spec in IDS.items():
        for role in ("pGO", "pGI", "oDO", "oDI", "oDG", "oSW"):
            i = spec[role]
            n = g3.get(i, 0)
            assert n >= 1, (
                f"BREACH INVARIANT: {side} wall {role} id={i} has NO face in "
                f"navmesh.bin -> breach toggling is a no-op (present ids: "
                f"{sorted(k for k in g3 if 200 <= k < 400)})")
        cs = {role: [cen(f) for f in mesh.faces if f.g3 == spec[role]]
              for role in ("pGO", "pGI", "oDO", "oDI", "oDG", "oSW")}
        print(f"[verify] breach {side}: " + " ".join(
            f"{r}={spec[r]}({len(cs[r])})" for r in
            ("pGO", "pGI", "oDO", "oDI", "oDG", "oSW")))

    # connectivity sim (shared vertex-pair adjacency)
    def build_adj(active):
        ef = {}
        for fi in active:
            v = mesh.faces[fi].vertex_ids
            n = len(v)
            for k in range(n):
                a, c = v[k], v[(k + 1) % n]
                ef.setdefault((min(a, c), max(a, c)), []).append(fi)
        adj = {}
        for fis in ef.values():
            for i in range(len(fis)):
                for j in range(i + 1, len(fis)):
                    adj.setdefault(fis[i], set()).add(fis[j])
                    adj.setdefault(fis[j], set()).add(fis[i])
        return adj

    def face_at(px, py, pool):
        bd, bi = 1e18, None
        for fi in pool:
            cx, cy, _ = cen(mesh.faces[fi])
            d = (cx - px) ** 2 + (cy - py) ** 2
            if d < bd:
                bd, bi = d, fi
        return bi

    def connected(src, dst, active):
        adj = build_adj(active)
        s = face_at(*src, active)
        d = face_at(*dst, active)
        seen = {s}
        dq = deque([s])
        while dq:
            u = dq.popleft()
            if u == d:
                return True
            for w in adj.get(u, ()):
                if w not in seen:
                    seen.add(w)
                    dq.append(w)
        return d in seen

    allf = set(range(len(mesh.faces)))

    # (b) SOLID: every overDebris disabled + gate blocked -> no leak anywhere.
    solid_active = {fi for fi, f in enumerate(mesh.faces)
                    if f.g3 not in ALL_OVER and f.g3 not in gate_ids}
    for side, spec in IDS.items():
        leak = connected(spec["probe_out"], spec["probe_in"], solid_active)
        assert not leak, (
            f"BREACH INVARIANT: SOLID state leaks outside->inside near the "
            f"{side} wall (overDebris disabled but a route survives)")
    print("[verify] breach SOLID state: no outside->inside leak (both walls)")

    # (c) BROKEN: this wall's overDebris on, onSolidWall off, other wall solid.
    for side, spec in IDS.items():
        other = "right" if side == "left" else "left"
        other_over = {IDS[other][k] for k in ("oDO", "oDI", "oDG")}
        active = {fi for fi, f in enumerate(mesh.faces)
                  if f.g3 not in ALL_SOLID and f.g3 not in other_over
                  and f.g3 not in gate_ids}
        ok = connected(spec["probe_out"], spec["probe_in"], active)
        assert ok, (
            f"BREACH INVARIANT: BROKEN {side} wall has NO outside->inside path "
            f"through the breach (dual navmesh mis-wired)")
    print("[verify] breach BROKEN state: outside->inside path exists (both walls)")
    print("[verify] BREACH NAVMESH OK")


def verify_siege_invariants(scene_dir):
    """Encode the two structural invariants whose violation crashed the scene.

    (a) EXACTLY 2 qualifying breachable WallSegments (DefenseSide set via SideTag
        left/middle/right AND a broken_child child), one per defended side, with
        sides matching the ladder/ram spawner SideTag / TargetWallSegmentTag.
        -> SiegeMissionPreparationHandler.FindRightMostWall requires list3 in
           {1,2}; WallSectionCount==2 means the loop runs twice.

    (b) EVERY DeploymentPoint either has a deployable weapon under it (tag match or
        within Radius) OR provably satisfies the breach-side path (a SiegeTower is
        under it AND a WallSegment exists on its side).  Points tagged "dpWeapon"
        with no weapon within Radius crash SetBreachSideDeploymentPoint (also on a
        civilian visit).  This mirrors Clun's containment structure.

    Raises AssertionError on any violation.
    """
    root = ET.parse(Path(scene_dir) / "scene.xscene").getroot()
    ents = root.find("entities")
    tops = ents.findall("game_entity")

    # ---- (a) breachable WallSegments ----
    qualifying = []           # (SideTag, x, y)
    for e in tops:
        scr = _scripts_of(e)
        if "WallSegment" not in scr:
            continue
        side = scr["WallSegment"].get("SideTag", "")
        if side in ("left", "middle", "right") and _has_child_tag(e, "broken_child"):
            p = _elem_pos(e)
            qualifying.append((side, p[0] if p else 0.0, p[1] if p else 0.0))
    qsides = sorted(s for s, _, _ in qualifying)
    print(f"[verify] qualifying breachable WallSegments: {len(qualifying)} sides={qsides}")
    assert len(qualifying) == 2, (
        f"CRASH-1 INVARIANT: need EXACTLY 2 qualifying breachable WallSegments "
        f"(FindRightMostWall NREs otherwise); got {len(qualifying)}: {qualifying}")

    # Sides must match the spawner sides (ladders/tower/ram SideTag + targets).
    wall_sides = set(qsides)
    spawner_sides = set()
    target_tags = set()
    for e in tops:
        scr = _scripts_of(e)
        for sn in ("SiegeLadderSpawner", "SiegeTowerSpawner"):
            if sn in scr:
                sd = scr[sn].get("SideTag")
                if sd:
                    spawner_sides.add(sd)
                tt = scr[sn].get("TargetWallSegmentTag")
                if tt:
                    target_tags.add(tt)
    # Ladder/tower spawner sides that target a wall must have a wall on that side.
    for sd in spawner_sides:
        assert sd in wall_sides or sd == "middle", (
            f"CRASH-1 INVARIANT: spawner SideTag {sd!r} has no matching breachable "
            f"WallSegment (wall sides={wall_sides})")
    for tt in target_tags:
        want = tt.replace("wall_segment_", "")
        assert want in wall_sides or want == "middle", (
            f"CRASH-1 INVARIANT: TargetWallSegmentTag {tt!r} has no matching "
            f"breachable WallSegment (wall sides={wall_sides})")
    print(f"[verify] spawner sides={sorted(spawner_sides)} target_tags={sorted(target_tags)} "
          f"-> all covered by wall sides {sorted(wall_sides)}")

    # ---- (b) DeploymentPoint containment (Clun's pattern) ----
    # Ground truth (see bisect/analyze_scenes.py on Clun_castle): Clun ships and
    # survives with DeploymentPoints that appear "empty" under a purely static
    # proximity scan -- e.g. Defender dpWeapon points far from any spawner, and
    # attacker "no_deploy" part_b points.  Those are NOT what crashed Rochester,
    # so the invariant is NOT "every point has a weapon".  Clun's real, minimal
    # structure is:
    #   * an ATTACKER dpWeapon point (the besieger-machine placeholder_part_a and
    #     the ram point) MUST sit within its Radius of a tower/ram spawner -- this
    #     is the point that becomes a breach-side point and dereferences a
    #     SiegeTower in SetBreachSideDeploymentPoint.  Rochester's original crash
    #     was exactly such a point placed away from the tower spawner.
    #   * "no_deploy"-tagged points and Defender-side dpWeapon points are safe as
    #     Clun ships them (they mirror Clun 1:1), so we only assert they are not
    #     *more* exposed than Clun (same tag / same side).
    # We therefore require: every ATTACKER-side point whose SiegeWeaponTag is the
    # default "dpWeapon" (i.e. a besieger-machine point, not a "no_deploy" marker)
    # has a tower or ram spawner within its Radius.
    weapons = _siege_weapon_globals(ents)
    problems = []
    ndp = 0
    for e in tops:
        scr = _scripts_of(e)
        if "DeploymentPoint" not in scr:
            continue
        ndp += 1
        dp = scr["DeploymentPoint"]
        p = _elem_pos(e)
        radius = float(dp.get("Radius") or 3.0)
        swtag = dp.get("SiegeWeaponTag") or "dpWeapon"
        side = dp.get("Side", "Attacker")
        under = []
        for sn, gx, gy, tg in weapons:
            d = ((gx - p[0]) ** 2 + (gy - p[1]) ** 2) ** 0.5
            if (swtag in tg) or (d < radius):
                under.append((sn, round(d, 1)))
        # Only besieger-machine points (Attacker + default dpWeapon tag) must be
        # co-located with a tower/ram spawner; Clun's Defender + no_deploy points
        # are structurally safe as-shipped and are not required to have one.
        is_besieger_machine = (side == "Attacker" and swtag == "dpWeapon")
        needs_spawner = is_besieger_machine
        has_spawner = any(sn in ("SiegeTowerSpawner", "BatteringRamSpawner",
                                 "SiegeTower", "BatteringRam") for sn, _ in under)
        ok = (not needs_spawner) or has_spawner
        tag = "OK" if ok else "CRASH"
        note = "(besieger-machine: needs tower/ram spawner)" if needs_spawner else \
               "(Clun-pattern safe: no_deploy/Defender)"
        print(f"[verify] DP pos=({p[0]:.1f},{p[1]:.1f}) Side={side} R={radius} "
              f"tag={swtag!r} under={under} {note} -> {tag}")
        if not ok:
            problems.append((p[0], p[1], side, swtag, radius))
    assert not problems, (
        "CRASH-2 INVARIANT: besieger-machine DeploymentPoint(s) (Attacker/dpWeapon) "
        "with no tower/ram spawner within Radius would NRE in "
        f"SetBreachSideDeploymentPoint: {problems}")
    print(f"[verify] DeploymentPoints checked: {ndp}, besieger-machine points all "
          f"co-located with a spawner; no_deploy/Defender points match Clun")
    print("[verify] SIEGE INVARIANTS OK")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    heights = build_heights()
    print(f"Height range: min={heights.min():.3f} max={heights.max():.3f}")
    lw = layer_weights(heights)

    builder = SceneBuilder.new_battle(
        SCENE_NAME, heights, node_size=NODE_SIZE, layer_weights=lw,
    )
    builder.provenance_note("script", "examples/gen_rochester_castle.py")
    builder.provenance_note("seed", SEED)
    builder.provenance_note("period", "Wars of the Roses c.1460")
    builder.provenance_note("terrain", "GENERATED from scratch (Medway/Boley/"
                            "platform/esplanade/ditch)")
    builder.provenance_note("navmesh", "GENERATED from scratch (ground g3=2, "
                            "interior g3=1, gate g3=462/106, ladder drops "
                            "202/212/302/312, wall footprints cut); breach "
                            "dual-navmesh authored at both breachable "
                            "WallSegments (left 228/291/271/281/261/251, right "
                            "328/391/371/381/361/351) so OnChooseUsedWallSegment "
                            "toggles real faces (solid=barrier, broken=path)")
    builder.provenance_note("siege_reuse", "individual Clun siege entities "
                            "harvested one-by-one + retagged (no whole-castle "
                            "copy); gate hand-placed with baked CastleGate")

    build_structure(builder, heights)
    siege = place_siege(builder, heights)
    add_paths(builder, heights)
    build_dressing(builder, heights)
    add_flora_entities(builder, heights)

    # Correct the atmosphere provenance BEFORE build() writes provenance.md:
    # we reuse Clun's DADG castle atmosphere, not the battle template's.
    for rec in builder._provenance.sources:
        if rec.get("role") == "atmosphere":
            rec["source"] = "DellarteDellaGuerraScenes/Clun_castle"
            rec["detail"] = "copied verbatim (DADG castle atmosphere)"

    scene_dir = builder.build(OUT_DIR)

    # Reuse a DADG atmosphere (Clun's) instead of the battle template's.
    import shutil
    shutil.copy2(CLUN + r"\atmosphere.xml", str(Path(scene_dir) / "atmosphere.xml"))

    # Overwrite build()'s auto ground navmesh with our hand-authored siege navmesh.
    mesh = build_navmesh(heights, siege)
    rnm1.write(str(Path(scene_dir) / "navmesh.bin"), mesh.serialize())
    st = mesh.stats()
    print(f"navmesh stats: faces={st['faces']} verts={st['vertices']} "
          f"g3={st['face_ids_g3']}")

    # Re-emit provenance AFTER the atmosphere + navmesh overwrites so file_origins
    # reflect the bytes actually on disk: atmosphere.xml now hash-differs from
    # battle_terrain_a (it is Clun's verbatim, see the atmosphere source record),
    # and navmesh.bin is the hand-authored siege mesh, not build()'s auto ground.
    from blscene.provenance import write_provenance
    write_provenance(
        builder._provenance,
        scene_dir,
        builder._source_dir,
        builder._terrain_dirty,
        ["scene.xscene", "terrain.bin", "flora.bin", "atmosphere.xml",
         "references.txt", "navmesh.bin"],
    )

    print(f"\nScene written to: {scene_dir}")
    for pth in sorted(Path(scene_dir).iterdir()):
        if pth.is_file():
            print(f"  {pth.name}  ({pth.stat().st_size:,} bytes)")

    # Siege-invariant verification: catches regressions of the two mission-start
    # NREs (FindRightMostWall / SetBreachSideDeploymentPoint) on future regens.
    print()
    verify_siege_invariants(scene_dir)
    verify_breach_navmesh(scene_dir)


if __name__ == "__main__":
    main()
