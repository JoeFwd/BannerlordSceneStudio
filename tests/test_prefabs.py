"""Tests for blscene.prefabs — prefab catalog for Bannerlord v1.4 install."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blscene.prefabs import PrefabCatalog

GAME_DIR = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord"
GAME_NATIVE = GAME_DIR + r"\Modules\Native"


def test_native_prefab_count():
    """Native module alone should have well over 1000 top-level prefabs."""
    catalog = PrefabCatalog()
    catalog.scan([GAME_NATIVE])
    assert len(catalog.names()) > 1000, f"Expected >1000, got {len(catalog.names())}"


def test_strategic_archer_point_found_in_v12():
    """strategic_archer_point must be findable somewhere in the v1.4 install."""
    catalog = PrefabCatalog.scan_install(GAME_DIR)
    record = catalog.get("strategic_archer_point")
    assert record is not None, "strategic_archer_point not found in v1.4 install"
    print(f"\nstrategic_archer_point found in module: {record.module}, file: {record.source_file}")


def test_search():
    """search() returns only records whose name contains the substring."""
    catalog = PrefabCatalog()
    catalog.scan([GAME_NATIVE])
    results = catalog.search("strategic_archer")
    assert len(results) > 0, "search('strategic_archer') returned nothing"
    for r in results:
        assert "strategic_archer" in r.name.lower()


def test_record_fields():
    """PrefabRecord fields are populated for strategic_archer_point."""
    catalog = PrefabCatalog.scan_install(GAME_DIR)
    r = catalog.get("strategic_archer_point")
    assert r is not None
    # It has a StrategicArea script per manual inspection
    assert "StrategicArea" in r.scripts, f"scripts: {r.scripts}"
    assert r.has_meta_mesh


def test_json_roundtrip():
    """to_json / from_json preserves all records."""
    catalog = PrefabCatalog()
    catalog.scan([GAME_NATIVE])
    original_names = set(catalog.names())
    original_count = len(catalog.all_records())

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
        tmp_path = tmp.name

    try:
        catalog.to_json(tmp_path)
        restored = PrefabCatalog.from_json(tmp_path)
        assert set(restored.names()) == original_names
        assert len(restored.all_records()) == original_count
        # Spot-check a record
        r_orig = catalog.get("strategic_archer_point")
        r_rest = restored.get("strategic_archer_point")
        if r_orig is not None and r_rest is not None:
            assert r_orig.scripts == r_rest.scripts
            assert r_orig.module == r_rest.module
    finally:
        Path(tmp_path).unlink(missing_ok=True)
