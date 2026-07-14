"""Prefab catalog for Mount & Blade II: Bannerlord.

Scans module Prefabs/*.xml files and indexes top-level <game_entity> elements.
Uses xml.etree.iterparse so large files (>1 MB) are streamed without holding
full trees in memory.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Iterator


@dataclass
class PrefabRecord:
    name: str
    module: str
    source_file: str
    tags: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    has_meta_mesh: bool = False
    has_physics: bool = False
    child_count: int = 0


def _parse_file(path: str, module: str) -> Iterator[PrefabRecord]:
    """Yield one PrefabRecord per top-level game_entity in *path*."""
    depth = 0
    # Stack-based streaming parse: we collect state as we enter/exit elements.
    # When we close a depth-1 game_entity we emit a record and clear state.
    in_top_entity = False
    record_name: str | None = None
    tags: list[str] = []
    scripts: list[str] = []
    has_meta_mesh = False
    has_physics = False
    child_count = 0

    context = ET.iterparse(path, events=("start", "end"))
    for event, elem in context:
        if event == "start":
            depth += 1
            if elem.tag == "game_entity" and depth == 2:
                in_top_entity = True
                record_name = elem.get("name", "")
                tags = []
                scripts = []
                has_meta_mesh = False
                has_physics = False
                child_count = 0
            elif in_top_entity:
                if elem.tag == "physics" and depth == 3:
                    has_physics = True
                elif elem.tag == "tag" and depth == 4:
                    n = elem.get("name")
                    if n:
                        tags.append(n)
                elif elem.tag == "script" and depth == 4:
                    n = elem.get("name")
                    if n:
                        scripts.append(n)
                elif elem.tag == "meta_mesh_component":
                    has_meta_mesh = True
                elif elem.tag == "game_entity" and depth == 3:
                    # direct child entity
                    child_count += 1
        else:  # end
            if elem.tag == "game_entity" and depth == 2 and in_top_entity:
                if record_name is not None:
                    yield PrefabRecord(
                        name=record_name,
                        module=module,
                        source_file=path,
                        tags=list(tags),
                        scripts=list(scripts),
                        has_meta_mesh=has_meta_mesh,
                        has_physics=has_physics,
                        child_count=child_count,
                    )
                in_top_entity = False
                record_name = None
                # Release the element from memory
                elem.clear()
            depth -= 1


class PrefabCatalog:
    """Catalog of Bannerlord prefab definitions across one or more modules."""

    def __init__(self) -> None:
        # Primary index: name -> most-recently-scanned record
        self._primary: dict[str, PrefabRecord] = {}
        # All records (preserves duplicates across modules)
        self._all: list[PrefabRecord] = []

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def scan(self, module_dirs: list[str]) -> None:
        """Scan a list of individual module folder paths."""
        for module_dir in module_dirs:
            module_name = os.path.basename(module_dir.rstrip("/\\"))
            prefabs_dir = os.path.join(module_dir, "Prefabs")
            if not os.path.isdir(prefabs_dir):
                continue
            for fname in sorted(os.listdir(prefabs_dir)):
                if not fname.lower().endswith(".xml"):
                    continue
                fpath = os.path.join(prefabs_dir, fname)
                try:
                    for record in _parse_file(fpath, module_name):
                        self._all.append(record)
                        self._primary[record.name] = record  # later wins
                except ET.ParseError:
                    pass  # skip malformed files

    @classmethod
    def scan_install(cls, game_dir: str) -> "PrefabCatalog":
        """Scan all Modules/*/Prefabs under *game_dir*."""
        catalog = cls()
        modules_dir = os.path.join(game_dir, "Modules")
        if not os.path.isdir(modules_dir):
            return catalog
        module_dirs = [
            os.path.join(modules_dir, m)
            for m in sorted(os.listdir(modules_dir))
            if os.path.isdir(os.path.join(modules_dir, m))
        ]
        catalog.scan(module_dirs)
        return catalog

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> PrefabRecord | None:
        """Return the primary record for *name* (last-scanned module wins)."""
        return self._primary.get(name)

    def search(self, substring: str) -> list[PrefabRecord]:
        """Return all primary records whose name contains *substring*."""
        sub = substring.lower()
        return [r for r in self._primary.values() if sub in r.name.lower()]

    def names(self) -> list[str]:
        """Return all primary prefab names."""
        return list(self._primary.keys())

    def all_records(self) -> list[PrefabRecord]:
        """Return every record including duplicates across modules."""
        return list(self._all)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self, path: str) -> None:
        """Save the full catalog (all records) to a JSON file."""
        data = [asdict(r) for r in self._all]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    @classmethod
    def from_json(cls, path: str) -> "PrefabCatalog":
        """Load a catalog previously saved with to_json."""
        catalog = cls()
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for d in data:
            r = PrefabRecord(**d)
            catalog._all.append(r)
            catalog._primary[r.name] = r  # last wins (same order as original scan)
        return catalog
