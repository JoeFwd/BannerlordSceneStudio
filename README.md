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
                                            i32 group; u8 flag }    (4+8n+21 B, unaligned)
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

- `blnav/` — core library (`rnm1`, `nmg9`, `nmg8`, `terrain`, `xscene`, `lz4raw`)
- `server/` — MCP server + web viewer
- `tests/` — validation against `empire_town_s` and `Main_map` shipped scenes

## Validation

```
python tests/test_roundtrip.py       # byte-identical NMG9 re-serialization + LZ4 re-encode
python tests/test_terrain.py         # all 5 terrain sections, heightmap assembly
python tests/test_crossvalidate.py   # navmesh vertices vs terrain surface heights
```
