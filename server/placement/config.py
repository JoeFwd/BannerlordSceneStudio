"""Per-map footprint configuration, persisted as a sidecar JSON next to the scene.

The file ``navmesh_studio.placement.json`` lives in the scene directory (e.g.
``SceneObj/Main_map/``). It is *not* game data — Bannerlord never reads it — so
it is written directly, without the byte-surgical backup dance the game XML gets.
Absent file => defaults from :data:`model.DEFAULT_TYPE_RADIUS`.
"""
from __future__ import annotations

import json
import os

from server.placement.model import DEFAULT_TYPE_RADIUS, Footprint

CONFIG_NAME = "navmesh_studio.placement.json"


def config_path(scene_dir: str) -> str:
    return os.path.join(scene_dir, CONFIG_NAME)


def load(scene_dir: str) -> Footprint:
    path = config_path(scene_dir)
    if not os.path.exists(path):
        return Footprint()
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    type_radius = dict(DEFAULT_TYPE_RADIUS)
    for k, v in (data.get("type_radius") or {}).items():
        type_radius[k] = None if v is None else float(v)
    custom = {k: float(v) for k, v in (data.get("custom_radius") or {}).items()}
    return Footprint(type_radius=type_radius, custom_radius=custom)


def save(scene_dir: str, footprint: Footprint) -> str:
    path = config_path(scene_dir)
    payload = {
        "type_radius": footprint.type_radius,
        "custom_radius": footprint.custom_radius,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return path
