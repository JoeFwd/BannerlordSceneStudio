"""Scene corpus indexer for Mount & Blade II: Bannerlord.

Parses every scene's scene.xscene into a queryable JSON index.  Each scene
record contains terrain metadata, entity summaries, and file-existence info.

Usage::

    from blscene.corpus import build_corpus, save_corpus, load_corpus

    corpus = build_corpus(r"D:\\...\\Modules")
    save_corpus(corpus, "corpus.json")
    corpus = load_corpus("corpus.json")
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _file_info(scene_dir: str, filename: str) -> int | None:
    """Return byte size of *filename* in *scene_dir*, or None if absent."""
    p = os.path.join(scene_dir, filename)
    try:
        return os.path.getsize(p)
    except OSError:
        return None


def _atmosphere_file(scene_dir: str) -> tuple[str, int] | None:
    """Return (filename, size) for any .xml in scene_dir other than scene.xscene, or None."""
    try:
        for name in os.listdir(scene_dir):
            if name.lower().endswith(".xml") and name.lower() != "scene.xscene":
                p = os.path.join(scene_dir, name)
                try:
                    return (name, os.path.getsize(p))
                except OSError:
                    pass
    except OSError:
        pass
    return None


def _parse_pos(value: str | None) -> list[float] | None:
    """Parse 'x, y, z' into [x, y, z], or return None."""
    if value is None:
        return None
    try:
        parts = [float(p.strip()) for p in value.split(",")]
        if len(parts) >= 3:
            return parts[:3]
    except ValueError:
        pass
    return None


def _count_child_entities(elem: ET.Element) -> int:
    """Count direct game_entity children inside <children> of *elem*."""
    children_elem = elem.find("children")
    if children_elem is None:
        return 0
    return sum(1 for ch in children_elem if ch.tag == "game_entity")


# ---------------------------------------------------------------------------
# Per-scene parser
# ---------------------------------------------------------------------------

def _parse_scene(path: str, module: str, scene_name: str) -> dict[str, Any]:
    """Parse a single scene.xscene and return the scene record dict."""
    scene_dir = os.path.dirname(path)

    # File existence / sizes
    terrain_size = _file_info(scene_dir, "terrain.bin")
    flora_size = _file_info(scene_dir, "flora.bin")
    navmesh_size = _file_info(scene_dir, "navmesh.bin")
    atm = _atmosphere_file(scene_dir)

    files: dict[str, Any] = {}
    if terrain_size is not None:
        files["terrain.bin"] = terrain_size
    if flora_size is not None:
        files["flora.bin"] = flora_size
    if navmesh_size is not None:
        files["navmesh.bin"] = navmesh_size
    if atm is not None:
        files["atmosphere"] = {"name": atm[0], "size": atm[1]}

    # Parse XML
    tree = ET.parse(path)
    root = tree.getroot()

    # Terrain
    terrain_info: dict[str, Any] | None = None
    terrain_elem = root.find("terrain")
    if terrain_elem is not None:
        def _float_attr(attr: str) -> float | None:
            v = terrain_elem.get(attr)
            return float(v) if v is not None else None

        def _int_attr(attr: str) -> int | None:
            v = terrain_elem.get(attr)
            return int(v) if v is not None else None

        # Layer names from <layers><layer name="...">
        layer_names: list[str] = []
        layers_elem = terrain_elem.find("layers")
        if layers_elem is not None:
            for layer in layers_elem:
                if layer.tag == "layer":
                    n = layer.get("name")
                    if n:
                        layer_names.append(n)

        # Node heightmap_level values: summarised as distinct levels seen
        heightmap_levels: list[int] = []
        nodes_elem = terrain_elem.find("nodes")
        if nodes_elem is not None:
            for node in nodes_elem:
                if node.tag != "node":
                    continue
                tex_levels = node.find("texture_levels")
                if tex_levels is None:
                    continue
                for var in tex_levels:
                    if var.tag == "variable" and var.get("name") == "heightmap_level":
                        v = var.get("value")
                        if v is not None:
                            try:
                                heightmap_levels.append(int(v))
                            except ValueError:
                                pass
                        break

        distinct_levels = sorted(set(heightmap_levels))

        terrain_info = {
            "node_dimension_x": _int_attr("node_dimension_x"),
            "node_dimension_y": _int_attr("node_dimension_y"),
            "node_size": _float_attr("node_size"),
            "min_height": _float_attr("min_height"),
            "max_height": _float_attr("max_height"),
            "layer_names": layer_names,
            "heightmap_levels": distinct_levels,
        }

    # Entities
    entities: list[dict[str, Any]] = []
    entities_elem = root.find("entities")
    if entities_elem is not None:
        for ge in entities_elem:
            if ge.tag != "game_entity":
                continue

            name = ge.get("name")
            prefab = ge.get("prefab")

            # Tags
            tags: list[str] = []
            tags_elem = ge.find("tags")
            if tags_elem is not None:
                for tg in tags_elem:
                    if tg.tag == "tag":
                        tn = tg.get("name")
                        if tn:
                            tags.append(tn)

            # Position from <transform>
            pos: list[float] | None = None
            xform = ge.find("transform")
            if xform is not None:
                pos = _parse_pos(xform.get("position"))

            child_count = _count_child_entities(ge)

            rec: dict[str, Any] = {"name": name, "prefab": prefab, "tags": tags, "pos": pos, "children": child_count}
            entities.append(rec)

    prefab_refs = sorted({e["prefab"] for e in entities if e["prefab"]})

    return {
        "module": module,
        "scene": scene_name,
        "files": files,
        "terrain": terrain_info,
        "entities": entities,
        "entity_count": len(entities),
        "prefab_refs": prefab_refs,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_corpus(modules_dir: str) -> dict[str, Any]:
    """Scan all scenes under *modules_dir* and return the corpus dict.

    The returned dict has keys:
      - ``"scenes"``: list of per-scene records
      - ``"skipped"``: list of scene dirs that had no scene.xscene
      - ``"parse_errors"``: list of {scene_dir, error} for XML parse failures
    """
    scenes: list[dict[str, Any]] = []
    skipped: list[str] = []
    parse_errors: list[dict[str, str]] = []

    try:
        module_entries = sorted(os.listdir(modules_dir))
    except OSError as exc:
        raise ValueError(f"Cannot list modules dir: {modules_dir!r}: {exc}") from exc

    for module_name in module_entries:
        module_dir = os.path.join(modules_dir, module_name)
        if not os.path.isdir(module_dir):
            continue
        scene_obj_dir = os.path.join(module_dir, "SceneObj")
        if not os.path.isdir(scene_obj_dir):
            continue

        try:
            scene_dirs = sorted(os.listdir(scene_obj_dir))
        except OSError:
            continue

        for scene_name in scene_dirs:
            scene_dir = os.path.join(scene_obj_dir, scene_name)
            if not os.path.isdir(scene_dir):
                continue
            xscene_path = os.path.join(scene_dir, "scene.xscene")
            if not os.path.isfile(xscene_path):
                skipped.append(os.path.join(module_name, scene_name))
                continue

            try:
                record = _parse_scene(xscene_path, module_name, scene_name)
                scenes.append(record)
            except ET.ParseError as exc:
                parse_errors.append({"scene_dir": os.path.join(module_name, scene_name), "error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                parse_errors.append({"scene_dir": os.path.join(module_name, scene_name), "error": repr(exc)})

    return {
        "scenes": scenes,
        "skipped": skipped,
        "parse_errors": parse_errors,
    }


def save_corpus(corpus: dict[str, Any], path: str) -> None:
    """Write *corpus* to *path* as JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, separators=(",", ":"))


def load_corpus(path: str) -> dict[str, Any]:
    """Load a corpus previously saved with :func:`save_corpus`."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
