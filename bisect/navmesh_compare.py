"""Compare generated scene navmesh vs native battle_terrain_a navmesh."""
from pathlib import Path

from blnav import rnm1
from blnav.nmg9 import NavMesh

HERE = Path(__file__).parent

for name in ("native", "generated"):
    payload = rnm1.read(str(HERE / name / "navmesh.bin"))
    nm = NavMesh.parse(payload)
    print(f"=== {name}: {nm.stats()}")
    faces = nm.faces
    # face attribute distributions
    from collections import Counter
    for attr in ("g3", "g5", "island", "material") if hasattr(faces[0], "material") else ():
        pass
    # generic: dump dataclass fields of face 0
    f0 = faces[0]
    print("  face0 fields:", {k: getattr(f0, k) for k in f0.__dataclass_fields__})
    for field in f0.__dataclass_fields__:
        sample = getattr(f0, field)
        if isinstance(sample, list):
            continue
        vals = Counter(getattr(f, field) for f in faces)
        if len(vals) <= 12:
            print(f"  {field}: {dict(vals.most_common(12))}")
    # vertex bounds
    import numpy as np
    vs = np.array(nm.vertices)
    print(f"  verts={len(vs)} x[{vs[:,0].min():.1f},{vs[:,0].max():.1f}] "
          f"y[{vs[:,1].min():.1f},{vs[:,1].max():.1f}] z[{vs[:,2].min():.1f},{vs[:,2].max():.1f}]")
