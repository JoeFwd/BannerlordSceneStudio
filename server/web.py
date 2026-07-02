"""Web GUI for viewing/editing Bannerlord navmeshes.

Run:  python server/web.py [scene_dir]     then open http://127.0.0.1:8770
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import subprocess

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import server.state as state
from blnav import generate
from blnav.nmg9 import Face

app = FastAPI(title="bannerlord-navmesh-studio")
STATIC = Path(__file__).parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


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


@app.get("/api/terrain")
def api_terrain(max_dim: int = 256):
    sess = _sess()
    if sess.heights is None:
        return {"grid": None}
    h = sess.heights
    step = max(1, int(np.ceil(max(h.shape) / max_dim)))
    g = h[::step, ::step]
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
    return {"changed": len(req.indices)}


class SaveReq(BaseModel):
    out_path: str | None = None


@app.post("/api/save")
def api_save(req: SaveReq):
    return {"path": _sess().save(req.out_path)}


if __name__ == "__main__":
    import uvicorn

    if len(sys.argv) > 1:
        state.load_scene(sys.argv[1])
    uvicorn.run(app, host="127.0.0.1", port=8770)
