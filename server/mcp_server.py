"""MCP server: LLM-driven Bannerlord navmesh generation and editing.

Run:  python server/mcp_server.py            (stdio)
      fastmcp run server/mcp_server.py:mcp --transport http --port 8765
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastmcp import FastMCP

import server.state as state
from blnav import generate
from blnav.nmg9 import Face

mcp = FastMCP(
    "bannerlord-navmesh",
    instructions=(
        "Generate and edit Mount & Blade II: Bannerlord navigation meshes. "
        "Workflow: load_scene(scene_dir) -> inspect (scene_info, query_faces, "
        "sample_height) -> generate_navmesh or edit faces -> save_navmesh. "
        "Coordinates are world meters: X/Y ground plane, Z up."
    ),
)


def _scene_info() -> dict:
    sess = state.current()
    info: dict = {"scene_dir": sess.scene_dir, "dirty": sess.dirty}
    if sess.params:
        p = sess.params
        info["terrain"] = {
            "world_size_x": p.world_size_x,
            "world_size_y": p.world_size_y,
            "min_height": p.min_height,
            "max_height": p.max_height,
            "heightmap_shape": list(sess.heights.shape),
        }
    info["navmesh"] = sess.mesh.stats()
    return info


@mcp.tool
def load_scene(scene_dir: str) -> dict:
    """Load a Bannerlord scene directory (scene.xscene + terrain.bin + optional
    navmesh.bin). Returns terrain parameters and navmesh stats."""
    state.load_scene(scene_dir)
    return _scene_info()


@mcp.tool
def scene_info() -> dict:
    """Terrain parameters and current navmesh statistics for the loaded scene."""
    return _scene_info()


@mcp.tool
def sample_height(x: float, y: float) -> float:
    """Terrain surface height (world meters) at world position (x, y)."""
    return state.current().sample_height(x, y)


@mcp.tool
def query_faces(min_x: float, min_y: float, max_x: float, max_y: float, limit: int = 200) -> list[dict]:
    """List navmesh faces whose centroid lies in the world-space rectangle.
    Each entry: index, centroid, vertex positions, face_id (g3), group (g5)."""
    sess = state.current()
    out = []
    for i, f in enumerate(sess.mesh.faces):
        pts = [sess.mesh.vertices[v] for v in f.vertex_ids]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        if min_x <= cx <= max_x and min_y <= cy <= max_y:
            out.append({
                "index": i,
                "centroid": [round(cx, 2), round(cy, 2), round(sum(p[2] for p in pts) / len(pts), 2)],
                "vertices": [[round(c, 2) for c in p] for p in pts],
                "face_id": f.g3,
                "group": f.g5,
            })
            if len(out) >= limit:
                break
    return out


@mcp.tool
def generate_navmesh(
    cell_size: float = 4.0,
    max_slope_deg: float = 40.0,
    min_x: float | None = None,
    min_y: float | None = None,
    max_x: float | None = None,
    max_y: float | None = None,
    face_id: int = 0,
    group: int = -1,
    replace: bool = True,
) -> dict:
    """Generate a walkable navmesh from the scene terrain heightmap.
    Optional world-space region clip; replace=False appends to the current mesh
    (as a disconnected island). Returns resulting stats."""
    sess = state.current()
    if sess.heights is None:
        raise ValueError("scene has no terrain")
    region = None
    if None not in (min_x, min_y, max_x, max_y):
        region = (min_x, min_y, max_x, max_y)
    gen = generate.from_heightmap(
        sess.heights, sess.params.world_size_x, sess.params.world_size_y,
        cell_size=cell_size, max_slope_deg=max_slope_deg,
        face_id=face_id, group=group, region=region,
    )
    if replace:
        sess.mesh = gen
    else:
        base_v = len(sess.mesh.vertices)
        sess.mesh.vertices.extend(gen.vertices)
        for f in gen.faces:
            sess.mesh.faces.append(Face(
                [v + base_v for v in f.vertex_ids], [], f.g1, f.g2, f.g3, f.g4, f.g5, f.g6))
        sess.mesh.rebuild_edges()
    sess.dirty = True
    return sess.mesh.stats()


@mcp.tool
def add_face(vertices: list[list[float]], face_id: int = 0, group: int = -1) -> dict:
    """Add one polygon face (3-4 [x,y,z] world positions, counter-clockwise
    viewed from above). Vertices within 1cm of existing ones are reused."""
    sess = state.current()
    mesh = sess.mesh
    ids = []
    for p in vertices:
        for i, v in enumerate(mesh.vertices):
            if abs(v[0] - p[0]) < 0.01 and abs(v[1] - p[1]) < 0.01 and abs(v[2] - p[2]) < 0.01:
                ids.append(i)
                break
        else:
            ids.append(len(mesh.vertices))
            mesh.vertices.append((p[0], p[1], p[2]))
    mesh.faces.append(Face(ids, [], 2, 0, face_id, 0, group, 0))
    mesh.rebuild_edges()
    sess.dirty = True
    return {"face_index": len(mesh.faces) - 1, "vertex_ids": ids}


@mcp.tool
def delete_faces(face_indices: list[int]) -> dict:
    """Delete faces by index. Orphaned vertices are removed, edges rebuilt."""
    sess = state.current()
    mesh = sess.mesh
    kill = set(face_indices)
    mesh.faces = [f for i, f in enumerate(mesh.faces) if i not in kill]
    used = sorted({v for f in mesh.faces for v in f.vertex_ids})
    remap = {old: new for new, old in enumerate(used)}
    mesh.vertices = [mesh.vertices[i] for i in used]
    for f in mesh.faces:
        f.vertex_ids = [remap[v] for v in f.vertex_ids]
    mesh.rebuild_edges()
    sess.dirty = True
    return sess.mesh.stats()


@mcp.tool
def set_face_attributes(face_indices: list[int], face_id: int | None = None, group: int | None = None) -> int:
    """Set face_id (g3, used by SetAbilityOfFacesWithId to toggle faces at
    runtime) and/or group (g5) on the given faces. Returns count changed."""
    sess = state.current()
    n = 0
    for i in face_indices:
        f = sess.mesh.faces[i]
        if face_id is not None:
            f.g3 = face_id
        if group is not None:
            f.g5 = group
        n += 1
    sess.dirty = n > 0
    return n


@mcp.tool
def move_vertex(vertex_id: int, x: float, y: float, z: float) -> list[float]:
    """Move a navmesh vertex to a new world position."""
    sess = state.current()
    sess.mesh.vertices[vertex_id] = (x, y, z)
    sess.dirty = True
    return [x, y, z]


@mcp.tool
def snap_to_terrain(offset: float = 0.3) -> int:
    """Set every vertex Z to terrain height + offset. Returns vertex count."""
    sess = state.current()
    sess.mesh.vertices = [
        (x, y, sess.sample_height(x, y) + offset) for x, y, _ in sess.mesh.vertices
    ]
    sess.dirty = True
    return len(sess.mesh.vertices)


@mcp.tool
def save_navmesh(out_path: str | None = None) -> str:
    """Write the working navmesh as navmesh.bin (RNM1+LZ4). Defaults to the
    scene directory; the first save keeps a .bak of the original."""
    return state.current().save(out_path)


@mcp.tool
def export_obj(out_path: str) -> str:
    """Export the current navmesh as a Wavefront OBJ for external viewing."""
    sess = state.current()
    with open(out_path, "w") as fh:
        fh.write(sess.mesh.to_obj())
    return out_path


if __name__ == "__main__":
    mcp.run()
