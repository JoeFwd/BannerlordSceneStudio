"""Round-trip DADG's England Main_map navmesh and swap it in for live testing.

Backs up the original as navmesh.bin.orig once; writes our re-encoded file
(payload byte-identical, LZ4 stream ours). Run with 'restore' to undo.
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav import nmg9, rnm1

PATH = Path(r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraMap\SceneObj\Main_map\navmesh.bin")
BAK = PATH.with_suffix(".bin.orig")

if len(sys.argv) > 1 and sys.argv[1] == "restore":
    shutil.copy2(BAK, PATH)
    print(f"restored original from {BAK}")
    sys.exit(0)

payload = rnm1.read(str(PATH))
mesh = nmg9.NavMesh.parse(payload)
assert mesh.serialize() == payload, "reserialize mismatch"
print(f"DADG Main_map navmesh: v={len(mesh.vertices):,} e={len(mesh.edges):,} f={len(mesh.faces):,} — parse/serialize byte-identical")

if not BAK.exists():
    shutil.copy2(PATH, BAK)
    print(f"backed up original -> {BAK}")
rnm1.write(str(PATH), payload)
assert rnm1.read(str(PATH)) == payload
orig_size = BAK.stat().st_size
print(f"wrote re-encoded navmesh.bin ({PATH.stat().st_size:,} B vs orig {orig_size:,} B) — ready for live test")
