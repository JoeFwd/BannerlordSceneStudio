"""Scene corpus indexer for Mount & Blade II: Bannerlord.

Parses every scene's scene.xscene into a queryable JSON index.  Each scene
record contains terrain metadata, entity summaries, navmesh stats, and
file-existence info.

Usage::

    from blscene.corpus import build_corpus, save_corpus, load_corpus

    corpus = build_corpus(r"D:\\...\\Modules")
    save_corpus(corpus, "corpus.json")
    corpus = load_corpus("corpus.json")

    # Terrain grids (downsampled float32) are stored separately:
    #   corpus_terrain.npz  (numpy savez_compressed, key = "<module>/<scene>")
    # build_corpus() returns terrain grids in corpus["_terrain_grids"] (not
    # serialised to JSON).  Use save_corpus() to write both files.
"""
from __future__ import annotations

import io
import json
import os
import struct
import xml.etree.ElementTree as ET
from collections import Counter, deque
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
# Terrain binary reader helpers
# ---------------------------------------------------------------------------

_TERRAIN_MAGIC = b"ZGR6RTRN"
_TERRAIN_TAGS = ("MIDX", "HGHT", "NRML", "WGHT", "PHYM")

_TARGET_GRID = 96  # target downsampled side length


def _read_terrain_section(data: bytes, off: int, csz: int, usz: int) -> tuple[list[int], bytes]:
    """Read one terrain section at *off* in *data*; return (node_offsets, decompressed)."""
    from blnav import lz4raw
    k = off
    table: list[int] = []
    while True:
        (v,) = struct.unpack_from("<I", data, k)
        if (table and v <= table[-1]) or (not table and v != 0):
            break
        table.append(v)
        k += 4
    mode, _pad, inner_usz, _inner_csz, _ptr = struct.unpack_from("<IIQQQ", data, k)
    if mode != 3:
        raise ValueError(f"unexpected stream mode {mode}")
    body = k + 32 + 8
    out, _consumed = lz4raw.decompress_prefix(data[body:], inner_usz)
    return table, out


def _node_slice(data: bytes, table: list[int], idx: int) -> bytes:
    end = table[idx + 1] if idx + 1 < len(table) else len(data)
    return data[table[idx]:end]


def _parse_terrain_grid(terrain_path: str, nx: int, ny: int):
    """Return (full_grid uint16, downsampled float32 ~96x96, stats_dict).

    Raises on parse errors.
    """
    import numpy as np
    from PIL import Image

    raw = open(terrain_path, "rb").read()
    if raw[:8] != _TERRAIN_MAGIC:
        raise ValueError(f"bad terrain magic {raw[:8]!r}")

    # Parse section table
    sections: dict[str, tuple[list[int], bytes]] = {}
    j = 0x0C
    for _ in range(5):
        tag = raw[j: j + 4].decode()
        count, off, csz, usz = struct.unpack_from("<4I", raw, j + 4)
        j += 20
        if count != 1:
            raise ValueError(f"{tag}: unexpected count {count}")
        if tag == "HGHT":
            table, decomp = _read_terrain_section(raw, off, csz, usz)
            sections["HGHT"] = (table, decomp)

    if "HGHT" not in sections:
        raise ValueError("No HGHT section found")

    table, decomp = sections["HGHT"]
    n_nodes = len(table)
    if nx * ny != n_nodes:
        raise ValueError(f"node_dim {nx}×{ny}={nx*ny} but HGHT has {n_nodes} nodes")

    tiles = []
    for i in range(n_nodes):
        blob = _node_slice(decomp, table, i)
        (png_size,) = struct.unpack_from("<I", blob, 0)
        png_bytes = blob[4: 4 + png_size]
        img = Image.open(io.BytesIO(png_bytes))
        tiles.append(np.array(img))

    th, tw = tiles[0].shape
    full = np.zeros(((th - 1) * ny + 1, (tw - 1) * nx + 1), dtype=tiles[0].dtype)
    for i, tile in enumerate(tiles):
        gx, gy = i % nx, i // nx
        full[gy * (th - 1): gy * (th - 1) + th, gx * (tw - 1): gx * (tw - 1) + tw] = tile

    # Height stats (uint16 values are raw; convert to float for stats)
    fgrid = full.astype(np.float32)
    h_min = float(fgrid.min())
    h_max = float(fgrid.max())
    h_mean = float(fgrid.mean())

    # Roughness: std of local gradient magnitude (Sobel-like using np.gradient)
    dy, dx = np.gradient(fgrid)
    grad_mag = np.sqrt(dx * dx + dy * dy)
    roughness = float(grad_mag.std())

    # Downsample to ~TARGET_GRID × TARGET_GRID
    H, W = full.shape
    # Compute step sizes to get as close to TARGET_GRID as possible
    step_h = max(1, H // _TARGET_GRID)
    step_w = max(1, W // _TARGET_GRID)
    small = fgrid[::step_h, ::step_w]

    stats = {
        "grid_h": H,
        "grid_w": W,
        "h_min": h_min,
        "h_max": h_max,
        "h_mean": round(h_mean, 2),
        "roughness": round(roughness, 2),
        "downsample_shape": list(small.shape),
    }
    return full, small, stats


# ---------------------------------------------------------------------------
# Navmesh binary reader helpers
# ---------------------------------------------------------------------------

_RNM1_MAGIC = b"RNM1"
_RNM1_VERSION = 3
_RNM1_HEADER = 0x30
_NMG9_MAGIC = b"NMG9"

_SPECIAL_IDS = frozenset({0, 1, 2, 7})
_SPECIAL_RANGE_LO = 100
_SPECIAL_RANGE_HI = 999
_G3_HIST_CAP = 50  # max distinct g3 ids in histogram


def _parse_navmesh_stats(navmesh_path: str) -> dict[str, Any]:
    """Parse navmesh.bin and return stats dict. Raises on errors."""
    import lz4.block
    import numpy as np

    raw = open(navmesh_path, "rb").read()
    if raw[:4] != _RNM1_MAGIC:
        raise ValueError(f"bad RNM1 magic {raw[:4]!r}")
    (version,) = struct.unpack_from("<I", raw, 0x08)
    if version != _RNM1_VERSION:
        raise ValueError(f"unsupported RNM1 version {version}")
    (usz,) = struct.unpack_from("<Q", raw, 0x10)
    payload = lz4.block.decompress(raw[_RNM1_HEADER:], uncompressed_size=usz)

    if payload[:4] != _NMG9_MAGIC:
        raise ValueError(f"bad NMG9 magic {payload[:4]!r}")

    i = 4
    (vcount,) = struct.unpack_from("<I", payload, i)
    i += 4
    vertices = [struct.unpack_from("<3f", payload, i + k * 12) for k in range(vcount)]
    i += vcount * 12

    (ecount,) = struct.unpack_from("<I", payload, i)
    i += 4
    # Parse edges (24 bytes each: i32 -1, u32 va, u32 vb, i32 -1, i32 -1, u32 0)
    edge_vas = []
    edge_vbs = []
    for _ in range(ecount):
        _f0, va, vb, _f3, _f4, _f5 = struct.unpack_from("<i2I2iI", payload, i)
        edge_vas.append(va)
        edge_vbs.append(vb)
        i += 24

    (fcount,) = struct.unpack_from("<I", payload, i)
    i += 4

    # Parse faces, collecting per-face edge_ids and g3
    face_edge_ids: list[list[int]] = []
    g3_values: list[int] = []
    for k in range(fcount):
        (n,) = struct.unpack_from("<I", payload, i)
        if not 3 <= n <= 64:
            raise ValueError(f"face {k}: implausible vertex count {n}")
        _verts = struct.unpack_from(f"<{n}I", payload, i + 4)
        eids = list(struct.unpack_from(f"<{n}I", payload, i + 4 + n * 4))
        _g1, _g2, g3, _g4, _g5 = struct.unpack_from("<5i", payload, i + 4 + n * 8)
        face_edge_ids.append(eids)
        g3_values.append(g3)
        i += 4 + 8 * n + 21

    # Bounding box from vertices
    if vertices:
        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        zs = [v[2] for v in vertices]
        bbox = {
            "x_min": round(min(xs), 3), "x_max": round(max(xs), 3),
            "y_min": round(min(ys), 3), "y_max": round(max(ys), 3),
            "z_min": round(min(zs), 3), "z_max": round(max(zs), 3),
        }
    else:
        bbox = None

    # Connected islands via BFS on edge adjacency
    edge_to_faces: dict[int, list[int]] = {}
    for fi, eids in enumerate(face_edge_ids):
        for eid in eids:
            edge_to_faces.setdefault(eid, []).append(fi)

    visited = bytearray(fcount)
    island_sizes: list[int] = []
    for start in range(fcount):
        if visited[start]:
            continue
        q = deque([start])
        visited[start] = 1
        size = 0
        while q:
            fi = q.popleft()
            size += 1
            for eid in face_edge_ids[fi]:
                for nfi in edge_to_faces.get(eid, []):
                    if not visited[nfi]:
                        visited[nfi] = 1
                        q.append(nfi)
        island_sizes.append(size)

    island_sizes.sort(reverse=True)
    top5 = island_sizes[:5]

    # g3 histogram (cap at G3_HIST_CAP most common)
    g3_ctr = Counter(g3_values)
    g3_hist = {str(k): v for k, v in g3_ctr.most_common(_G3_HIST_CAP)}

    # Special band face count
    special_count = sum(
        1 for g in g3_values
        if g in _SPECIAL_IDS or _SPECIAL_RANGE_LO <= g <= _SPECIAL_RANGE_HI
    )

    return {
        "face_count": fcount,
        "vertex_count": vcount,
        "bbox": bbox,
        "island_count": len(island_sizes),
        "island_sizes_top5": top5,
        "g3_histogram": g3_hist,
        "special_band_face_count": special_count,
    }


# ---------------------------------------------------------------------------
# Per-scene parser
# ---------------------------------------------------------------------------

def _parse_scene(
    path: str,
    module: str,
    scene_name: str,
) -> tuple[dict[str, Any], Any | None]:
    """Parse a single scene.xscene and return (scene_record, terrain_grid_or_None).

    terrain_grid_or_None is a downsampled float32 numpy array, or None.
    """
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

    # Terrain (XML metadata)
    terrain_info: dict[str, Any] | None = None
    terrain_xml_nx: int | None = None
    terrain_xml_ny: int | None = None
    terrain_grid_small = None

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

        node_size = _float_attr("node_size")
        nx = _int_attr("node_dimension_x")
        ny = _int_attr("node_dimension_y")
        terrain_xml_nx = nx
        terrain_xml_ny = ny

        # World size in metres: node_size * node_count (nodes share a border pixel,
        # but world extent = node_size * dim)
        world_size_x = (node_size * nx) if (node_size and nx) else None
        world_size_y = (node_size * ny) if (node_size and ny) else None

        terrain_info = {
            "node_dimension_x": nx,
            "node_dimension_y": ny,
            "node_size": node_size,
            "world_size_x": world_size_x,
            "world_size_y": world_size_y,
            "min_height": _float_attr("min_height"),
            "max_height": _float_attr("max_height"),
            "layer_names": layer_names,
            "heightmap_levels": distinct_levels,
            # Extended binary stats (filled in below if terrain.bin exists)
            "grid_h": None,
            "grid_w": None,
            "h_min": None,
            "h_max": None,
            "h_mean": None,
            "roughness": None,
            "terrain_grid_key": None,
            "terrain_grid_shape": None,
            "terrain_error": None,
        }

        # Parse terrain.bin if present
        if terrain_size is not None and nx and ny:
            terrain_path = os.path.join(scene_dir, "terrain.bin")
            try:
                _full, terrain_grid_small, tstats = _parse_terrain_grid(terrain_path, nx, ny)
                terrain_info["grid_h"] = tstats["grid_h"]
                terrain_info["grid_w"] = tstats["grid_w"]
                terrain_info["h_min"] = tstats["h_min"]
                terrain_info["h_max"] = tstats["h_max"]
                terrain_info["h_mean"] = tstats["h_mean"]
                terrain_info["roughness"] = tstats["roughness"]
                terrain_info["terrain_grid_key"] = f"{module}/{scene_name}"
                terrain_info["terrain_grid_shape"] = tstats["downsample_shape"]
            except Exception as exc:  # noqa: BLE001
                terrain_info["terrain_error"] = repr(exc)

    # Navmesh stats
    navmesh_stats: dict[str, Any] | None = None
    if navmesh_size is not None:
        navmesh_path = os.path.join(scene_dir, "navmesh.bin")
        try:
            navmesh_stats = _parse_navmesh_stats(navmesh_path)
        except Exception as exc:  # noqa: BLE001
            navmesh_stats = {"navmesh_error": repr(exc)}

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

    record = {
        "module": module,
        "scene": scene_name,
        "files": files,
        "terrain": terrain_info,
        "navmesh": navmesh_stats,
        "entities": entities,
        "entity_count": len(entities),
        "prefab_refs": prefab_refs,
    }
    return record, terrain_grid_small


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _scene_worker(item: tuple[str, str, str]) -> tuple[dict | None, Any | None, str | None, str | None]:
    """Module-level worker used by multiprocessing pool (must be picklable)."""
    xscene_path, module_name, scene_name = item
    try:
        record, grid = _parse_scene(xscene_path, module_name, scene_name)
        return record, grid, None, None
    except ET.ParseError as exc:
        return None, None, os.path.join(module_name, scene_name), str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, None, os.path.join(module_name, scene_name), repr(exc)


def build_corpus(modules_dir: str, *, workers: int = 4) -> dict[str, Any]:
    """Scan all scenes under *modules_dir* and return the corpus dict.

    The returned dict has keys:
      - ``"scenes"``: list of per-scene records
      - ``"skipped"``: list of scene dirs that had no scene.xscene
      - ``"parse_errors"``: list of {scene_dir, error} for XML parse failures
      - ``"_terrain_grids"``: dict mapping "<module>/<scene>" to float32 ndarray
        (NOT serialised to JSON — consumed by save_corpus)
    """
    import multiprocessing as mp

    scenes: list[dict[str, Any]] = []
    skipped: list[str] = []
    parse_errors: list[dict[str, str]] = []
    terrain_grids: dict[str, Any] = {}

    # Collect work items
    work_items: list[tuple[str, str, str]] = []  # (xscene_path, module_name, scene_name)

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
            work_items.append((xscene_path, module_name, scene_name))

    # Process scenes (parallel via pool)
    if workers > 1:
        with mp.Pool(workers) as pool:
            results = pool.map(_scene_worker, work_items)
    else:
        results = [_scene_worker(item) for item in work_items]

    for record, grid, err_path, err_msg in results:
        if err_path is not None:
            parse_errors.append({"scene_dir": err_path, "error": err_msg})
        else:
            scenes.append(record)
            if grid is not None:
                key = record["terrain"]["terrain_grid_key"]
                terrain_grids[key] = grid

    return {
        "scenes": scenes,
        "skipped": skipped,
        "parse_errors": parse_errors,
        "_terrain_grids": terrain_grids,
    }


def save_corpus(
    corpus: dict[str, Any],
    path: str,
    *,
    terrain_npz_path: str | None = None,
) -> None:
    """Write *corpus* to *path* as JSON; write terrain grids to *terrain_npz_path*.

    If *terrain_npz_path* is None, it defaults to the same directory as *path*
    with the filename ``corpus_terrain.npz``.
    """
    import numpy as np

    if terrain_npz_path is None:
        terrain_npz_path = os.path.join(
            os.path.dirname(os.path.abspath(path)), "corpus_terrain.npz"
        )

    # Separate out the private terrain grids before JSON serialisation
    grids = corpus.pop("_terrain_grids", {})

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(corpus, fh, separators=(",", ":"))

    # Restore so the in-memory object stays usable
    corpus["_terrain_grids"] = grids

    if grids:
        np.savez_compressed(terrain_npz_path, **{k.replace("/", "__"): v for k, v in grids.items()})


def load_corpus(path: str) -> dict[str, Any]:
    """Load a corpus previously saved with :func:`save_corpus`."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_terrain_grids(npz_path: str) -> dict[str, Any]:
    """Load terrain grids from *npz_path* produced by :func:`save_corpus`.

    Returns a dict mapping ``"<module>/<scene>"`` to float32 ndarray.
    """
    import numpy as np
    npz = np.load(npz_path)
    return {k.replace("__", "/"): npz[k] for k in npz.files}
