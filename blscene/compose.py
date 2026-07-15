"""Scene composer: create complete, game-loadable SceneObj folders.

Usage::

    # Battle scene from a heightmap
    builder = SceneBuilder.new_battle("my_battle", heights, node_size=200.0)
    builder.add("TacticalPosition", (600.0, 600.0, 50.0))
    builder.build(r"C:/Modules/MyMod/SceneObj")

    # Clone an existing scene
    builder = SceneBuilder.from_scene(r".../battle_terrain_a", "my_clone")
    builder.build(r"C:/Modules/MyMod/SceneObj")

Coordinate system: X/Y are the ground plane, Z is up.  Heights arrays are
indexed [row, col] = [Y, X] (row 0 = Y=0 = south edge).

References.txt: copied verbatim from the template/source scene as a v1
approximation — contains the mesh/prefab/texture asset manifest the engine
uses for preloading.  This may be stale after heavy entity edits but does not
affect scene correctness (the engine falls back to on-demand loading).
"""
from __future__ import annotations

import copy
import math
import os
import shutil
import warnings
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np

from blscene.xscene import Scene
from blscene.prefabs import PrefabCatalog
from blnav.terrain_write import generate_terrain, write_terrain, node_layer_usage
from blnav import rnm1
from blnav.generate import from_heightmap


# ---------------------------------------------------------------------------
# Names of entity categories to keep when cloning the battle template
# ---------------------------------------------------------------------------

# Top-level entity prefabs that are kept (gameplay-required non-decoration)
_KEEP_PREFABS = frozenset({
    "TacticalPosition",
    "TacticalRegion",
    "plains_ambient_sound",
})

# Top-level entity names (name= attr) that are kept
_KEEP_NAMES = frozenset({
    "border_soft",
    "barrier_path_1",
    "border_1",
    "sp_battle_set",
    "envmap_prop",
})


def _is_keep_entity(prefab: str | None, name: str | None) -> bool:
    """Return True if this top-level entity should be kept in a new_battle scene."""
    if prefab is not None and prefab in _KEEP_PREFABS:
        return True
    if name is not None and name in _KEEP_NAMES:
        return True
    return False


# ---------------------------------------------------------------------------
# Bilinear height sampling from a heights array
# ---------------------------------------------------------------------------

def _sample_height(heights: np.ndarray, world_size_x: float, world_size_y: float,
                   wx: float, wy: float) -> float | None:
    """Bilinearly sample *heights* at world position (wx, wy).

    heights: float32 (H, W), row=Y axis, col=X axis.
    Returns None if (wx, wy) is outside the grid bounds.
    """
    H, W = heights.shape
    # Normalised [0, W-1] and [0, H-1] indices
    gx = wx / world_size_x * (W - 1)
    gy = wy / world_size_y * (H - 1)
    if gx < 0 or gx > W - 1 or gy < 0 or gy > H - 1:
        return None
    x0, y0 = int(gx), int(gy)
    x1, y1 = min(x0 + 1, W - 1), min(y0 + 1, H - 1)
    fx, fy = gx - x0, gy - y0
    z = (heights[y0, x0] * (1 - fx) * (1 - fy)
         + heights[y0, x1] * fx * (1 - fy)
         + heights[y1, x0] * (1 - fx) * fy
         + heights[y1, x1] * fx * fy)
    return float(z)


# ---------------------------------------------------------------------------
# Path point height snapping
# ---------------------------------------------------------------------------

def _snap_position_z(
    elem: ET.Element,
    heights: np.ndarray,
    world_size_x: float,
    world_size_y: float,
) -> None:
    """Parse and rewrite the 'position' attribute on *elem*, snapping Z to terrain.

    No-op if the attribute is absent or out of terrain bounds.
    """
    pos_str = elem.get("position")
    if pos_str is None:
        return
    vals = [float(v.strip()) for v in pos_str.split(",")]
    if len(vals) != 3:
        return
    wx, wy = vals[0], vals[1]
    z = _sample_height(heights, world_size_x, world_size_y, wx, wy)
    if z is not None:
        elem.set("position", "%.3f, %.3f, %.3f" % (wx, wy, z))


def _snap_paths(
    root: ET.Element,
    heights: np.ndarray,
    world_size_x: float,
    world_size_y: float,
) -> None:
    """Snap Z of every path point (and its tangents) in <Paths> to the new terrain.

    Mirrors the plain-snap rule used for entities: new_z = terrain_height(x, y).
    Tangent positions carry absolute Z coordinates and are updated identically.
    """
    paths_elem = root.find("Paths")
    if paths_elem is None:
        return
    for path_elem in paths_elem:
        if path_elem.tag != "path":
            continue
        points_elem = path_elem.find("points")
        if points_elem is None:
            continue
        for point_elem in points_elem:
            if point_elem.tag != "point":
                continue
            _snap_position_z(point_elem, heights, world_size_x, world_size_y)
            for tangent_tag in ("first_tangent", "second_tangent"):
                tangent_elem = point_elem.find(tangent_tag)
                if tangent_elem is not None:
                    _snap_position_z(tangent_elem, heights, world_size_x, world_size_y)


# ---------------------------------------------------------------------------
# Terrain node record rebuild
# ---------------------------------------------------------------------------

_HEIGHTMAP_LEVEL = 7  # log2(128): generate_terrain always emits 129-px node textures


def _rebuild_terrain_nodes(
    terrain_elem: ET.Element,
    heights: np.ndarray,
    node_dim: tuple[int, int],
    node_size: float,
    node_usage: dict[tuple[int, int], list[int]] | None = None,
) -> None:
    """Regenerate <terrain><nodes> records to match the generated terrain.

    The template's records describe *its* terrain: per-node height bounds and
    texture levels (heightmap_level = log2 of per-node cell count, e.g. 8 for
    257-px nodes).  The engine sizes and strides its height/weight buffers
    from these records, so stale values from a 257-px template make it index
    our 129-px data out of bounds and crash at scene load.

    Per-node layer texturing (decoded from native battle_terrain_015/025/026/O
    /biome_022/085):
      * ``layer_is_used_mask_{summer,fall,winter,spring}`` is a bitmask where
        bit b is set iff layer b is used in that node.  Natives set it to exactly
        the WGHT-present slot set (minus seasonal-only layers).  We use the same
        mask for all four seasons since our generator layers are not seasonal.
      * ``weightmap_levels``: all 16 slots get ``heightmap_level`` — the pattern
        native 129-res scenes use (battle_terrain_015/026/J/018 pad all 16; no
        native ever sets fewer entries than its layer-def count).  Writing levels
        only for the used layers crashed the loader (AV at Native+0x441700) once
        a mask bit activated a layer path: the level is declarative per-slot
        capacity, not a mask of what data is present.

    *node_usage* maps (idx, idy) -> sorted list of used layer indices.  When None
    the single-layer default ([0] everywhere) is used.
    """
    nx, ny = node_dim
    if node_usage is None:
        node_usage = {(idx, idy): [0] for idx in range(nx) for idy in range(ny)}

    nodes_elem = terrain_elem.find("nodes")
    if nodes_elem is None:
        nodes_elem = ET.SubElement(terrain_elem, "nodes")
    for child in list(nodes_elem):
        nodes_elem.remove(child)

    nodes_elem.text = "\n\t\t\t"
    for idx in range(nx):
        for idy in range(ny):
            tile = heights[idy * 128 : idy * 128 + 129, idx * 128 : idx * 128 + 129]
            tmin, tmax = float(tile.min()), float(tile.max())
            used = node_usage.get((idx, idy), [0])
            mask = 0
            for layer in used:
                mask |= (1 << layer)
            node = ET.SubElement(nodes_elem, "node", {
                "idx": str(idx),
                "idy": str(idy),
                "occluders_enabled": "true",
                # per-node layer-usage bitmask (same for all seasons: our layers
                # are not seasonal). bit b set iff layer b used in this node.
                "layer_is_used_mask_summer": str(mask),
                "layer_is_used_mask_fall": str(mask),
                "layer_is_used_mask_winter": str(mask),
                "layer_is_used_mask_spring": str(mask),
                "layer_is_used_mask": "true",
                "height_complexity": "%.3f" % ((tmax - tmin) / node_size),
                "min_height": "%.3f" % tmin,
                "max_height": "%.3f" % tmax,
            })
            node.text = "\n\t\t\t\t"
            node.tail = "\n\t\t\t"
            tl = ET.SubElement(node, "texture_levels")
            tl.text = "\n\t\t\t\t\t"
            tl.tail = "\n\t\t\t"
            for nm, val in (
                ("heightmap_level", _HEIGHTMAP_LEVEL),
                ("min_heightmap_level", 2),
                ("normalmap_level", _HEIGHTMAP_LEVEL),
            ):
                v = ET.SubElement(tl, "variable", {"name": nm, "value": str(val)})
                v.tail = "\n\t\t\t\t\t"
            wl = ET.SubElement(tl, "variable", {"name": "weightmap_levels"})
            wl.text = "\n\t\t\t\t\t\t"
            wl.tail = "\n\t\t\t\t"
            for layer in range(16):
                lv = ET.SubElement(wl, "variable", {
                    "layer": str(layer),
                    # declarative per-slot capacity: natives pad all 16 at 129-res
                    "value": str(_HEIGHTMAP_LEVEL),
                })
                lv.tail = "\n\t\t\t\t\t\t"
            lv.tail = "\n\t\t\t\t\t"
    node.tail = "\n\t\t"


# ---------------------------------------------------------------------------
# SceneBuilder
# ---------------------------------------------------------------------------

class SceneBuilder:
    """Builds a complete Bannerlord SceneObj folder.

    Do not instantiate directly; use :meth:`from_scene` or :meth:`new_battle`.
    """

    def __init__(
        self,
        name: str,
        scene: Scene,
        *,
        source_dir: str,
        heights: np.ndarray | None = None,
        node_size: float | None = None,
        min_height: float | None = None,
        max_height: float | None = None,
        terrain_dirty: bool = False,
        layer_weights: dict[int, np.ndarray] | None = None,
    ) -> None:
        self._name = name
        self._scene = scene
        self._source_dir = source_dir  # template/source folder for asset copying
        self._heights = heights
        self._node_size = node_size
        self._min_height = min_height
        self._max_height = max_height
        self._terrain_dirty = terrain_dirty  # False = copy source terrain.bin
        self._layer_weights = layer_weights  # None = single-layer (uniform layer 0)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_scene(cls, scene_dir: str, name: str) -> "SceneBuilder":
        """Clone an existing scene folder as starting point.

        Loads its scene.xscene; remembers *scene_dir* for asset copying.
        terrain.bin and navmesh.bin will be copied unmodified when build() is
        called (terrain_dirty=False).
        """
        xscene_path = os.path.join(scene_dir, "scene.xscene")
        scene = Scene.load(xscene_path)
        return cls(
            name,
            scene,
            source_dir=scene_dir,
            terrain_dirty=False,
        )

    @classmethod
    def new_battle(
        cls,
        name: str,
        heights: np.ndarray,
        node_size: float = 200.0,
        template_dir: str = (
            r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
            r"\Modules\SandBoxCore\SceneObj\battle_terrain_a"
        ),
        layer_weights: dict[int, np.ndarray] | None = None,
    ) -> "SceneBuilder":
        """Create a battle scene from a heightmap.

        Clones the template xscene, patches the <terrain> element dimensions,
        keeps gameplay-required entities (borders, sp_battle_set hierarchy,
        TacticalPosition/Region, AmbientSoundEmitter, ReflectionCapturer) and
        snaps their z to the new terrain height, removes decoration entities.

        Args:
            name: output scene folder name.
            heights: float32 (H, W) heightmap covering [0, world_size_x] x
                [0, world_size_y].  Shape must be (ny*128+1, nx*128+1).
            node_size: terrain node size in metres (default 200).
            template_dir: path to the battle_terrain_a SceneObj folder.
            layer_weights: optional {layer_index: full-map weight array} for
                multi-layer terrain texturing.  Each array matches *heights*
                shape.  Layer 0 defaults to the base.  Referenced layer indices
                must exist in the template's <layers> list.  None = single layer 0.
        """
        heights = np.asarray(heights, dtype=np.float32)
        H, W = heights.shape

        # Derive node_dim from shape: each node is 128 cells + 1 overlap pixel
        if (H - 1) % 128 != 0 or (W - 1) % 128 != 0:
            raise ValueError(
                f"heights shape {heights.shape} is not compatible with 129-node math "
                f"(H-1 and W-1 must each be multiples of 128)"
            )
        ny = (H - 1) // 128
        nx = (W - 1) // 128
        node_dim = (nx, ny)
        world_size_x = nx * node_size
        world_size_y = ny * node_size
        min_height = float(np.min(heights))
        max_height = float(np.max(heights))

        # Load template xscene
        xscene_path = os.path.join(template_dir, "scene.xscene")
        scene = Scene.load(xscene_path)

        # --- Patch <terrain> element attributes ---
        terrain_elem = scene._root.find("terrain")
        if terrain_elem is None:
            raise RuntimeError("Template xscene has no <terrain> element")
        terrain_elem.set("node_dimension_x", str(nx))
        terrain_elem.set("node_dimension_y", str(ny))
        terrain_elem.set("node_size", "%.3f" % node_size)
        terrain_elem.set("min_height", "%.3f" % min_height)
        terrain_elem.set("max_height", "%.3f" % max_height)

        # --- Rebuild per-node records (height bounds, texture levels, masks) ---
        node_usage = node_layer_usage(layer_weights, heights.shape, node_dim)
        _rebuild_terrain_nodes(terrain_elem, heights, node_dim, node_size, node_usage)

        # Also update scene name
        scene._root.set("name", name)

        # --- Filter entities ---
        # Work on a copy of the entity list so we can iterate + remove
        entities_to_remove = []
        for ent in scene.entities:
            pfb = ent.prefab
            nm = ent.name
            if not _is_keep_entity(pfb, nm):
                entities_to_remove.append(ent)

        for ent in entities_to_remove:
            scene.remove_entity(ent)

        # --- Snap kept entities z to new terrain height ---
        for ent in scene.entities:
            pos = ent.position
            if pos is None:
                continue
            wx, wy, _ = pos
            z = _sample_height(heights, world_size_x, world_size_y, wx, wy)
            if z is not None:
                ent.position = (wx, wy, z)

        # --- Snap path point positions z to new terrain height ---
        _snap_paths(scene._root, heights, world_size_x, world_size_y)

        return cls(
            name,
            scene,
            source_dir=template_dir,
            heights=heights,
            node_size=node_size,
            min_height=min_height,
            max_height=max_height,
            terrain_dirty=True,
            layer_weights=layer_weights,
        )

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add(
        self,
        prefab_name: str,
        position: tuple[float, float, float],
        rotation_euler: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: tuple[float, float, float] | None = None,
        levels: list[str] | None = None,
        catalog: PrefabCatalog | None = None,
    ) -> None:
        """Add a prefab instance to the scene.

        Args:
            prefab_name: name of the prefab to place.
            position: (x, y, z) world position.
            rotation_euler: (rx, ry, rz) rotation in radians.
            scale: optional (sx, sy, sz) scale.
            levels: optional list of level names.
            catalog: if provided, raises KeyError for unknown prefab names.
        """
        if catalog is not None and catalog.get(prefab_name) is None:
            raise KeyError(f"Prefab not found in catalog: {prefab_name!r}")
        self._scene.add_entity(prefab_name, position, rotation_euler, scale, levels)

    def copy_entities(
        self,
        src_scene_path: str,
        prefab: str | None = None,
        name_contains: str | None = None,
        offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        """Import matching top-level entities from another scene.

        Deep-copies their XML subtree and applies *offset* to position.

        Args:
            src_scene_path: path to source scene.xscene file.
            prefab: filter by prefab name (exact match).
            name_contains: filter by name/prefab substring.
            offset: (dx, dy, dz) added to each entity's position.
        """
        src = Scene.load(src_scene_path)
        matched = src.find_entities(prefab=prefab, name_contains=name_contains)

        ent_elem = self._scene._entities_elem
        children = list(ent_elem)
        dx, dy, dz = offset

        for src_ent in matched:
            new_elem = copy.deepcopy(src_ent._element)
            # Apply offset if entity has a transform/position
            xform = new_elem.find("transform")
            if xform is not None:
                pos_str = xform.get("position")
                if pos_str is not None:
                    vals = tuple(float(v.strip()) for v in pos_str.split(","))
                    if len(vals) == 3:
                        new_pos = (vals[0] + dx, vals[1] + dy, vals[2] + dz)
                        xform.set("position", "%.3f, %.3f, %.3f" % new_pos)

            # Fix indentation tails for the new element
            if children:
                children[-1].tail = "\n\t\t"
            ent_elem.append(new_elem)
            new_elem.tail = "\n\t"
            children = list(ent_elem)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, out_dir: str) -> str:
        """Write a complete SceneObj folder to *out_dir/<name>/*.

        Writes: scene.xscene, terrain.bin, flora.bin, atmosphere.xml,
        references.txt, navmesh.bin.

        Validates that all sp_* entities have terrain under them (warns if not).

        Returns: path to the written scene folder.
        """
        scene_dir = os.path.join(out_dir, self._name)
        os.makedirs(scene_dir, exist_ok=True)

        # --- Validate sp_* entities are within terrain bounds ---
        self._validate_sp_entities(scene_dir)

        # --- scene.xscene ---
        xscene_path = os.path.join(scene_dir, "scene.xscene")
        self._scene.save(xscene_path)

        # --- terrain.bin ---
        terrain_path = os.path.join(scene_dir, "terrain.bin")
        if self._terrain_dirty and self._heights is not None:
            H, W = self._heights.shape
            ny = (H - 1) // 128
            nx = (W - 1) // 128
            terrain = generate_terrain(
                self._heights,
                node_dim=(nx, ny),
                min_height=self._min_height,
                max_height=self._max_height,
                layer_weights=self._layer_weights,
            )
            write_terrain(terrain, terrain_path)
        else:
            src_terrain = os.path.join(self._source_dir, "terrain.bin")
            if os.path.exists(src_terrain):
                shutil.copy2(src_terrain, terrain_path)

        # --- flora.bin ---
        flora_path = os.path.join(scene_dir, "flora.bin")
        src_flora = os.path.join(self._source_dir, "flora.bin")
        if os.path.exists(src_flora):
            shutil.copy2(src_flora, flora_path)
        else:
            # 12-byte empty stub: "FLR2" + u32(4) + u32(0)
            import struct
            with open(flora_path, "wb") as fh:
                fh.write(b"FLR2")
                fh.write(struct.pack("<II", 4, 0))

        # --- atmosphere.xml ---
        atm_path = os.path.join(scene_dir, "atmosphere.xml")
        src_atm = os.path.join(self._source_dir, "atmosphere.xml")
        if os.path.exists(src_atm):
            shutil.copy2(src_atm, atm_path)

        # --- references.txt ---
        # Copied verbatim from template/source as v1 approximation.
        # This is a mesh/prefab/texture preload manifest; may be stale after
        # heavy entity edits but does not affect scene correctness.
        ref_path = os.path.join(scene_dir, "references.txt")
        src_ref = os.path.join(self._source_dir, "references.txt")
        if os.path.exists(src_ref):
            shutil.copy2(src_ref, ref_path)

        # --- navmesh.bin ---
        navmesh_path = os.path.join(scene_dir, "navmesh.bin")
        if self._terrain_dirty and self._heights is not None:
            H, W = self._heights.shape
            ny = (H - 1) // 128
            nx = (W - 1) // 128
            world_size_x = nx * (self._node_size or 200.0)
            world_size_y = ny * (self._node_size or 200.0)
            mesh = from_heightmap(
                self._heights,
                world_size_x=world_size_x,
                world_size_y=world_size_y,
                cell_size=4.0,
                max_slope_deg=40.0,
            )
            payload = mesh.serialize()
            rnm1.write(navmesh_path, payload)
        else:
            src_nav = os.path.join(self._source_dir, "navmesh.bin")
            if os.path.exists(src_nav):
                shutil.copy2(src_nav, navmesh_path)

        return scene_dir

    # ------------------------------------------------------------------
    # Internal validation
    # ------------------------------------------------------------------

    def _validate_sp_entities(self, scene_dir: str) -> None:
        """Warn for sp_* top-level entities outside the terrain grid."""
        if self._heights is None:
            return
        H, W = self._heights.shape
        ny = (H - 1) // 128
        nx = (W - 1) // 128
        world_size_x = nx * (self._node_size or 200.0)
        world_size_y = ny * (self._node_size or 200.0)

        offenders = []
        for ent in self._scene.entities:
            nm = ent.name or ""
            if not nm.startswith("sp_"):
                continue
            pos = ent.position
            if pos is None:
                continue
            wx, wy, _ = pos
            z = _sample_height(self._heights, world_size_x, world_size_y, wx, wy)
            if z is None:
                offenders.append(f"{nm} at ({wx:.1f}, {wy:.1f})")

        if offenders:
            warnings.warn(
                f"sp_* entities outside terrain bounds in {self._name!r}: "
                + ", ".join(offenders),
                stacklevel=3,
            )
