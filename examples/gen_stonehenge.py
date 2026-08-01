"""Generate the dadg_gen_stonehenge battle scene.

A Salisbury-Plain-style open grassland battle map (same size/template as
dadg_gen_battle_test but FLATTER) with a Stonehenge stone circle at map center.

Terrain (769x769 float32, 6x6 nodes @ 200 m = 1200x1200 m world):
  * base 50 m, gentle low-amplitude rolling undulation (a few metres)
  * a subtle circular earthwork bank+ditch ring around the monument
    (~110 m diameter, bank ~+1 m, ditch ~-1.5 m, NE entrance gap)
  * same slope-based grass / base_rock layer split as gen_battle_test
    (on this flat ground it reads as almost all grass — correct)

Monument (approximate real Stonehenge, scaled to read in-game), map center (600,600):
  * outer sarsen circle: ~33 m diameter, 30 slots, ~17 standing + a few
    leaning + a few fallen/half-buried, with gaps (ruined, period-accurate)
  * inner trilithon horseshoe: 5 pairs of taller uprights, opening to the NE;
    3 with a horizontal lintel across the top, others ruined/fallen

Rocks are harvested native props (no menhir prefab exists) re-scaled
non-uniformly into rough sarsen slabs via each entity's own <transform> scale.

Output: DellarteDellaGuerraScenes/SceneObj/dadg_gen_stonehenge/
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.compose import SceneBuilder, _sample_height
from blscene.harvest import harvest_entities, place_entities

GAME = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"
DART = GAME + r"\DellarteDellaGuerraScenes\SceneObj\Dartmouth_castle"
STURG = GAME + r"\SandBoxCore\SceneObj\sturgia_village_h"
OUT_DIR = GAME + r"\DellarteDellaGuerraScenes\SceneObj"

# --- Map / world constants (mirror gen_battle_test) ---
N = 769                       # samples per axis
NODE_SIZE = 200.0
NODES = 6
WORLD = NODES * NODE_SIZE     # 1200 m
CX = CY = WORLD / 2.0         # monument center (600, 600)
BASE_H = 50.0

# Earthwork ring geometry (metres, radius from centre)
RING_MID = 52.0               # centre of bank/ditch band
DITCH_R = 49.0                # ditch (inner) radius
BANK_R = 55.0                 # bank (outer) radius
RING_W = 5.0                  # gaussian width of each feature
BANK_H = 1.0                  # bank height above base
DITCH_D = 1.5                 # ditch depth below base
ENTRANCE_DEG = 45.0           # NE entrance bearing (0=+X/E, 90=+Y/N)
ENTRANCE_HALF = 16.0          # +/- degrees of gap where ring flattens


# ---------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------
def build_heights() -> np.ndarray:
    xx, yy = np.meshgrid(
        np.arange(N, dtype=np.float32), np.arange(N, dtype=np.float32)
    )
    # Gentle rolling undulation: ~+/-2 m over the map (flatter than battle_test's 10 m).
    heights = (
        BASE_H
        + 2.0 * np.sin(xx / 70.0) * np.cos(yy / 90.0)
        + 1.0 * np.sin(xx / 33.0 + 1.3) * np.cos(yy / 41.0 - 0.7)
    ).astype(np.float32)

    # --- Circular earthwork bank + ditch ring around the monument ---
    # World coords per sample.
    wx = xx / (N - 1) * WORLD
    wy = yy / (N - 1) * WORLD
    dx = wx - CX
    dy = wy - CY
    r = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dy, dx)) % 360.0   # 0=E, 90=N

    # NE entrance: taper the ring to 0 within +/- ENTRANCE_HALF of the bearing.
    dang = np.abs((ang - ENTRANCE_DEG + 180.0) % 360.0 - 180.0)
    gate = np.clip(dang / ENTRANCE_HALF, 0.0, 1.0)  # 0 in gap, 1 far from gap
    gate = gate * gate * (3 - 2 * gate)             # smoothstep

    bank = BANK_H * np.exp(-((r - BANK_R) ** 2) / (2 * RING_W ** 2))
    ditch = DITCH_D * np.exp(-((r - DITCH_R) ** 2) / (2 * RING_W ** 2))
    ring = (bank - ditch) * gate
    heights = heights + ring.astype(np.float32)

    # Flatten the very centre so the monument sits on level ground.
    flat = np.exp(-(r ** 2) / (2 * 30.0 ** 2))
    heights = heights * (1 - 0.6 * flat) + (BASE_H) * (0.6 * flat)
    return heights.astype(np.float32)


def slope_layer_weights(heights: np.ndarray) -> dict[int, np.ndarray]:
    """Same slope-based grass/base_rock split as gen_battle_test."""
    LAYER_ROCK = 1
    sample_spacing = NODE_SIZE * NODES / (N - 1)
    gy, gx = np.gradient(heights)
    slope = np.hypot(gx, gy) / sample_spacing
    rock_thresh = 0.10
    rock_w = (slope > rock_thresh).astype(np.float32)
    print(f"slope max={slope.max():.4f}  rock coverage={rock_w.mean()*100:.2f}% of cells")
    return {LAYER_ROCK: rock_w}


# ---------------------------------------------------------------------------
# Stone placement
# ---------------------------------------------------------------------------
def _wsize():
    return WORLD, WORLD


def set_stone(elem, x, y, heights, *, scale, yaw, pitch=0.0, roll=0.0, bury=0.5):
    """Rewrite a placed entity's <transform> into an upright/leaning/fallen sarsen.

    scale = (sx, sy, sz) non-uniform (tall+narrow = upright slab).
    yaw/pitch/roll in radians (rotation_euler = rx=pitch, ry=roll, rz=yaw).
    bury: metres the base is sunk below terrain so nothing floats.
    Z is set to terrain height at (x,y) minus bury.
    """
    t = elem.find("transform")
    wsx, wsy = _wsize()
    th = _sample_height(heights, wsx, wsy, x, y)
    z = (th if th is not None else BASE_H) - bury
    t.set("position", "%.3f, %.3f, %.3f" % (x, y, z))
    t.set("rotation_euler", "%.3f, %.3f, %.3f" % (pitch, roll, yaw))
    t.set("scale", "%.3f, %.3f, %.3f" % scale)


def place_one(builder, cluster, heights, x, y, **kw):
    """Insert one harvested prop at (x,y) and rewrite its transform to a sarsen."""
    inserted = place_entities(builder, cluster, x=x, y=y, snap_z=False)
    # place_entities inserts every element of the cluster; we harvested a
    # single-instance cluster, so exactly one element comes back.
    elem = inserted[0]
    set_stone(elem, x, y, heights, **kw)
    return elem


def build_monument(builder, heights, big_c, big_a, cliff_c):
    """Place the outer sarsen circle and inner trilithon horseshoe."""
    rng = np.random.default_rng(42)

    # --- Outer sarsen circle: 30 slots, ~33 m diameter (r = 16.5) ---
    OUTER_R = 16.5
    N_SLOTS = 30
    # Slots to leave empty (gaps) and slots that are leaning / fallen.
    # NE quadrant kept sparser (entrance side, more ruin).
    empty = {2, 3, 9, 16, 22, 27, 28}            # 7 gaps -> 23 slots occupied
    leaning = {5, 11, 19, 24}                     # slight tilt
    fallen = {7, 13, 25}                          # toppled, half-buried
    # -> 23 - 3 fallen = 20 upright-ish; of those 4 lean, ~16 truly upright.
    standing_ct = leaning_ct = fallen_ct = 0
    for i in range(N_SLOTS):
        if i in empty:
            continue
        ang = math.radians(i / N_SLOTS * 360.0)
        x = CX + OUTER_R * math.cos(ang)
        y = CY + OUTER_R * math.sin(ang)
        # Face the slab tangentially (broad face pointing inward/outward).
        yaw = ang + math.pi / 2 + float(rng.uniform(-0.18, 0.18))
        jitter = lambda a: float(rng.uniform(-a, a))
        if i in fallen:
            # Toppled slab lying on the ground, mostly buried.
            place_one(
                builder, big_a, heights, x, y,
                scale=(0.95 + jitter(0.1), 0.55, 0.30),
                yaw=yaw, pitch=math.radians(82) + jitter(0.15),
                roll=jitter(0.2), bury=0.35,
            )
            fallen_ct += 1
        elif i in leaning:
            place_one(
                builder, big_c, heights, x, y,
                scale=(0.55 + jitter(0.05), 0.32, 1.10 + jitter(0.1)),
                yaw=yaw, pitch=math.radians(18) + jitter(0.08),
                roll=jitter(0.06), bury=0.6,
            )
            leaning_ct += 1
        else:
            place_one(
                builder, big_c, heights, x, y,
                scale=(0.55 + jitter(0.06), 0.30 + jitter(0.03), 1.15 + jitter(0.12)),
                yaw=yaw, pitch=jitter(0.04), roll=jitter(0.04), bury=0.6,
            )
            standing_ct += 1

    # --- Inner trilithon horseshoe: 5 pairs, opening to the NE ---
    # Horseshoe is a ~200 deg arc centred opposite the NE entrance (i.e. SW),
    # so the open mouth faces NE (45 deg).  Pairs sit along that arc; each pair
    # is two tall uprights a couple of metres apart, some capped by a lintel.
    HORSE_R = 7.5           # radius of the pair centres
    PAIR_GAP = 2.6          # spacing between the two uprights of a pair
    UP_SCALE = (0.70, 0.42, 1.75)   # tall trilithon upright (~6-7 m)
    open_dir = math.radians(ENTRANCE_DEG)              # NE = mouth
    closed_dir = open_dir + math.pi                    # SW = back of horseshoe
    # 5 pairs spread over a 200 deg arc centred on closed_dir.
    arc = math.radians(200.0)
    lintel_pairs = {0, 2, 4}      # which pairs get a lintel (3 of 5)
    fallen_pairs = {3}            # one pair ruined (one upright fallen, no lintel)
    for p in range(5):
        frac = (p / 4.0) - 0.5    # -0.5 .. 0.5
        centre_ang = closed_dir + frac * arc
        px = CX + HORSE_R * math.cos(centre_ang)
        py = CY + HORSE_R * math.sin(centre_ang)
        # Tangent direction (uprights sit either side across the tangent).
        tang = centre_ang + math.pi / 2
        ox = math.cos(tang) * PAIR_GAP / 2
        oy = math.sin(tang) * PAIR_GAP / 2
        # Broad faces of the uprights face radially (yaw along tangent).
        yaw = tang
        a_x, a_y = px - ox, py - oy
        b_x, b_y = px + ox, py + oy

        if p in fallen_pairs:
            # One upright standing, the partner toppled inward; no lintel.
            place_one(builder, cliff_c, heights, a_x, a_y,
                      scale=UP_SCALE, yaw=yaw, pitch=math.radians(12),
                      roll=0.0, bury=0.7)
            place_one(builder, big_c, heights, b_x, b_y,
                      scale=(0.9, 0.5, 0.32), yaw=yaw,
                      pitch=math.radians(85), roll=0.1, bury=0.4)
            continue

        # Two tall uprights.
        place_one(builder, cliff_c, heights, a_x, a_y,
                  scale=UP_SCALE, yaw=yaw, bury=0.7)
        place_one(builder, cliff_c, heights, b_x, b_y,
                  scale=UP_SCALE, yaw=yaw, bury=0.7)

        if p in lintel_pairs:
            # Horizontal lintel bridging the two uprights, resting on top.
            # Sits at the midpoint, long axis along the pair (X of the slab),
            # flattened in Z, raised to the top of the uprights.
            th = _sample_height(heights, WORLD, WORLD, px, py) or BASE_H
            top_z = th - 0.7 + 6.3       # approx top of ~6.5 m uprights
            elem = place_entities(builder, big_c, x=px, y=py, snap_z=False)[0]
            t = elem.find("transform")
            t.set("position", "%.3f, %.3f, %.3f" % (px, py, top_z))
            # Long axis spans the gap (~PAIR_GAP+2*half-width), thin, flat.
            t.set("scale", "%.3f, %.3f, %.3f" % (1.05, 0.42, 0.30))
            # Long axis of the slab should point along the pair (tangent).
            t.set("rotation_euler", "%.3f, %.3f, %.3f" % (0.0, 0.0, tang))

    print(f"outer circle: standing={standing_ct} leaning={leaning_ct} "
          f"fallen={fallen_ct} (gaps={len(empty)})")
    print(f"inner horseshoe: 5 pairs, lintels={sorted(lintel_pairs)}, "
          f"fallen_pair={sorted(fallen_pairs)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    heights = build_heights()
    print(f"Height range: min={heights.min():.3f} max={heights.max():.3f}")
    lw = slope_layer_weights(heights)

    builder = SceneBuilder.new_battle(
        "dadg_gen_stonehenge", heights, node_size=NODE_SIZE, layer_weights=lw
    )

    # Harvest single clean instances of each sarsen-candidate prop.
    big_c = harvest_entities(DART, 255.0, 395.0, 285.0, 425.0,
                             prefab_re="^terrain_green_rock_big_c$")
    big_a = harvest_entities(DART, 240.0, 415.0, 260.0, 450.0,
                             prefab_re="^terrain_green_rock_big_a$")
    cliff_c = harvest_entities(STURG, 615.0, 840.0, 635.0, 860.0,
                               prefab_re="^rock_cliff_c$")
    # Keep exactly one instance of each so place_one inserts a single prop.
    for c in (big_c, big_a, cliff_c):
        del c.elements[1:]; del c.offsets[1:]; del c.clearances[1:]
    print(f"harvested props: big_c={len(big_c)} big_a={len(big_a)} cliff_c={len(cliff_c)}")

    build_monument(builder, heights, big_c, big_a, cliff_c)

    scene_dir = builder.build(OUT_DIR)
    print(f"\nScene written to: {scene_dir}")
    for pth in sorted(Path(scene_dir).iterdir()):
        if pth.is_file():
            print(f"  {pth.name}  ({pth.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
