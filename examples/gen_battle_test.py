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

# --- Slope-based two-layer split ---
# node_size 200 over a 6-node grid = 1200 m across 769 samples ≈ 1.5625 m/sample.
# Slope (rise/run) = |grad(height)| / sample_spacing.  Where slope exceeds a
# threshold, paint the template's "base_rock" layer (index 1); the flat base is
# "first_material" (layer 0, the default).
#
# Template battle_terrain_a <layers>: [0]=first_material  [1]=base_rock  ...
LAYER_BASE = 0        # first_material
LAYER_ROCK = 1        # base_rock
sample_spacing = 200.0 * 6 / (769 - 1)   # metres per sample
gy, gx = np.gradient(heights)
slope = np.hypot(gx, gy) / sample_spacing  # rise/run
rock_thresh = 0.10                          # ~5.7 deg; picks the steeper faces
rock_w = (slope > rock_thresh).astype(np.float32)  # 1 where steep, else 0
frac_rock = float(rock_w.mean())
print(f"slope max={slope.max():.4f}  rock coverage={frac_rock*100:.1f}% of cells")
assert 0.02 < frac_rock < 0.98, f"rock coverage {frac_rock:.3f} degenerate; tune threshold"
layer_weights = {LAYER_ROCK: rock_w}   # layer 0 base is auto-filled as 1-rock

# --- Build ---
out_dir = (
    r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
    r"\Modules\DellarteDellaGuerraScenes\SceneObj"
)

builder = SceneBuilder.new_battle(
    "dadg_gen_battle_test",
    heights,
    node_size=200.0,
    layer_weights=layer_weights,
)

# Preserve ShaderCache if present by building directly (build() uses makedirs exist_ok=True)
scene_dir = builder.build(out_dir)
print(f"Scene written to: {scene_dir}")

# Report written files
for p in sorted(Path(scene_dir).iterdir()):
    if p.is_file():
        print(f"  {p.name}  ({p.stat().st_size:,} bytes)")
