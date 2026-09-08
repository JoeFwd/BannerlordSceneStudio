# Bannerlord Navmesh Studio

Read, edit, **generate** and write Mount & Blade II: Bannerlord navigation meshes
(`navmesh.bin`), with a web GUI viewer and an MCP server so an LLM can build a
navmesh from a scene (`scene.xscene` + `terrain.bin`).

## File formats (reverse-engineered, fully decoded)

### navmesh.bin — `RNM1` container

| offset | type | meaning |
|--------|------|---------|
| 0x00 | `'RNM1'` | magic |
| 0x04 | u32 | file_size − 8 |
| 0x08 | u32 | version = 3 |
| 0x10 | u64 | uncompressed payload size |
| 0x18 | u64 | file_size − 8 |
| 0x20 | 16 B | runtime pointer garbage (ignored) |
| 0x30 | … | **LZ4 raw block stream** → NMG9 payload |

### NMG9 payload

```
'NMG9'
u32 vertex_count            vertex_count × { f32 x, y, z }          (world meters, Z up)
u32 edge_count              edge_count × { -1, u32 va, u32 vb, -1, -1, 0 }   (24 B)
u32 face_count              face_count × { u32 n; n×u32 verts; n×u32 edges;
                                            i32 2; i32 0; i32 face_id; i32 0;
                                            i32 scene_level_mask; u8 flag }    (4+8n+21 B, unaligned)
u32 32; 256 × 0x00          reserved footer
```

Every edge is referenced by exactly 1 (boundary) or 2 (interior) faces.

### terrain.bin — `ZGR6` container

5 LZ4 sections (`MIDX HGHT NRML WGHT PHYM`) with per-node offset tables.
`HGHT` nodes are 129×129 (battle scenes) / 257×257 (world map) 16-bit PNGs;
u16 → world height via `<terrain min_height max_height>` in `scene.xscene`.

### NMG8 — navmesh prefab (`Scene.ImportNavigationMeshPrefab`)

`u32 size−4; 'NMG8'; u32 nv; nv×xyz; u32 nt; nt×3×u32`.

## Layout

- `blnav/` — core library (`rnm1`, `nmg9`, `nmg8`, `terrain`, `xscene`, `lz4raw`, `generate`)
- `server/` — MCP server (`mcp_server.py`) + web GUI (`web.py`, `static/index.html`)
- `tests/` — validation against `empire_town_s`, vanilla `Main_map` and DADG `Main_map`

## Web GUI

```powershell
python server\web.py "D:\...\Modules\SandBoxCore\SceneObj\empire_town_s"
# open http://127.0.0.1:8770
```

3D view of terrain + navmesh. Click faces (shift = multi-select), delete faces,
set face id / scene-level visibility mask, generate a navmesh from the terrain (whole map or a region),
save back to `navmesh.bin` (first save keeps a `.bak`).

## MCP server (LLM-driven editing)

```jsonc
// .mcp.json
{
  "mcpServers": {
    "bannerlord-navmesh": {
      "command": "python",
      "args": ["C:/Users/Joe/Desktop/bannerlord-navmesh-studio/server/mcp_server.py"]
    }
  }
}
```

Tools: `load_scene`, `scene_info`, `sample_height`, `query_faces`,
`generate_navmesh`, `add_face`, `delete_faces`, `set_face_attributes`,
`move_vertex`, `snap_to_terrain`, `save_navmesh`, `export_obj`.

Typical LLM flow: `load_scene(dir)` → `generate_navmesh(cell_size=4, max_slope_deg=40)`
→ inspect with `query_faces` → `save_navmesh()`.

## Validation

```
python tests/test_roundtrip.py       # byte-identical NMG9 re-serialization + LZ4 re-encode
python tests/test_terrain.py         # all 5 terrain sections, heightmap assembly
python tests/test_crossvalidate.py   # navmesh vertices vs terrain surface heights
python tests/test_generate.py        # generator winding/topology vs vanilla
python tests/test_mcp.py             # MCP tools end-to-end (in-process client)
python tests/test_web.py             # web API (server must be running)
python tests/test_gui_render.py      # headless-browser render check (playwright)
python tests/test_dadg_map.py        # third navmesh sample (DADG England map)
```

### Live in-game test (manual, swaps a game file)

```powershell
python tests\swap_dadg_map_navmesh.py          # backs up original as navmesh.bin.orig, swaps in re-encoded file
# launch Bannerlord, load a DADG campaign, verify parties pathfind on the map
python tests\swap_dadg_map_navmesh.py restore  # put the original back
```

## Known unknowns

- `g5` is a signed scene-level visibility bitmask, confirmed against the native
  editor inspector and level filters. It is not an island/group identifier.
  The shipped SandBox Main_map uses `-109` on 13,304 of 17,153 faces; its other
  masks are `-101` (3,564), `-103` (276), and `-69` (9). Native and DADG define
  base=1, level_1=2, level_2=4, level_3=8, civilian=16, siege=32, looted=64.
  `-109` enables base, level_1, and civilian among these levels. Preserve its
  upper bits. Native variants and authored masks must not be normalized blindly.
- New Main_map faces created through the web/MCP APIs default to `g5=-109`;
  other scenes and the low-level terrain generator default to `-1` (all levels).
  Existing masks are preserved on load/save. The API parameter is now
  `scene_level_mask`; the obsolete `group` mutation parameter is rejected to
  prevent island IDs from accidentally changing level visibility.
- Campaign preview defaults to requiring base + level_1 + civilian. Disable the
  level filter to inspect all faces, including intentionally restricted levels.
  This models the visibility bits, not campaign pathfinding or native rendering.
- The 24-byte edge records' `-1` slots are assumed runtime-filled adjacency.
- Re-encoded LZ4 streams are valid LZ4 but not byte-identical to TaleWorlds' encoder
  output; payloads are byte-identical. In-game load test pending.
