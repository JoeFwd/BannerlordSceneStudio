"""Byte-surgical settlement repository (adapter).

The campaign map places settlements from ModuleData/settlements.xml (posX/posY).
Each settlement has a scene entity named with its settlement id. Regional
capsules can contain several settlement children and have their own transforms.

Moving a settlement therefore means:
  * settlements.xml: rewrite posX/posY (and shift gate_posX/gate_posY by the
    same delta) on that Settlement's opening tag, and
  * scene.xscene: convert that world-space delta through the inverse parent
    transform and move only the settlement child. Its gate and other descendants
    follow it, while sibling settlements and the regional capsule stay fixed.

Both writes are targeted byte-surgical edits — only the moved settlement's own
line/transform changes; every other byte (English content, navmesh, etc.) is
preserved verbatim. A byte-exact ``.bak_placement_<stamp>`` is written before
each file is modified.

This module owns all XML/scene I/O; the pure footprint/land rules live in
``placement.model``.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import time
import xml.etree.ElementTree as ET

import numpy as np

_LOC_RE = re.compile(r"(town|castle|village)_complex")
_NAME_LOC_RE = re.compile(r"^\{=[^}]*\}")


def settlements_path(scene_dir: str) -> str:
    """ModuleData/settlements.xml sits two levels up from SceneObj/<scene>/."""
    return os.path.normpath(
        os.path.join(scene_dir, "..", "..", "ModuleData", "settlements.xml")
    )


def _classify(settlement: ET.Element) -> str | None:
    loc = settlement.find("Locations")
    ct = loc.get("complex_template", "") if loc is not None else ""
    m = _LOC_RE.search(ct)
    return m.group(1) if m else None


def _display_name(raw: str | None) -> str:
    return _NAME_LOC_RE.sub("", raw or "").strip()


def load_settlements(scene_dir: str) -> list[dict]:
    """Parse every Settlement into a placement record (read-only).

    Returns [] when there is no settlements.xml (non-campaign scenes).
    dadg_sco_* settlements are flagged ``movable``; everything else is a
    read-only reference marker. Footprint radius is resolved later from the
    per-map config, not stored here.
    """
    path = settlements_path(scene_dir)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        root = ET.fromstring(fh.read())
    out: list[dict] = []
    for s in root.findall(".//Settlement"):
        sid = s.get("id")
        if not sid:
            continue
        px, py = s.get("posX"), s.get("posY")
        if px is None or py is None:
            continue
        out.append({
            "id": sid,
            "name": _display_name(s.get("name")) or sid,
            "x": float(px),
            "y": float(py),
            "type": _classify(s),
            "movable": sid.startswith("dadg_sco_"),
        })
    return out


# ---------------------------------------------------------------------------
# Saving (targeted byte-surgical edits)
# ---------------------------------------------------------------------------

def _backup(path: str, data: bytes) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_placement_{stamp}"
    with open(bak, "wb") as fh:
        fh.write(data)
    with open(bak, "rb") as fh:
        assert hashlib.md5(fh.read()).hexdigest() == hashlib.md5(data).hexdigest()
    return bak


def _sub_attr(tag: str, attr: str, value: str) -> str:
    """Replace attr="..." inside a single opening tag string."""
    new, n = re.subn(rf'({re.escape(attr)}=")[^"]*(")', rf"\g<1>{value}\g<2>", tag, count=1)
    if n != 1:
        raise ValueError(f"attribute {attr} not found")
    return new


def apply_moves_settlements(path: str, moves: dict[str, tuple[float, float]]) -> tuple[bytes, int]:
    """Rewrite posX/posY (+ gate by delta) for each moved id. Returns (new_bytes, changed)."""
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    changed = 0
    for sid, (nx, ny) in moves.items():
        pat = re.compile(rf'<Settlement id="{re.escape(sid)}"[^>]*>')
        m = pat.search(text)
        if not m:
            raise ValueError(f"settlement {sid} not found in settlements.xml")
        tag = m.group(0)
        ox = float(re.search(r'posX="([^"]*)"', tag).group(1))
        oy = float(re.search(r'posY="([^"]*)"', tag).group(1))
        dx, dy = nx - ox, ny - oy
        new_tag = _sub_attr(tag, "posX", f"{nx:.3f}")
        new_tag = _sub_attr(new_tag, "posY", f"{ny:.3f}")
        gx = re.search(r'gate_posX="([^"]*)"', new_tag)
        gy = re.search(r'gate_posY="([^"]*)"', new_tag)
        if gx:
            new_tag = _sub_attr(new_tag, "gate_posX", f"{float(gx.group(1)) + dx:.3f}")
        if gy:
            new_tag = _sub_attr(new_tag, "gate_posY", f"{float(gy.group(1)) + dy:.3f}")
        text = text[:m.start()] + new_tag + text[m.end():]
        changed += 1
    return text.encode("utf-8"), changed


def _entity_transform(entity: ET.Element) -> np.ndarray:
    """Bannerlord local transform: Rz @ Ry @ Rx @ scale, then translation."""
    t = entity.find("transform")
    matrix = np.eye(4)
    if t is None:
        return matrix
    x, y, z = (float(v) for v in t.get("rotation_euler", "0,0,0").split(","))
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = np.array(((1, 0, 0), (0, cx, -sx), (0, sx, cx)))
    ry = np.array(((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)))
    rz = np.array(((cz, -sz, 0), (sz, cz, 0), (0, 0, 1)))
    scale = np.array([float(v) for v in t.get("scale", "1,1,1").split(",")])
    matrix[:3, :3] = rz @ ry @ rx @ np.diag(scale)
    matrix[:3, 3] = [float(v) for v in t.get("position", "0,0,0").split(",")]
    return matrix


def apply_moves_scene(path: str, moves: dict[str, tuple[float, float]]) -> tuple[bytes, int]:
    """Move each settlement entity by a world-space delta under its actual parents.

    Here ``moves`` maps id -> (dx, dy) already resolved to deltas.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    text = data.decode("utf-8")
    root = ET.fromstring(data)
    parents = {child: parent for parent in root.iter() for child in parent}
    entities = {}
    for entity in root.iter("game_entity"):
        sid = entity.get("name")
        if sid in moves:
            if sid in entities:
                raise ValueError(f"duplicate scene entity for settlement {sid}")
            entities[sid] = entity
    missing = set(moves) - set(entities)
    if missing:
        raise ValueError(f"settlement scene entities not found: {', '.join(sorted(missing))}")
    changed = 0
    for sid, (dx, dy) in moves.items():
        entity = entities[sid]
        chain, cursor = [], parents.get(entity)
        while cursor is not None:
            if cursor.tag == "game_entity":
                chain.append(cursor)
            cursor = parents.get(cursor)
        parent_world = np.eye(4)
        for ancestor in reversed(chain):
            parent_world = parent_world @ _entity_transform(ancestor)
        local_delta = np.linalg.solve(parent_world[:3, :3], (dx, dy, 0.0))
        transform = entity.find("transform")
        if transform is None or transform.get("position") is None:
            raise ValueError(f"settlement {sid} has no scene position")
        position = np.array([float(v) for v in transform.get("position").split(",")]) + local_delta
        rx = re.compile(rf'(<game_entity\b(?=[^>]*\bname="{re.escape(sid)}")[^>]*>'
                        r'(?:(?!<game_entity\b|</game_entity>|<children\b).)*?)'
                        r'(<transform\b[^>]*>)', re.DOTALL)
        m = rx.search(text)
        if not m:
            raise ValueError(f"cannot locate settlement {sid} transform for surgical update")
        new_transform = _sub_attr(m.group(2), "position", "%.6f, %.6f, %.6f" % tuple(position))
        text = text[:m.start()] + m.group(1) + new_transform + text[m.end():]
        changed += 1
    return text.encode("utf-8"), changed


def save_moves(scene_dir: str, moves: dict[str, tuple[float, float]]) -> dict:
    """Persist staged moves to settlements.xml + scene.xscene with backups.

    ``moves`` maps settlement id -> new (x, y). Deltas for the scene entity are
    computed from the current on-disk posX/posY.
    """
    if not moves:
        return {"changed": 0, "backups": []}

    set_path = settlements_path(scene_dir)
    scene_path = os.path.join(scene_dir, "scene.xscene")

    # Resolve deltas from current on-disk positions before rewriting.
    with open(set_path, encoding="utf-8", newline="") as fh:
        set_text = fh.read()
    deltas: dict[str, tuple[float, float]] = {}
    for sid, (nx, ny) in moves.items():
        tag = re.search(rf'<Settlement id="{re.escape(sid)}"[^>]*>', set_text)
        if not tag:
            raise ValueError(f"settlement {sid} not found")
        ox = float(re.search(r'posX="([^"]*)"', tag.group(0)).group(1))
        oy = float(re.search(r'posY="([^"]*)"', tag.group(0)).group(1))
        deltas[sid] = (nx - ox, ny - oy)

    set_bytes_old = set_text.encode("utf-8")
    new_set, n_set = apply_moves_settlements(set_path, moves)

    with open(scene_path, "rb") as fh:
        scene_bytes_old = fh.read()
    new_scene, n_scene = apply_moves_scene(scene_path, deltas)

    backups = [_backup(set_path, set_bytes_old), _backup(scene_path, scene_bytes_old)]
    with open(set_path, "wb") as fh:
        fh.write(new_set)
    with open(scene_path, "wb") as fh:
        fh.write(new_scene)

    return {
        "changed": len(moves),
        "settlements_updated": n_set,
        "capsules_updated": n_scene,
        "backups": [os.path.basename(b) for b in backups],
    }
