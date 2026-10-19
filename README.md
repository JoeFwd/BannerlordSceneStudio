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
| 0x30 | … | **LZ4 raw block stream** → NMG8 or NMG9 scene payload |

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

Older **NMG8 scene payloads** use the same polygon layout and footer, but start
with `'NMG8'` and have 20-byte edges (omit the final `u32 0`). `blnav.nmg9.NavMesh`
and the Studio loader detect both versions automatically. Saving preserves the
loaded version and raw face fields; newly created meshes default to NMG9.
Unsupported edge fields and nonzero NMG9 edge flags are rejected.

### terrain.bin — `ZGR6` container

5 LZ4 sections (`MIDX HGHT NRML WGHT PHYM`) with per-node offset tables.
`HGHT` nodes are 129×129 (battle scenes) / 257×257 (world map) 16-bit PNGs;
u16 → world height via `<terrain min_height max_height>` in `scene.xscene`.

### NMG8 — navmesh prefab (`Scene.ImportNavigationMeshPrefab`)

`u32 size−4; 'NMG8'; u32 nv; nv×xyz; u32 nt; nt×3×u32`.
This uncompressed, size-prefixed triangle format remains handled by `blnav.nmg8`;
it is distinct from an RNM1-compressed NMG8 polygon scene mesh.

### terrain_ed.bin — `OK01` container (editor terrain source, container decoded)

`SceneEditData/<scene>/terrain_ed.bin`. Same container family as `RNM1`; the
existing `blnav.lz4raw.decompress_prefix` reads it as-is.

| offset | type | meaning |
|--------|------|---------|
| 0x00 | `'OK01'` | magic |
| 0x04 | u32 | file_size − 12 |
| 0x08 | u32 | 0 |
| 0x0C | u32 | version = 2 |
| 0x10 | u32 | 0 |
| 0x14 | u64 | uncompressed payload size |
| 0x1C | u64 | file_size − 12 (repeat of 0x04) |
| 0x24 | 16 B | runtime pointer garbage (ignored) |
| 0x34 | … | **LZ4 raw block stream** → payload |

Verified across 108 shipped + DADG scenes: decompression consumes exactly the
declared byte count and yields exactly the declared size.

Payload (decoded 2026-08-18; the earlier "non-constant stride" reading was wrong —
the stride varies because the per-node layer *count* varies):

```
u32 node_dim_x, node_dim_y     ← match <terrain node_dimension_x/y> in scene.xscene

node_dim_x × node_dim_y nodes, walked COLUMN-major: (0,0) (0,1) … (0,dimy−1) (1,0) …
  u32 node_x, node_y
  u32 mask[4]                  layer-usage bitmasks (see below)
  u32 res_x, res_y             per-node vertex resolution (5 / 33 / 65 / 129 / 257 / 513)
  f32 normals[N][4]            x, y, z, pad — unit length;  N = res_x × res_y
  u32 res_x, res_y             repeated header for the next block
  f32 blockB[N]                all-zero in 104 of 108 scenes (meaning TBD)
  u32 layer_res[32]            16 × (res_x, res_y) palette slot table, (0,0) = unused slot
  f32 heights[N]               world-space metres
  u32 nlayers
  nlayers × { u32 layer_index; f32 weights[N] }     layer_index is 1-based
```

Verified on all 108 scenes here: the walk consumes the payload **exactly**, with no
trailing bytes, and `heights` matches the `ZGR6` `HGHT` PNGs to within one
quantisation step ((max−min)/65535).

Two orientation traps, both confirmed against `ZGR6`:

- **Vertex order is transposed.** `heights`/`weights` are `[res_x][res_y]`; the `ZGR6`
  PNG for the same node is the transpose. Reshape `(res_x, res_y)` then `.T`.
- **Node order is transposed too.** `OK01` walks nodes column-major; `ZGR6`'s per-node
  offset tables are indexed row-major. `zgr6_index = node_y × node_dim_x + node_x`.

`mask[4]` is **four independent per-node layer bitmasks, not four copies** — they are
equal in only 60 of 108 scenes. The set of stored weight planes is their **union**:
`layer_index == bit + 1` over `mask[0]|mask[1]|mask[2]|mask[3]`. Zero counter-examples
across all 108 scenes / 6 500+ nodes. (What distinguishes the four masks from each other
is still open; the union is what governs the payload layout.)

`layer_res[32]` is a fixed **16-slot palette capacity table**, not a per-scene layer list:
slots are filled contiguously from slot 0 and hold that node's resolution, but the filled
count is 16 in 101 of 108 scenes regardless of how many layers the scene declares, so it
does **not** equal the `<layers>` count. `layer_index` indexes this palette 1-based, and
the palette is **sparse** — `dadg_joust_v3` declares 15 layers named `1_base`,
`2_grass_flora`, `14_wet_flora`, … in scrambled document order, and the name prefix, not
the document position, is the `layer_index`.

The compiled `WGHT` section mirrors this: each node is 16 palette slots of
`u32 count` followed by `count × (u32 png_len; PNG)` (8-bit greyscale), `count = 0`
for an unpainted layer. `HGHT`/`NRML` nodes are instead a single `u32 png_len; PNG`
(16-bit greyscale / 8-bit RGBA).

Writing `OK01` back is straightforward: re-LZ4 the payload and re-emit the 0x34
header (`sz1 == sz2 == file_size − 12`, holds on all 108 scenes; the 16 pointer
bytes are ignored, zeros are fine). `lz4.block` round-trips the payload
byte-identically; `mode="high_compression", compression=12` lands at ~94% of
TaleWorlds' own file size.

Normals are **derivable from heights** — `normalize(-dh/dx, -dh/dy, 1)` by central
differences, with vertex spacing `node_size / (res − 1)`. It is not the engine's
exact filter (max deviation 0.29 on 40°+ slopes) but it is accurate where it
matters: 0.0054 max on flat ground, 0.0003 mean on gentle terrain. Recompute only
at vertices whose height you changed. The `ZGR6` `NRML` PNG is *not* a usable
source for this — red/green are x/y as `(c/255)·2−1`, but blue is not z. The
4th f32 of each `OK01` normal is uninitialised padding (`inf` in places) — copy it
through, never read it.

`OK01` is the editor *source* and carries more channels than the compiled `ZGR6`
runtime terrain, so `ZGR6 → OK01` is a **lossy decompile**, not a round trip — the
discarded channels get defaulted. Worth building anyway: **392 of 494 (79%) of
terrain-bearing vanilla scenes ship compiled-only**, with no `terrain_ed.bin` at all,
so a decompiler is the only way to open native/sandbox terrain in the editor.
See `docs/scene-composer-design.md` for the staged plan.

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
`validate_navmesh`,
`move_vertex`, `snap_to_terrain`, `save_navmesh`, `export_obj`.

Typical LLM flow: `load_scene(dir)` → `generate_navmesh(cell_size=4, max_slope_deg=40)`
→ inspect with `query_faces` → `save_navmesh()`.

## Validation

```
python tests/test_roundtrip.py       # byte-identical NMG9 re-serialization + LZ4 re-encode
python tests/test_scene_formats.py   # synthetic NMG8/NMG9 parsing, validation, load/save
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
