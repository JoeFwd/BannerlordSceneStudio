"""Web GUI for viewing/editing Bannerlord navmeshes.

Run:  python server/web.py [scene_dir]     then open http://127.0.0.1:8770
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mimetypes
import os
import subprocess

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure ES module scripts are served with a JavaScript MIME type (some Windows
# registries map .js to text/plain, which browsers reject for `type="module"`).
mimetypes.add_type("application/javascript", ".js")

import server.state as state
from server import navmesh_diagnostics as diagnostics
from server.terrain_preview import resample_heights
from server.placement import config as placement_config
from server.placement import model as placement_model
from server.placement import repository as placement_repo
from blnav import generate
from blnav.nmg9 import Face

app = FastAPI(title="bannerlord-navmesh-studio")
STATIC = Path(__file__).parent / "static"
DIST = STATIC / "dist"   # built Vite (React + R3F) front-end, when present


@app.get("/")
def index():
    return FileResponse(DIST / "index.html")


# Vite emits hashed bundles under dist/assets.
app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


_PICKER = (
    "import sys, tkinter as tk\n"
    "from tkinter import filedialog\n"
    "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)\n"
    "print(filedialog.askdirectory(title='Select Bannerlord scene directory',"
    " initialdir=sys.argv[1]) or '')\n"
)

_MODULES_DIR = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules"


@app.get("/api/browse")
def api_browse():
    """Open a native folder picker on the machine running the server."""
    initial = _MODULES_DIR if os.path.isdir(_MODULES_DIR) else os.path.expanduser("~")
    try:
        if state._current is not None:
            initial = os.path.dirname(state._current.scene_dir)
    except Exception:
        pass
    r = subprocess.run(
        [sys.executable, "-c", _PICKER, initial],
        capture_output=True, text=True, timeout=600,
    )
    path = r.stdout.strip()
    return {"path": path or None}


class LoadReq(BaseModel):
    scene_dir: str


@app.post("/api/load")
def api_load(req: LoadReq):
    sess = state.load_scene(req.scene_dir)
    return _info(sess)


def _info(sess):
    info = {"scene_dir": sess.scene_dir, "dirty": sess.dirty, "navmesh": sess.mesh.stats()}
    if sess.params:
        info["terrain"] = {
            "world_size_x": sess.params.world_size_x,
            "world_size_y": sess.params.world_size_y,
            "min_height": sess.params.min_height,
            "max_height": sess.params.max_height,
        }
    return info


@app.get("/api/info")
def api_info():
    return _info(_sess())


def _sess():
    try:
        return state.current()
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@app.get("/api/mesh")
def api_mesh():
    sess = _sess()
    return {
        "vertices": [c for v in sess.mesh.vertices for c in v],
        "faces": [f.vertex_ids for f in sess.mesh.faces],
        "face_id": [f.g3 for f in sess.mesh.faces],
        "group": [f.g5 for f in sess.mesh.faces],
    }


@app.get("/api/navmesh/inspect-region")
def api_inspect_region(min_x: float, min_y: float, max_x: float, max_y: float,
                       limit: int = 200):
    try:
        return diagnostics.inspect_region(_sess(), min_x, min_y, max_x, max_y, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/navmesh/probe-point")
def api_probe_point(x: float, y: float):
    return diagnostics.probe_point(_sess(), x, y)


@app.get("/api/terrain")
def api_terrain(max_dim: int = 256):
    sess = _sess()
    if sess.heights is None:
        return {"grid": None}
    try:
        g = resample_heights(sess.heights, max_dim)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        "rows": g.shape[0],
        "cols": g.shape[1],
        "world_size_x": sess.params.world_size_x,
        "world_size_y": sess.params.world_size_y,
        "heights": np.round(g.astype(float), 2).flatten().tolist(),
    }


class GenReq(BaseModel):
    cell_size: float = 4.0
    max_slope_deg: float = 40.0
    min_x: float | None = None
    min_y: float | None = None
    max_x: float | None = None
    max_y: float | None = None
    face_id: int = 0
    group: int = -1
    replace: bool = True


@app.post("/api/generate")
def api_generate(req: GenReq):
    sess = _sess()
    if sess.heights is None:
        raise HTTPException(400, "scene has no terrain")
    region = None
    if None not in (req.min_x, req.min_y, req.max_x, req.max_y):
        region = (req.min_x, req.min_y, req.max_x, req.max_y)
    gen = generate.from_heightmap(
        sess.heights, sess.params.world_size_x, sess.params.world_size_y,
        cell_size=req.cell_size, max_slope_deg=req.max_slope_deg,
        face_id=req.face_id, group=req.group, region=region,
    )
    if req.replace:
        sess.mesh = gen
    else:
        base = len(sess.mesh.vertices)
        sess.mesh.vertices.extend(gen.vertices)
        for f in gen.faces:
            sess.mesh.faces.append(Face([v + base for v in f.vertex_ids], [],
                                        f.g1, f.g2, f.g3, f.g4, f.g5, f.g6))
        sess.mesh.rebuild_edges()
    sess.dirty = True
    sess.land_oracle = None
    return _info(sess)


class FacesReq(BaseModel):
    indices: list[int]
    face_id: int | None = None
    group: int | None = None


@app.post("/api/delete_faces")
def api_delete(req: FacesReq):
    sess = _sess()
    kill = set(req.indices)
    mesh = sess.mesh
    mesh.faces = [f for i, f in enumerate(mesh.faces) if i not in kill]
    used = sorted({v for f in mesh.faces for v in f.vertex_ids})
    remap = {old: new for new, old in enumerate(used)}
    mesh.vertices = [mesh.vertices[i] for i in used]
    for f in mesh.faces:
        f.vertex_ids = [remap[v] for v in f.vertex_ids]
    mesh.rebuild_edges()
    sess.dirty = True
    sess.land_oracle = None
    return _info(sess)


@app.post("/api/set_attrs")
def api_set_attrs(req: FacesReq):
    sess = _sess()
    for i in req.indices:
        if req.face_id is not None:
            sess.mesh.faces[i].g3 = req.face_id
        if req.group is not None:
            sess.mesh.faces[i].g5 = req.group
    sess.dirty = True
    sess.land_oracle = None
    return {"changed": len(req.indices)}


class SaveReq(BaseModel):
    out_path: str | None = None


@app.post("/api/save")
def api_save(req: SaveReq):
    return {"path": _sess().save(req.out_path)}


# ---------------------------------------------------------------------------
# Settlement placement layer (v1: placement only)
# ---------------------------------------------------------------------------

WATER_LEVEL = 10.0


def _settlements(sess) -> list:
    if sess.settlements is None:
        sess.settlements = placement_repo.load_settlements(sess.scene_dir)
    return sess.settlements


def _footprint(sess):
    if sess.footprint is None:
        sess.footprint = placement_config.load(sess.scene_dir)
    return sess.footprint


def _land_oracle(sess):
    """Navmesh land/water oracle (rivers + lakes + sea via face terrain type)."""
    if sess.land_oracle is None and sess.mesh.faces:
        sess.land_oracle = placement_model.LandOracle(
            [(v[0], v[1]) for v in sess.mesh.vertices],
            [(f.vertex_ids, f.g3) for f in sess.mesh.faces],
        )
    return sess.land_oracle


def _sample_on_land(sess, oracle, x: float, y: float) -> bool:
    """One footprint-sample land verdict: dry ground that is not a water face.

    Water = below sea level (heightmap) OR sitting on a navmesh water face
    (river / lake / sea). Dry terrain with no navmesh carved yet still counts as
    land, so un-navmeshed dry ground is not falsely flagged.
    """
    h = sess.sample_height(x, y) if sess.heights is not None else WATER_LEVEL + 1.0
    if not placement_model.is_on_land(h, WATER_LEVEL):
        return False
    if oracle is not None and oracle.over_water_face(x, y):
        return False
    return True


def _enrich(sess, rec: dict) -> dict:
    """Attach live position (staged move if any), height, radius and the
    zone-based land verdict.

    A settlement is validly placed when *part* of its footprint zone is on land;
    ``land_fraction`` (share of the disc on land) drives fully-land / partly /
    fully-water in the UI. Rivers and lakes count as water via the navmesh
    terrain type, not just sea level. Villages (no zone) reduce to a point test.
    """
    x, y = sess.entity_moves.get(rec["id"], (rec["x"], rec["y"]))
    h = sess.sample_height(x, y) if sess.heights is not None else WATER_LEVEL
    radius = _footprint(sess).radius_for(rec["id"], rec["type"])
    oracle = _land_oracle(sess)
    pts = placement_model.disc_samples(x, y, radius)
    land_fraction = sum(_sample_on_land(sess, oracle, px, py) for px, py in pts) / len(pts)
    return {
        **rec,
        "x": x,
        "y": y,
        "height": round(h, 3),
        "land_fraction": round(land_fraction, 3),
        "on_land": land_fraction > 0.0,   # partial land still counts as valid
        "moved": rec["id"] in sess.entity_moves,
        "radius": radius,
    }


@app.get("/api/entities")
def api_entities():
    sess = _sess()
    recs = _settlements(sess)
    fp = _footprint(sess)
    return {
        "water_level": WATER_LEVEL,
        "type_radius": fp.type_radius,
        "settlements": [_enrich(sess, r) for r in recs],
        "moved": len(sess.entity_moves),
    }


class MoveReq(BaseModel):
    id: str
    x: float
    y: float


@app.post("/api/move_entity")
def api_move_entity(req: MoveReq):
    sess = _sess()
    rec = next((r for r in _settlements(sess) if r["id"] == req.id), None)
    if rec is None:
        raise HTTPException(404, f"unknown settlement {req.id}")
    if not rec["movable"]:
        raise HTTPException(400, f"{req.id} is a read-only reference settlement")
    sess.entity_moves[req.id] = (req.x, req.y)
    return _enrich(sess, rec)


@app.post("/api/reset_moves")
def api_reset_moves():
    sess = _sess()
    n = len(sess.entity_moves)
    sess.entity_moves.clear()
    return {"cleared": n}


@app.post("/api/save_entities")
def api_save_entities():
    sess = _sess()
    result = placement_repo.save_moves(sess.scene_dir, dict(sess.entity_moves))
    # Reflect the saved positions as the new baseline and clear staged moves.
    for r in _settlements(sess):
        if r["id"] in sess.entity_moves:
            r["x"], r["y"] = sess.entity_moves[r["id"]]
    sess.entity_moves.clear()
    return result


class TypeRadiusReq(BaseModel):
    type_radius: dict[str, float | None]


@app.post("/api/set_type_radius")
def api_set_type_radius(req: TypeRadiusReq):
    """Update per-map default footprint radii (e.g. {"town": 9.0}). Persisted."""
    sess = _sess()
    fp = _footprint(sess)
    for typ, radius in req.type_radius.items():
        fp.type_radius[typ] = radius
    placement_config.save(sess.scene_dir, fp)
    return {"type_radius": fp.type_radius}


class CustomRadiusReq(BaseModel):
    id: str
    radius: float | None = None


@app.post("/api/set_custom_radius")
def api_set_custom_radius(req: CustomRadiusReq):
    """Override (radius set) or clear (radius null) one settlement's radius."""
    sess = _sess()
    rec = next((r for r in _settlements(sess) if r["id"] == req.id), None)
    if rec is None:
        raise HTTPException(404, f"unknown settlement {req.id}")
    fp = _footprint(sess)
    if req.radius is None:
        fp.custom_radius.pop(req.id, None)
    else:
        fp.custom_radius[req.id] = req.radius
    placement_config.save(sess.scene_dir, fp)
    return _enrich(sess, rec)


if __name__ == "__main__":
    import uvicorn

    if len(sys.argv) > 1:
        state.load_scene(sys.argv[1])
    uvicorn.run(app, host="127.0.0.1", port=8770)
