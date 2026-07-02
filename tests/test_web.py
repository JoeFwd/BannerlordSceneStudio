"""Smoke-test the web GUI API against a running server on :8770."""
import json
import urllib.request


def call(path, body=None):
    url = "http://127.0.0.1:8770" + path
    if body is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        ct = r.headers.get("Content-Type", "")
        data = r.read()
        return json.loads(data) if "json" in ct else data


html = call("/")
assert b"Bannerlord Navmesh Studio" in html
info = call("/api/info")
print("info:", info["navmesh"]["faces"], "faces; terrain", info.get("terrain"))
mesh = call("/api/mesh")
assert len(mesh["faces"]) == info["navmesh"]["faces"]
print("mesh json:", len(mesh["vertices"]) // 3, "verts,", len(mesh["faces"]), "faces")
terr = call("/api/terrain?max_dim=128")
assert terr["rows"] and len(terr["heights"]) == terr["rows"] * terr["cols"]
print("terrain json:", terr["rows"], "x", terr["cols"])
gen = call("/api/generate", {"cell_size": 4, "max_slope_deg": 40,
                             "min_x": 950, "min_y": 1150, "max_x": 1050, "max_y": 1250,
                             "replace": False})
print("after append-generate:", gen["navmesh"]["faces"], "faces; dirty:", gen["dirty"])
attrs = call("/api/set_attrs", {"indices": [0, 1], "face_id": 7})
assert attrs["changed"] == 2
d = call("/api/delete_faces", {"indices": [0]})
assert d["navmesh"]["faces"] == gen["navmesh"]["faces"] - 1
print("WEB API CHECKS PASSED")
