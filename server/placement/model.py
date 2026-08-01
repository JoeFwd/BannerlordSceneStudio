"""Pure placement domain — no I/O, no Bannerlord, no HTTP.

Settlement footprint radius is a per-type nominal constant grounded in a
one-time analysis of the DADG world-map prefabs. Every settlement icon carries
a ``town_circle_decal`` (material ``decal_city_circle_a``) sitting on unscaled
parent entities, so the decal's transform scale is the footprint radius in world
units. Across the whole Main_map scene those scales collapse onto exactly two
values — town 8.475, castle 3.572 — with villages carrying no circle at all.

Villages therefore have *no* navmesh settlement zone. The per-type defaults are
configurable per map (see ``config``) and any single settlement may override its
radius with a custom value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

TOWN, CASTLE, VILLAGE = "town", "castle", "village"

# TaleWorlds.Core.TerrainType ids (navmesh face g3) that are water on the
# campaign map: a settlement zone sitting over these is *not* on land. This is
# what makes rivers and lakes count as water, not just the sea level.
#   8 Lake · 10 Water · 11 River · 18 CoastalSea · 19 OpenSea
#   22 NonNavigableRiver · 24 SeaRestriction
WATER_TERRAIN_TYPES: frozenset[int] = frozenset({8, 10, 11, 18, 19, 22, 24})

# Grounded in DADG prefab decal scales (decal_city_circle_a on unscaled parents).
# None => the type has no navmesh settlement zone (villages).
DEFAULT_TYPE_RADIUS: dict[str, float | None] = {
    TOWN: 8.475,
    CASTLE: 3.572,
    VILLAGE: None,
}


@dataclass
class Footprint:
    """Resolves a settlement's footprint radius (world units, or None = no zone).

    ``type_radius`` holds the per-map defaults; ``custom_radius`` holds
    per-settlement overrides keyed by settlement id.
    """

    type_radius: dict[str, float | None] = field(
        default_factory=lambda: dict(DEFAULT_TYPE_RADIUS)
    )
    custom_radius: dict[str, float] = field(default_factory=dict)

    def radius_for(self, settlement_id: str, settlement_type: str | None) -> float | None:
        if settlement_id in self.custom_radius:
            return self.custom_radius[settlement_id]
        return self.type_radius.get(settlement_type)


def is_on_land(height: float, water_level: float) -> bool:
    """A position is on land when its sampled terrain height clears the water."""
    return height > water_level


def disc_samples(x: float, y: float, radius: float | None,
                 rings: int = 2, spokes: int = 12) -> list[tuple[float, float]]:
    """Points covering a settlement footprint disc: centre + concentric rings.

    A None/0 radius (villages) yields just the centre point, so the zone rule
    degrades to a plain point test for zoneless settlements.
    """
    pts = [(x, y)]
    if not radius:
        return pts
    for ri in range(1, rings + 1):
        rr = radius * ri / rings
        for s in range(spokes):
            a = 2.0 * math.pi * s / spokes
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    return pts


def _point_in_tri(px, py, ax, ay, bx, by, cx, cy) -> bool:
    d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if d == 0.0:
        return False
    u = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
    v = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
    return u >= -1e-6 and v >= -1e-6 and (u + v) <= 1.0 + 1e-6


class LandOracle:
    """Locates the navmesh water faces (rivers, lakes, sea) via a grid index.

    Only water-typed faces are indexed; ``over_water_face`` reports whether a
    point sits on one. Dry terrain that carries no navmesh yet is therefore
    *not* reported as water — the caller decides land vs water by combining this
    with the sea-level height test. Faces are fan-triangulated and each triangle
    is bucketed by the grid cells its bounding box spans. Built from plain (x, y)
    vertex coords and (vertex_ids, g3) faces — no mesh/engine dependency.
    """

    def __init__(self, vertices, faces, cell: float = 32.0):
        self.cell = cell
        self.tris: list[tuple] = []
        self.grid: dict[tuple[int, int], list[int]] = {}
        for vids, g3 in faces:
            if g3 not in WATER_TERRAIN_TYPES or len(vids) < 3:
                continue
            a = vertices[vids[0]]
            for k in range(1, len(vids) - 1):
                b = vertices[vids[k]]
                c = vertices[vids[k + 1]]
                ti = len(self.tris)
                self.tris.append((a[0], a[1], b[0], b[1], c[0], c[1]))
                minx = min(a[0], b[0], c[0]); maxx = max(a[0], b[0], c[0])
                miny = min(a[1], b[1], c[1]); maxy = max(a[1], b[1], c[1])
                for ix in range(int(minx // cell), int(maxx // cell) + 1):
                    for iy in range(int(miny // cell), int(maxy // cell) + 1):
                        self.grid.setdefault((ix, iy), []).append(ti)

    def over_water_face(self, x: float, y: float) -> bool:
        bucket = self.grid.get((int(x // self.cell), int(y // self.cell)))
        if not bucket:
            return False
        for ti in bucket:
            ax, ay, bx, by, cx, cy = self.tris[ti]
            if _point_in_tri(x, y, ax, ay, bx, by, cx, cy):
                return True
        return False
