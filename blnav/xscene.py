"""Minimal scene.xscene reader: terrain parameters needed to interpret
terrain.bin heightmaps in world units."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TerrainParams:
    node_dim_x: int
    node_dim_y: int
    node_size: float
    min_height: float
    max_height: float

    @property
    def world_size_x(self) -> float:
        return self.node_dim_x * self.node_size

    @property
    def world_size_y(self) -> float:
        return self.node_dim_y * self.node_size

    def decode_heights(self, grid):
        """uint16 grid -> float32 world heights."""
        return (
            grid.astype("float32") / 65535.0 * (self.max_height - self.min_height)
            + self.min_height
        )


_TERRAIN_RE = re.compile(r"<terrain\s[^>]*>")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def read_terrain_params(xscene_path: str) -> TerrainParams:
    # xscene files are multi-MB; scan for the single <terrain ...> element
    # instead of building a full XML tree.
    with open(xscene_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _TERRAIN_RE.search(line)
            if m:
                attrs = dict(_ATTR_RE.findall(m.group(0)))
                return TerrainParams(
                    node_dim_x=int(attrs["node_dimension_x"]),
                    node_dim_y=int(attrs["node_dimension_y"]),
                    node_size=float(attrs["node_size"]),
                    min_height=float(attrs["min_height"]),
                    max_height=float(attrs["max_height"]),
                )
    raise ValueError(f"{xscene_path}: no <terrain> element found")
