"""Navmesh g5 is a signed scene-level visibility bitmask, not an island ID."""
ALL_SCENE_LEVELS = -1
# Most common mask in the shipped SandBox Main_map (13,304 / 17,153 faces).
# Defined levels: base (1), level_1 (2), civilian (16); preserve upper bits.
NATIVE_CAMPAIGN_MASK = -109


def default_scene_level_mask(scene_dir: str) -> int:
    name = scene_dir.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return NATIVE_CAMPAIGN_MASK if name.lower() == "main_map" else ALL_SCENE_LEVELS
