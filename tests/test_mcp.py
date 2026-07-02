"""Exercise the MCP tools end-to-end in process (no transport)."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastmcp import Client

from server.mcp_server import mcp

SCENE = r"D:\SteamLibrary\steamapps\common\Mount & Blade II Bannerlord\Modules\SandBoxCore\SceneObj\empire_town_s"
TMP = Path(__file__).parent / "_tmp"


async def main():
    async with Client(mcp) as c:
        tools = await c.list_tools()
        print("tools:", sorted(t.name for t in tools))

        r = await c.call_tool("load_scene", {"scene_dir": SCENE})
        info = r.data
        print("scene_info:", json.dumps(info["terrain"]), "faces:", info["navmesh"]["faces"])

        h = (await c.call_tool("sample_height", {"x": 1000.0, "y": 1200.0})).data
        print("height @ (1000,1200):", h)

        fr = await c.call_tool("query_faces", {
            "min_x": 1000, "min_y": 1200, "max_x": 1020, "max_y": 1220, "limit": 3})
        faces = fr.structured_content["result"]
        print("query_faces sample:", json.dumps(faces[:1]))

        stats = (await c.call_tool("generate_navmesh", {
            "cell_size": 4.0, "max_slope_deg": 40.0,
            "min_x": 950, "min_y": 1150, "max_x": 1050, "max_y": 1250})).data
        print("generated:", stats)

        add = (await c.call_tool("add_face", {"vertices": [
            [950, 1150, h], [954, 1150, h], [954, 1154, h], [950, 1154, h]]})).data
        print("add_face:", add)

        n = (await c.call_tool("set_face_attributes", {
            "face_indices": [add["face_index"]], "face_id": 123})).data
        assert n == 1

        stats2 = (await c.call_tool("delete_faces", {"face_indices": [0, 1, 2]})).data
        assert stats2["faces"] == stats["faces"] + 1 - 3

        nv = (await c.call_tool("snap_to_terrain", {"offset": 0.3})).data
        print("snapped verts:", nv)

        out = (await c.call_tool("save_navmesh", {"out_path": str(TMP / "mcp_navmesh.bin")})).data
        obj = (await c.call_tool("export_obj", {"out_path": str(TMP / "mcp_navmesh.obj")})).data
        print("saved:", out, "obj:", obj)

        # verify saved file reloads
        r2 = (await c.call_tool("load_scene", {"scene_dir": SCENE})).data
        assert r2["navmesh"]["faces"] > 30000  # original untouched
        from blnav import nmg9, rnm1
        again = nmg9.NavMesh.parse(rnm1.read(str(TMP / "mcp_navmesh.bin")))
        assert len(again.faces) == stats2["faces"]
        print("MCP CHECKS PASSED")


asyncio.run(main())
