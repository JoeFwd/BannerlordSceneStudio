"""Regenerate the dadg_gen_battle_test scene.

Heights: 769x769 float32 using index-based sine formula
    heights[i,j] = 50 + 10*sin(j/45)*cos(i/60)
where i=row, j=col (matching np.meshgrid with xx=cols, yy=rows).

Output: D:/SteamLibrary/steamapps/common/Mount & Blade II Bannerlord/
        Modules/DellarteDellaGuerraScenes/SceneObj/dadg_gen_battle_test/
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.compose import SceneBuilder

# --- Height formula (index-based, exactly as specified) ---
xx, yy = np.meshgrid(np.arange(769, dtype=np.float32), np.arange(769, dtype=np.float32))
heights = (50 + 10 * np.sin(xx / 45) * np.cos(yy / 60)).astype(np.float32)

# The formula gives heights in range ~40..~60 (sin/cos range covers -1..1 asymptotically).
# The API derives min/max from the actual heights array; xscene gets those values.
print(f"Height range: min={heights.min():.4f}, max={heights.max():.4f}")
assert heights.min() <= 40.01, f"min_height {heights.min():.4f} unexpectedly above 40"
assert heights.max() >= 59.99, f"max_height {heights.max():.4f} unexpectedly below 60"

# --- Build ---
out_dir = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\DellarteDellaGuerraScenes\SceneObj"
)

builder = SceneBuilder.new_battle(
    "dadg_gen_battle_test",
    heights,
    node_size=200.0,
)

# Preserve ShaderCache if present by building directly (build() uses makedirs exist_ok=True)
scene_dir = builder.build(out_dir)
print(f"Scene written to: {scene_dir}")

# Report written files
for p in sorted(Path(scene_dir).iterdir()):
    if p.is_file():
        print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
