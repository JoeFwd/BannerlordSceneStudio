"""Provenance / audit-trail support for the blscene scene composer.

Every :class:`blscene.compose.SceneBuilder` carries a :class:`ProvenanceLog`
that accumulates records as the builder is configured.  ``build()`` calls
:func:`write_provenance` to emit two files alongside ``scene.xscene``:

* ``provenance.json`` — machine-readable list of records (UTF-8, no BOM).
* ``provenance.md``  — short human-readable rendering with a one-line reuse
  summary at the top.

Schema (provenance.json root object)::

    {
      "tool": "blscene",
      "tool_commit": "<git sha or null>",
      "generated_utc": "<ISO-8601 timestamp>",
      "scene_name": "<name>",
      "generator": {          // optional, from provenance_note / constructor
        "script": "...",
        "seed": 42,
        ...
      },
      "sources": [
        {
          "role": "xscene_skeleton|terrain|navmesh|flora|atmosphere|references|entities|terrain_patch|flora_transplant",
          "source": "<module/scene path string or 'GENERATED'>",
          "detail": "<human note>",
          "count": <int or null>,
          "verbatim": <bool or null>   // true=byte-identical copy, false=modified, null=generated
        },
        ...
      ],
      "file_origins": {
        "<filename>": {
          "origin": "COPIED|MODIFIED|GENERATED",
          "source_path": "<abs path or null>",
          "sha256_match": <bool or null>
        },
        ...
      },
      "reuse_summary": "<one-line text>"
    }
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_commit(repo_dir: str | None = None) -> str | None:
    """Return the HEAD SHA of the repo at *repo_dir* (or this file's repo)."""
    if repo_dir is None:
        repo_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or None
    except Exception:
        return None


def _sha256(path: str) -> str | None:
    """Return hex SHA-256 of *path*, or None if the file does not exist."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------
# ProvenanceLog
# ---------------------------------------------------------------------------

class ProvenanceLog:
    """Accumulates provenance records for a single scene build.

    Instantiated by :class:`blscene.compose.SceneBuilder`; populated
    automatically by the builder and by explicit :meth:`note` calls from
    generator scripts.
    """

    def __init__(self, scene_name: str, generator_meta: dict[str, Any] | None = None) -> None:
        self.scene_name = scene_name
        self.generator_meta: dict[str, Any] = dict(generator_meta) if generator_meta else {}
        self.sources: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Record accumulation
    # ------------------------------------------------------------------

    def record(
        self,
        role: str,
        source: str,
        *,
        detail: str = "",
        count: int | None = None,
        verbatim: bool | None = None,
    ) -> None:
        """Append a source record.

        Args:
            role: semantic role, e.g. ``"terrain"``, ``"entities"``, ``"xscene_skeleton"``.
            source: provenance string — a ``"module/scene"`` path or ``"GENERATED"``.
            detail: optional human-readable note (what changed, what was kept, etc.).
            count: optional item count (entity count, flora record count, …).
            verbatim: True = byte-identical copy, False = modified copy, None = generated.
        """
        self.sources.append({
            "role": role,
            "source": source,
            "detail": detail,
            "count": count,
            "verbatim": verbatim,
        })

    def note(self, key: str, value: Any) -> None:
        """Store a free-form generator metadata entry (script name, seed, …)."""
        self.generator_meta[key] = value

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def _reuse_summary(self, file_origins: dict[str, dict]) -> str:
        """Compose a one-line plain-English reuse summary."""
        parts: list[str] = []
        for fname, info in file_origins.items():
            stem = fname.split(".")[0]
            origin = info.get("origin", "")
            src = info.get("source_path") or ""
            src_leaf = os.path.basename(os.path.dirname(src)) if src else ""
            if origin == "COPIED":
                parts.append(f"{stem} COPIED from {src_leaf}")
            elif origin == "MODIFIED":
                parts.append(f"{stem} MODIFIED from {src_leaf}")
            elif origin == "GENERATED":
                parts.append(f"{stem} GENERATED")
        return " / ".join(parts) if parts else "no output files recorded"

    def to_dict(self, file_origins: dict[str, dict]) -> dict[str, Any]:
        reuse = self._reuse_summary(file_origins)
        return {
            "tool": "blscene",
            "tool_commit": _git_commit(),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "scene_name": self.scene_name,
            "generator": self.generator_meta or None,
            "sources": self.sources,
            "file_origins": file_origins,
            "reuse_summary": reuse,
        }

    def to_json(self, file_origins: dict[str, dict]) -> str:
        return json.dumps(self.to_dict(file_origins), indent=2, ensure_ascii=False)

    def to_markdown(self, file_origins: dict[str, dict]) -> str:
        d = self.to_dict(file_origins)
        lines: list[str] = []
        lines.append(f"# Provenance: {d['scene_name']}")
        lines.append("")
        lines.append(f"**Reuse:** {d['reuse_summary']}")
        lines.append("")
        lines.append(f"- **Tool:** {d['tool']}  commit `{d['tool_commit'] or 'unknown'}`")
        lines.append(f"- **Generated (UTC):** {d['generated_utc']}")
        if d["generator"]:
            gen_str = "  ".join(f"`{k}={v}`" for k, v in d["generator"].items())
            lines.append(f"- **Generator:** {gen_str}")
        lines.append("")
        lines.append("## Output files")
        lines.append("")
        lines.append("| File | Origin | Source |")
        lines.append("|------|--------|--------|")
        for fname, info in d["file_origins"].items():
            origin = info.get("origin", "?")
            src = info.get("source_path") or "—"
            sha_ok = info.get("sha256_match")
            sha_note = ""
            if sha_ok is True:
                sha_note = " ✓ hash match"
            elif sha_ok is False:
                sha_note = " ✗ hash differs"
            lines.append(f"| `{fname}` | {origin} | `{src}`{sha_note} |")
        lines.append("")
        lines.append("## Source records")
        lines.append("")
        for rec in d["sources"]:
            role = rec["role"]
            src = rec["source"]
            detail = rec.get("detail") or ""
            count = rec.get("count")
            verbatim = rec.get("verbatim")
            verbatim_str = ""
            if verbatim is True:
                verbatim_str = " (verbatim)"
            elif verbatim is False:
                verbatim_str = " (modified)"
            count_str = f" × {count}" if count is not None else ""
            lines.append(f"- **{role}**: `{src}`{verbatim_str}{count_str}"
                         + (f" — {detail}" if detail else ""))
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# File-origin determination
# ---------------------------------------------------------------------------

def compute_file_origins(
    scene_dir: str,
    source_dir: str | None,
    terrain_dirty: bool,
    filenames: list[str],
    navmesh_verbatim: bool = False,
) -> dict[str, dict]:
    """Build the file_origins mapping for all written files.

    For each file in *filenames*:
      * If *terrain_dirty* is True and the file is ``terrain.bin`` or
        ``navmesh.bin``, it is GENERATED — unless *navmesh_verbatim* is True,
        in which case ``navmesh.bin`` is copied from source and evaluated by
        SHA-256 like any other copied file.
      * ``scene.xscene`` is always MODIFIED (scene name attribute is rewritten).
      * Otherwise, if *source_dir* is set and the source file exists, compute
        SHA-256 of both; if they match → COPIED, else → MODIFIED.
      * If no source, treat as GENERATED.
    """
    origins: dict[str, dict] = {}
    for fname in filenames:
        dst_path = os.path.join(scene_dir, fname)
        generated_pair = ("terrain.bin",) if navmesh_verbatim else ("terrain.bin", "navmesh.bin")
        if terrain_dirty and fname in generated_pair:
            origins[fname] = {"origin": "GENERATED", "source_path": None, "sha256_match": None}
            continue
        if fname == "scene.xscene":
            src_path = os.path.join(source_dir, fname) if source_dir else None
            origins[fname] = {
                "origin": "MODIFIED",
                "source_path": src_path,
                "sha256_match": None,
            }
            continue
        if source_dir:
            src_path = os.path.join(source_dir, fname)
            if os.path.exists(src_path):
                dst_sha = _sha256(dst_path)
                src_sha = _sha256(src_path)
                match = (dst_sha is not None and src_sha is not None and dst_sha == src_sha)
                origins[fname] = {
                    "origin": "COPIED" if match else "MODIFIED",
                    "source_path": src_path,
                    "sha256_match": match,
                }
                continue
        origins[fname] = {"origin": "GENERATED", "source_path": None, "sha256_match": None}
    return origins


# ---------------------------------------------------------------------------
# Write provenance files
# ---------------------------------------------------------------------------

PROVENANCE_FILES = ("provenance.json", "provenance.md")


def write_provenance(
    log: ProvenanceLog,
    scene_dir: str,
    source_dir: str | None,
    terrain_dirty: bool,
    written_files: list[str],
    navmesh_verbatim: bool = False,
) -> None:
    """Write ``provenance.json`` and ``provenance.md`` into *scene_dir*.

    Args:
        log: the accumulated :class:`ProvenanceLog`.
        scene_dir: the output SceneObj folder just written by ``build()``.
        source_dir: the template/donor folder, or None.
        terrain_dirty: True when terrain/navmesh were generated from heights.
        written_files: list of filenames actually written (e.g. ``["scene.xscene",
            "terrain.bin", "flora.bin", "atmosphere.xml", "references.txt",
            "navmesh.bin"]``).
    """
    origins = compute_file_origins(
        scene_dir, source_dir, terrain_dirty, written_files,
        navmesh_verbatim=navmesh_verbatim,
    )
    json_path = os.path.join(scene_dir, "provenance.json")
    md_path = os.path.join(scene_dir, "provenance.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        fh.write(log.to_json(origins))
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(log.to_markdown(origins))
