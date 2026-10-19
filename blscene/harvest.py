"""Harvest / composite pipeline: transplant terrain, entities, and flora from
native Bannerlord scenes into generated scenes.

This module extracts three kinds of content from an existing SceneObj folder and
places them into a target scene being built with :class:`blscene.compose.SceneBuilder`:

  1. **Terrain patches** — a world-space rectangle of the source heightmap, stamped
     into a target heights array with a smooth blend border so it does not create
     cliffs.  Default stamping is *relative*: the patch is vertically shifted so its
     border mean matches the surrounding target terrain.

  2. **Entity clusters** — the full XML subtree of every top-level ``<game_entity>``
     whose position lies in the rectangle (children/transforms/paths preserved
     verbatim).  Positions are stored relative to a cluster anchor so the cluster can
     be re-placed (and rotated) anywhere on the target terrain.

  3. **Flora records** — FLR2 records inside the rectangle, again stored relative to
     the anchor, with per-record ground clearance from the source terrain.

Coordinate conventions (verified against native data + blscene.compose):
  * World meters.  X/Y are the ground plane, Z is up.
  * Heights arrays are indexed ``heights[row, col] = heights[Y, X]``; row 0 is Y=0
    (south edge).  ``world_size_x = nx * node_size``; grid has ``nx*128 + 1`` samples
    across X.  Sample spacing = ``node_size / 128`` meters.
  * Entity ``<transform>`` for a top-level entity carries the world position:
    ``<transform position="x, y, z" rotation_euler="rx, ry, rz" scale="..."/>``.
    Child entity transforms are relative to their parent, so only the top-level
    position is re-anchored; children ride along unchanged.
  * Flora records store a world XYZ position and a 3x4 row-major rot/scale matrix.
    The top-left 2x2 block (matrix indices 0,1,4,5) is the XY rotation/scale; index
    10 is the Z scale; indices 3,7,11 are a runtime column (0.0 here, preserved).
    Rotating flora about Z means rotating both the position offset and that 2x2 block.

The anchor is the *rectangle center at source terrain height*.  Harvested offsets are
measured from the anchor; placement translates them to a new anchor and (optionally)
rotates about Z.  Z is then re-snapped to the target terrain, re-applying each item's
harvested ground clearance so buried rocks stay buried and surface flora stays on the
surface.
"""
from __future__ import annotations

import copy
import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np

from blnav.flora import Flora, FloraRecord
from blnav.terrain import Terrain
from blscene.compose import _sample_height
from blscene.xscene import Scene


# ---------------------------------------------------------------------------
# Source terrain loading
# ---------------------------------------------------------------------------

def _load_source_terrain(scene_dir: str) -> tuple[np.ndarray, float, float, float]:
    """Load a source scene's terrain as a world-metre height grid.

    Reads terrain.bin for the raw uint16 heightmap and the xscene <terrain>
    element for node dimensions, node_size, and the min/max height used to
    decode uint16 -> meters (``h = min + u16/65535 * (max - min)``).

    Returns ``(heights_m, world_size_x, world_size_y, node_size)`` where
    heights_m is float32 [row=Y, col=X] in world meters.
    """
    xscene_path = os.path.join(scene_dir, "scene.xscene")
    root = ET.parse(xscene_path).getroot()
    terr = root.find("terrain")
    if terr is None:
        raise ValueError(f"{scene_dir}: xscene has no <terrain> element")
    nx = int(terr.get("node_dimension_x"))
    ny = int(terr.get("node_dimension_y"))
    node_size = float(terr.get("node_size"))
    min_h = float(terr.get("min_height"))
    max_h = float(terr.get("max_height"))

    terrain = Terrain.load(os.path.join(scene_dir, "terrain.bin"))
    grid_u16 = terrain.heightmap_grid((nx, ny)).astype(np.float32)
    heights_m = (min_h + grid_u16 / 65535.0 * (max_h - min_h)).astype(np.float32)
    world_size_x = nx * node_size
    world_size_y = ny * node_size
    return heights_m, world_size_x, world_size_y, node_size


# ---------------------------------------------------------------------------
# 1. Terrain patch
# ---------------------------------------------------------------------------

@dataclass
class TerrainPatch:
    """A rectangular slice of a source heightmap, resampled onto its own grid.

    Attributes:
        heights: float32 (rows, cols) world-metre heights of the rect, indexed
            [row=Y, col=X] like the main heights arrays.
        spacing: sample spacing in meters (world_size / (samples-1)), equal on
            both axes (source grids are square-celled).
        world_w, world_h: rect extent in meters (x1-x0, y1-y0).
        border_mean: mean height along the four edges (used for relative stamping).
        source: "module/scene" string for provenance reporting.
    """

    heights: np.ndarray
    spacing: float
    world_w: float
    world_h: float
    border_mean: float
    source: str = ""


def _resample_rect(
    heights: np.ndarray,
    world_size_x: float,
    world_size_y: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    spacing: float,
) -> np.ndarray:
    """Bilinearly resample the world-space rect [x0,x1]x[y0,y1] onto a regular grid.

    The output grid has ``round((x1-x0)/spacing)+1`` columns and the analogous row
    count, so the sample spacing is (approximately) *spacing* meters.
    """
    cols = max(2, int(round((x1 - x0) / spacing)) + 1)
    rows = max(2, int(round((y1 - y0) / spacing)) + 1)
    xs = np.linspace(x0, x1, cols)
    ys = np.linspace(y0, y1, rows)
    out = np.empty((rows, cols), dtype=np.float32)
    for r, wy in enumerate(ys):
        for c, wx in enumerate(xs):
            z = _sample_height(heights, world_size_x, world_size_y, wx, wy)
            if z is None:
                # Rect edge exactly on/just past the grid bound: clamp inward.
                z = _sample_height(
                    heights, world_size_x, world_size_y,
                    min(max(wx, 0.0), world_size_x),
                    min(max(wy, 0.0), world_size_y),
                )
            out[r, c] = 0.0 if z is None else z
    return out


def harvest_terrain_patch(
    scene_dir: str, x0: float, y0: float, x1: float, y1: float
) -> TerrainPatch:
    """Extract the height samples of the world-space rect from *scene_dir*.

    The rect is resampled onto a regular grid at the source terrain's native
    sample spacing (node_size / 128 meters).  Returns a :class:`TerrainPatch`.
    """
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"empty rect: ({x0},{y0})-({x1},{y1})")
    heights, wsx, wsy, node_size = _load_source_terrain(scene_dir)
    spacing = node_size / 128.0
    patch = _resample_rect(heights, wsx, wsy, x0, y0, x1, y1, spacing)

    # Border mean = mean of the four edges.
    edge = np.concatenate([
        patch[0, :], patch[-1, :], patch[1:-1, 0], patch[1:-1, -1]
    ])
    source = "/".join(os.path.normpath(scene_dir).split(os.sep)[-3:-1] + [os.path.basename(scene_dir)])
    return TerrainPatch(
        heights=patch,
        spacing=spacing,
        world_w=float(x1 - x0),
        world_h=float(y1 - y0),
        border_mean=float(edge.mean()),
        source=source,
    )


def _blend_falloff(rows: int, cols: int, ramp_cells_x: int, ramp_cells_y: int) -> np.ndarray:
    """Return an (rows, cols) weight mask that is 1 in the interior and ramps to 0
    at the border over *ramp_cells* cells using a smooth cosine (raised-cosine) ramp.
    """
    def ramp_1d(n: int, k: int) -> np.ndarray:
        w = np.ones(n, dtype=np.float32)
        if k <= 0:
            return w
        k = min(k, n // 2)
        # 0.5*(1-cos) over the first/last k cells; index 0 -> 0, index k -> 1.
        t = np.linspace(0.0, 1.0, k + 1)[1:]  # exclude the 0 endpoint (stays 0)
        ramp = 0.5 * (1.0 - np.cos(np.pi * t))
        w[:k] = ramp
        w[-k:] = ramp[::-1]
        w[0] = 0.0
        w[-1] = 0.0
        return w

    wy = ramp_1d(rows, ramp_cells_y)
    wx = ramp_1d(cols, ramp_cells_x)
    return np.outer(wy, wx).astype(np.float32)


def apply_terrain_patch(
    heights: np.ndarray,
    patch: TerrainPatch,
    x: float,
    y: float,
    node_size: float,
    *,
    blend_margin: float = 20.0,
    absolute: bool = False,
) -> np.ndarray:
    """Stamp *patch* into a copy of *heights* at world position (x, y).

    (x, y) is the world position of the patch's lower-left (south-west) corner,
    i.e. the sample at patch[0, 0].  The patch is bilinearly resampled onto the
    target grid spacing (node_size / 128) if the spacings differ, then blended in
    with a smooth cosine falloff over *blend_margin* meters at the border so the
    seam is continuous.

    Vertical offset:
      * ``absolute=False`` (default): the patch is shifted so its border mean
        matches the mean of the target terrain under the border ring — relative
        stamping that keeps the patch continuous with its surroundings.
      * ``absolute=True``: patch heights are used verbatim (world Z).

    Returns a new float32 array (the input is not modified).
    """
    heights = np.asarray(heights, dtype=np.float32)
    H, W = heights.shape
    ny = (H - 1) // 128
    nx = (W - 1) // 128
    world_size_x = nx * node_size
    world_size_y = ny * node_size
    target_spacing = node_size / 128.0

    # World extent covered by the patch.
    x1 = x + patch.world_w
    y1 = y + patch.world_h

    # Resample the patch onto the target grid spacing (its own world grid).
    cols = max(2, int(round(patch.world_w / target_spacing)) + 1)
    rows = max(2, int(round(patch.world_h / target_spacing)) + 1)
    src = patch.heights
    src_rows, src_cols = src.shape
    # Bilinear resample src -> (rows, cols) in patch-local normalized coords.
    ri = np.linspace(0, src_rows - 1, rows)
    ci = np.linspace(0, src_cols - 1, cols)
    r0 = np.floor(ri).astype(int); r1 = np.minimum(r0 + 1, src_rows - 1)
    c0 = np.floor(ci).astype(int); c1 = np.minimum(c0 + 1, src_cols - 1)
    fr = (ri - r0)[:, None]; fc = (ci - c0)[None, :]
    resampled = (
        src[np.ix_(r0, c0)] * (1 - fr) * (1 - fc)
        + src[np.ix_(r0, c1)] * (1 - fr) * fc
        + src[np.ix_(r1, c0)] * fr * (1 - fc)
        + src[np.ix_(r1, c1)] * fr * fc
    ).astype(np.float32)

    # Target index window (nearest grid cells covering [x,x1] x [y,y1]).
    gx0 = int(round(x / world_size_x * (W - 1)))
    gy0 = int(round(y / world_size_y * (H - 1)))
    gx1 = gx0 + cols
    gy1 = gy0 + rows
    if gx0 < 0 or gy0 < 0 or gx1 > W or gy1 > H:
        raise ValueError(
            f"patch at ({x},{y}) size ({patch.world_w},{patch.world_h}) does not "
            f"fit inside target terrain {world_size_x}x{world_size_y}"
        )

    target_window = heights[gy0:gy1, gx0:gx1]

    # Vertical offset for relative stamping.
    if absolute:
        stamp = resampled
    else:
        # Match the patch border mean to the target terrain under the border ring.
        border_target = np.concatenate([
            target_window[0, :], target_window[-1, :],
            target_window[1:-1, 0], target_window[1:-1, -1],
        ])
        border_stamp = np.concatenate([
            resampled[0, :], resampled[-1, :],
            resampled[1:-1, 0], resampled[1:-1, -1],
        ])
        offset = float(border_target.mean() - border_stamp.mean())
        stamp = resampled + offset

    # Blend mask: cosine ramp over blend_margin meters at the border.
    ramp_cells_x = int(round(blend_margin / target_spacing))
    ramp_cells_y = int(round(blend_margin / target_spacing))
    mask = _blend_falloff(rows, cols, ramp_cells_x, ramp_cells_y)

    out = heights.copy()
    out[gy0:gy1, gx0:gx1] = mask * stamp + (1.0 - mask) * target_window
    return out


# ---------------------------------------------------------------------------
# 2. Entity cluster
# ---------------------------------------------------------------------------

# Names/prefabs/tags marking scene infrastructure that should NOT be harvested as
# a visual/prop cluster by default.  Match is by substring on prefab OR name.
_INFRA_SUBSTRINGS = (
    "sp_battle_set",
    "sp_duel_set",
    "sp_npc",
    "sp_sheep",
    "sp_chicken",
    "spawn",
    "flee_line",
    "barrier_path",
    "border_soft",
    "border_1",
    "TacticalPosition",
    "TacticalRegion",
    "strategic_archer",
    "strategic_attacker",
    "prt_border",
    "envmap_prop",
    "ambient_sound",
)
_INFRA_TAGS = frozenset({
    "border_mesh",
    "spawn_point",
})


def _is_infrastructure(prefab: str | None, name: str | None, tags: list[str]) -> bool:
    hay = f"{prefab or ''} {name or ''}"
    for s in _INFRA_SUBSTRINGS:
        if s in hay:
            return True
    if any(tg in _INFRA_TAGS for tg in tags):
        return True
    return False


@dataclass
class EntityCluster:
    """A deep-copied set of entity XML subtrees with anchor-relative offsets.

    Attributes:
        elements: list of deep-copied top-level ``<game_entity>`` Elements.
        offsets: parallel list of (dx, dy) horizontal offsets from the anchor.
        clearances: parallel list of per-entity ground clearance (world Z minus
            source terrain height at the entity's XY) captured at harvest time.
        source: "module/scene" provenance string.
        group_objects: the source scene's editor group declarations
            ({guid: name}), so placement can declare the groups the copied
            ``<edit_mode_data>`` references.
    """

    elements: list[ET.Element] = field(default_factory=list)
    offsets: list[tuple[float, float]] = field(default_factory=list)
    clearances: list[float] = field(default_factory=list)
    source: str = ""
    group_objects: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.elements)


def _entity_tags(elem: ET.Element) -> list[str]:
    tags_elem = elem.find("tags")
    if tags_elem is None:
        return []
    return [tg.get("name", "") for tg in tags_elem if tg.tag == "tag"]


def harvest_entities(
    scene_dir: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    name_re: str | None = None,
    prefab_re: str | None = None,
    tags: list[str] | None = None,
    include_infrastructure: bool = False,
) -> EntityCluster:
    """Harvest top-level entities whose XY position is inside the rect.

    Deep-copies the full ``<game_entity>`` subtree (children, transforms, paths).
    Positions are stored relative to the anchor = rect center at source terrain Z.

    Filters (all AND-combined when supplied):
        name_re:   regex that must search-match the entity ``name`` attribute.
        prefab_re: regex that must search-match the entity ``prefab`` attribute.
        tags:      every listed tag must be present on the entity.

    By default, scene-infrastructure entities (sp_battle_set hierarchy, spawn
    paths, TacticalPosition/Region, border meshes, ...) are skipped; pass
    ``include_infrastructure=True`` to keep them.
    """
    heights, wsx, wsy, _ = _load_source_terrain(scene_dir)
    ax = (x0 + x1) / 2.0
    ay = (y0 + y1) / 2.0

    name_pat = re.compile(name_re) if name_re else None
    prefab_pat = re.compile(prefab_re) if prefab_re else None
    want_tags = set(tags) if tags else None

    scene = Scene.load(os.path.join(scene_dir, "scene.xscene"))
    source = "/".join(os.path.normpath(scene_dir).split(os.sep)[-3:-1] + [os.path.basename(scene_dir)])
    cluster = EntityCluster(source=source, group_objects=scene.group_objects)

    for ent in scene.entities:
        pos = ent.position
        if pos is None:
            continue
        wx, wy, wz = pos
        if not (x0 <= wx <= x1 and y0 <= wy <= y1):
            continue

        prefab = ent.prefab
        name = ent.name
        etags = ent.tag_names

        if not include_infrastructure and _is_infrastructure(prefab, name, etags):
            continue
        if name_pat is not None and not name_pat.search(name or ""):
            continue
        if prefab_pat is not None and not prefab_pat.search(prefab or ""):
            continue
        if want_tags is not None and not want_tags.issubset(set(etags)):
            continue

        th = _sample_height(heights, wsx, wsy, wx, wy)
        clearance = float(wz - th) if th is not None else 0.0

        cluster.elements.append(copy.deepcopy(ent._element))
        cluster.offsets.append((float(wx - ax), float(wy - ay)))
        cluster.clearances.append(clearance)

    return cluster


def _rotate_xy(dx: float, dy: float, cos_t: float, sin_t: float) -> tuple[float, float]:
    """Rotate (dx, dy) about the origin by angle whose cos/sin are given."""
    return (dx * cos_t - dy * sin_t, dx * sin_t + dy * cos_t)


def place_entities(
    target: "SceneBuilder | Scene",
    cluster: EntityCluster,
    x: float,
    y: float,
    *,
    rotation_deg: float = 0.0,
    snap_z: bool = True,
) -> list[ET.Element]:
    """Insert *cluster* into a target scene at anchor (x, y).

    *target* may be a :class:`blscene.compose.SceneBuilder` or a
    :class:`blscene.xscene.Scene`.  Each entity's anchor-relative offset is
    rotated about Z by *rotation_deg* and translated to the new anchor.  If
    *snap_z* is True, the entity Z is re-snapped to the target terrain and the
    harvested ground clearance re-applied (buried props stay buried).

    Rotation about Z also adds *rotation_deg* (in radians) to each top-level
    entity's ``rotation_euler`` Z component so the prop faces the rotated direction.

    Returns the list of inserted Element objects.
    """
    from blscene.compose import SceneBuilder  # local import avoids cycle

    if isinstance(target, SceneBuilder):
        scene = target._scene
        heights = target._heights
        node_size = target._node_size
    else:
        scene = target
        heights = None
        node_size = None

    if snap_z and heights is not None:
        H, W = heights.shape
        ny = (H - 1) // 128
        nx = (W - 1) // 128
        wsx = nx * (node_size or 200.0)
        wsy = ny * (node_size or 200.0)
    else:
        wsx = wsy = None

    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    inserted: list[ET.Element] = []
    for elem, (dx, dy), clearance in zip(
        cluster.elements, cluster.offsets, cluster.clearances
    ):
        new_elem = copy.deepcopy(elem)
        xform = new_elem.find("transform")
        if xform is None:
            continue

        # Declare the groups the copied subtree references (an orphan
        # group_object_guid crashes the editor); drop undeclarable ones.
        for emd in new_elem.iter("edit_mode_data"):
            guid = emd.get("group_object_guid")
            if not guid:
                continue
            if guid in cluster.group_objects:
                scene.add_group_object(guid, cluster.group_objects[guid])
            else:
                del emd.attrib["group_object_guid"]

        rdx, rdy = _rotate_xy(dx, dy, cos_t, sin_t)
        wx = x + rdx
        wy = y + rdy

        # Z: re-snap to target terrain + preserve ground clearance, else keep source Z.
        pos_str = xform.get("position")
        src_z = 0.0
        if pos_str:
            parts = [float(v.strip()) for v in pos_str.split(",")]
            if len(parts) == 3:
                src_z = parts[2]
        if snap_z and heights is not None:
            th = _sample_height(heights, wsx, wsy, wx, wy)
            wz = (th + clearance) if th is not None else src_z
        else:
            wz = src_z
        xform.set("position", "%.3f, %.3f, %.3f" % (wx, wy, wz))

        # Rotate the entity's own yaw (rotation_euler Z) by rotation_deg.
        if rotation_deg:
            rot_str = xform.get("rotation_euler")
            if rot_str:
                rvals = [float(v.strip()) for v in rot_str.split(",")]
                if len(rvals) == 3:
                    rvals[2] += theta
                    xform.set("rotation_euler", "%.3f, %.3f, %.3f" % tuple(rvals))

        _append_entity(scene, new_elem)
        inserted.append(new_elem)

    # Record provenance when target is a SceneBuilder.
    if isinstance(target, SceneBuilder) and cluster.source:
        target.record_harvest(
            "entities",
            cluster.source,
            detail=f"placed at anchor ({x:.1f}, {y:.1f})"
                   + (f" rot={rotation_deg:.1f}°" if rotation_deg else ""),
            count=len(inserted),
        )

    return inserted


def _append_entity(scene: Scene, new_elem: ET.Element) -> None:
    """Append a top-level game_entity element to <entities>, fixing indentation."""
    ent_elem = scene._entities_elem
    children = list(ent_elem)
    if children:
        children[-1].tail = "\n\t\t"
    ent_elem.append(new_elem)
    new_elem.tail = "\n\t"


# ---------------------------------------------------------------------------
# 3. Flora
# ---------------------------------------------------------------------------

@dataclass
class FloraCluster:
    """Deep-copied flora records with anchor-relative offsets + ground clearance.

    Attributes:
        records: deep-copied :class:`blnav.flora.FloraRecord` objects.  Their
            ``position`` fields still hold the SOURCE world XYZ; placement rewrites
            them.  The rot/scale matrix is preserved verbatim (rotated at placement).
        offsets: parallel (dx, dy) horizontal offset from the anchor.
        clearances: parallel per-record ground clearance from the source terrain.
        source: "module/scene" provenance string.
    """

    records: list[FloraRecord] = field(default_factory=list)
    offsets: list[tuple[float, float]] = field(default_factory=list)
    clearances: list[float] = field(default_factory=list)
    source: str = ""

    def __len__(self) -> int:
        return len(self.records)


def harvest_flora(
    scene_dir: str, x0: float, y0: float, x1: float, y1: float
) -> FloraCluster:
    """Harvest flora records whose XY position is inside the rect.

    Positions are stored relative to the anchor = rect center at source terrain Z.
    Per-record ground clearance (record Z minus source terrain height) is captured
    so it can be re-applied on the target terrain.
    """
    heights, wsx, wsy, _ = _load_source_terrain(scene_dir)
    ax = (x0 + x1) / 2.0
    ay = (y0 + y1) / 2.0

    flora = Flora.load(os.path.join(scene_dir, "flora.bin"))
    source = "/".join(os.path.normpath(scene_dir).split(os.sep)[-3:-1] + [os.path.basename(scene_dir)])
    cluster = FloraCluster(source=source)

    for rec in flora.records:
        fx, fy, fz = rec.position
        if not (x0 <= fx <= x1 and y0 <= fy <= y1):
            continue
        th = _sample_height(heights, wsx, wsy, fx, fy)
        clearance = float(fz - th) if th is not None else 0.0
        cluster.records.append(copy.deepcopy(rec))
        cluster.offsets.append((float(fx - ax), float(fy - ay)))
        cluster.clearances.append(clearance)

    return cluster


def _rotate_flora_matrix(matrix: list[float], cos_t: float, sin_t: float) -> list[float]:
    """Return a copy of the 3x4 row-major flora matrix rotated about Z by theta.

    The top-left 2x2 block (indices 0,1,4,5) holds the XY rotation/scale.  Left-
    multiplying it by the 2D rotation R = [[c,-s],[s,c]] rotates the flora about Z.
    Index 10 (Z scale) and indices 3,7,11 (runtime column) are preserved verbatim.
    """
    m = list(matrix)
    a, b = m[0], m[1]
    d, e = m[4], m[5]
    # R @ [[a,b],[d,e]]
    m[0] = cos_t * a - sin_t * d
    m[1] = cos_t * b - sin_t * e
    m[4] = sin_t * a + cos_t * d
    m[5] = sin_t * b + cos_t * e
    return m


def place_flora(
    target: "SceneBuilder | np.ndarray",
    cluster: FloraCluster,
    x: float,
    y: float,
    *,
    rotation_deg: float = 0.0,
    node_size: float | None = None,
) -> list[FloraRecord]:
    """Translate + rotate *cluster* to anchor (x, y) and re-snap Z to target terrain.

    *target* may be a :class:`blscene.compose.SceneBuilder` (records are registered
    so ``build()`` writes them into flora.bin) or a bare heights array (in which case
    *node_size* is required, and the returned records are simply produced, not stored).

    Each record's XY offset is rotated about Z by *rotation_deg*, its rot/scale
    matrix is rotated to match, and its Z is set to target terrain height + the
    harvested ground clearance.

    Returns the list of new (translated) FloraRecord objects.
    """
    from blscene.compose import SceneBuilder  # local import avoids cycle

    if isinstance(target, SceneBuilder):
        heights = target._heights
        ns = target._node_size
        builder = target
    else:
        heights = np.asarray(target, dtype=np.float32)
        ns = node_size
        builder = None
        if ns is None:
            raise ValueError("node_size is required when target is a heights array")

    if heights is None:
        raise ValueError("target has no heightmap to snap flora Z to")

    H, W = heights.shape
    ny = (H - 1) // 128
    nx = (W - 1) // 128
    wsx = nx * ns
    wsy = ny * ns

    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    new_records: list[FloraRecord] = []
    for rec, (dx, dy), clearance in zip(
        cluster.records, cluster.offsets, cluster.clearances
    ):
        rdx, rdy = _rotate_xy(dx, dy, cos_t, sin_t)
        wx = x + rdx
        wy = y + rdy
        th = _sample_height(heights, wsx, wsy, wx, wy)
        wz = (th + clearance) if th is not None else rec.position[2]

        matrix = _rotate_flora_matrix(rec.matrix, cos_t, sin_t) if rotation_deg else list(rec.matrix)
        new_records.append(FloraRecord(
            name=rec.name,
            kind=rec.kind,
            matrix=matrix,
            position=[float(wx), float(wy), float(wz)],
            extra=list(rec.extra),
        ))

    if builder is not None:
        builder.add_flora(new_records)
        if cluster.source:
            builder.record_harvest(
                "flora_transplant",
                cluster.source,
                detail=f"placed at anchor ({x:.1f}, {y:.1f})"
                       + (f" rot={rotation_deg:.1f}°" if rotation_deg else ""),
                count=len(new_records),
            )
    return new_records
