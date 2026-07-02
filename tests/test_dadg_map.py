"""Read-only round-trip of DADG's England Main_map navmesh (third sample).
Writes the re-encoded candidate into tests/_tmp only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blnav import nmg9, rnm1

SRC = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\DellarteDellaGuerraMap\SceneObj\Main_map\navmesh.bin"
OUT = Path(__file__).parent / "_tmp" / "dadg_main_map_navmesh_reencoded.bin"

payload = rnm1.read(SRC)
mesh = nmg9.NavMesh.parse(payload)
assert mesh.serialize() == payload
print(f"DADG Main_map: v={len(mesh.vertices):,} e={len(mesh.edges):,} f={len(mesh.faces):,} — byte-identical reserialize")
rnm1.write(str(OUT), payload)
assert rnm1.read(str(OUT)) == payload
print(f"re-encoded candidate written to {OUT} ({OUT.stat().st_size:,} B vs orig {Path(SRC).stat().st_size:,} B)")
print("DADG MAP CHECKS PASSED")
